"""Transactional local job queue. No paths or SQL fragments originate in requests."""

from __future__ import annotations

import re
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

import rfc8785

from .backend_api import bounded_json
from .canonical import parse_json, validate_ijson


class JobStoreError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class JobClaim:
    job_id: str
    token: str
    request: bytes


class JobStore:
    """Single-user SQLite store with atomic idempotency, claims and result publication.

    Cancellation of running work prevents publication; it is not a process kill.
    A lease expiry is an operational failure, never mathematical infeasibility.
    """

    def __init__(
        self,
        path: Path,
        *,
        max_jobs: int = 1000,
        lease_seconds: int = 300,
        max_payload_bytes: int = 256_000_000,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not (
            type(max_jobs) is int
            and 1 <= max_jobs <= 100_000
            and type(lease_seconds) is int
            and 1 <= lease_seconds <= 3600
            and type(max_payload_bytes) is int
            and 1 <= max_payload_bytes <= 1_000_000_000
        ):
            raise JobStoreError("store.invalid_limits")
        self.path = path.resolve()
        self.max_jobs = max_jobs
        self.lease_seconds = lease_seconds
        self.max_payload_bytes = max_payload_bytes
        self.clock = clock
        with self._transaction() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, 1}:
                raise JobStoreError("store.unsupported_version")
            if version == 0:
                existing = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
                if existing:
                    raise JobStoreError("store.unrecognized_database")
                connection.execute("""CREATE TABLE jobs (
                    job_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    request_hash TEXT NOT NULL,
                    request BLOB NOT NULL,
                    status TEXT NOT NULL CHECK(status IN (
                        'QUEUED','RUNNING','CANCEL_REQUESTED','CANCELLED','SUCCEEDED','FAILED')),
                    created_at REAL NOT NULL,
                    token TEXT,
                    lease_until REAL,
                    result BLOB,
                    result_hash TEXT,
                    error_code TEXT
                )""")
                connection.execute("PRAGMA user_version=1")

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        finally:
            connection.close()

    def submit(self, request: str | bytes, idempotency_key: str) -> str:
        if not isinstance(idempotency_key, str) or not re.fullmatch(
            r"[A-Za-z0-9._:-]{1,128}", idempotency_key
        ):
            raise JobStoreError("store.invalid_idempotency_key")
        payload = rfc8785.dumps(bounded_json(request))
        digest = sha256(payload).hexdigest()
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT job_id,request_hash FROM jobs WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone()
            if row:
                if row["request_hash"] != digest:
                    raise JobStoreError("store.idempotency_conflict")
                return str(row["job_id"])
            if connection.execute("SELECT count(*) FROM jobs").fetchone()[0] >= self.max_jobs:
                raise JobStoreError("store.capacity")
            used = connection.execute(
                "SELECT coalesce(sum(length(request)+coalesce(length(result),0)),0) FROM jobs"
            ).fetchone()[0]
            if used + len(payload) > self.max_payload_bytes:
                raise JobStoreError("store.payload_capacity")
            job_id = "job_" + uuid4().hex
            connection.execute(
                "INSERT INTO jobs(job_id,idempotency_key,request_hash,request,status,created_at) "
                "VALUES(?,?,?,?,?,?)",
                (job_id, idempotency_key, digest, payload, "QUEUED", self.clock()),
            )
            return job_id

    def recover_expired(self) -> int:
        with self._transaction() as connection:
            cancelled = connection.execute(
                "UPDATE jobs SET status='CANCELLED',token=NULL,lease_until=NULL "
                "WHERE status='CANCEL_REQUESTED' AND lease_until<=?",
                (self.clock(),),
            ).rowcount
            failed = connection.execute(
                "UPDATE jobs SET status='FAILED',error_code='E_WORKER_INTERRUPTED',"
                "token=NULL,lease_until=NULL WHERE status='RUNNING' AND lease_until<=?",
                (self.clock(),),
            ).rowcount
            return cancelled + failed

    def claim(self) -> JobClaim | None:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT job_id,request,request_hash FROM jobs WHERE status='QUEUED' "
                "ORDER BY created_at,job_id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            payload = bytes(row["request"])
            if sha256(payload).hexdigest() != row["request_hash"]:
                raise JobStoreError("store.request_integrity")
            token = uuid4().hex
            connection.execute(
                "UPDATE jobs SET status='RUNNING',token=?,lease_until=? "
                "WHERE job_id=? AND status='QUEUED'",
                (token, self.clock() + self.lease_seconds, row["job_id"]),
            )
            return JobClaim(str(row["job_id"]), token, payload)

    def finish(self, claim: JobClaim, result: dict[str, Any], *, failed: bool = False) -> bool:
        validate_ijson(result)
        payload = rfc8785.dumps(result)
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT status,token,lease_until FROM jobs WHERE job_id=?", (claim.job_id,)
            ).fetchone()
            if (
                row is None
                or row["token"] != claim.token
                or row["status"] not in {"RUNNING", "CANCEL_REQUESTED"}
            ):
                return False
            if row["status"] == "CANCEL_REQUESTED":
                connection.execute(
                    "UPDATE jobs SET status='CANCELLED',token=NULL,lease_until=NULL WHERE job_id=?",
                    (claim.job_id,),
                )
                return False
            if row["lease_until"] <= self.clock():
                connection.execute(
                    "UPDATE jobs SET status='FAILED',error_code='E_WORKER_INTERRUPTED',"
                    "token=NULL,lease_until=NULL WHERE job_id=?",
                    (claim.job_id,),
                )
                return False
            used = connection.execute(
                "SELECT coalesce(sum(length(request)+coalesce(length(result),0)),0) FROM jobs"
            ).fetchone()[0]
            if len(payload) > 32_000_000 or used + len(payload) > self.max_payload_bytes:
                connection.execute(
                    "UPDATE jobs SET status='FAILED',error_code='E_STORAGE_LIMIT',"
                    "token=NULL,lease_until=NULL WHERE job_id=?",
                    (claim.job_id,),
                )
                return False
            connection.execute(
                "UPDATE jobs SET status=?,result=?,result_hash=?,token=NULL,lease_until=NULL "
                "WHERE job_id=?",
                (
                    "FAILED" if failed else "SUCCEEDED",
                    payload,
                    sha256(payload).hexdigest(),
                    claim.job_id,
                ),
            )
            return True

    def cancel(self, job_id: str) -> str:
        with self._transaction() as connection:
            row = connection.execute("SELECT status FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise JobStoreError("store.not_found")
            status = {"QUEUED": "CANCELLED", "RUNNING": "CANCEL_REQUESTED"}.get(
                row["status"], row["status"]
            )
            connection.execute("UPDATE jobs SET status=? WHERE job_id=?", (status, job_id))
            return str(status)

    def list_jobs(self, *, limit: int = 20, offset: int = 0) -> dict[str, Any]:
        if not (
            type(limit) is int
            and 1 <= limit <= 100
            and type(offset) is int
            and 0 <= offset <= 100_000
        ):
            raise JobStoreError("store.pagination")
        with self._transaction() as connection:
            rows = connection.execute(
                "SELECT job_id,status,request_hash FROM jobs "
                "ORDER BY created_at,job_id LIMIT ? OFFSET ?",
                (limit + 1, offset),
            ).fetchall()
            return {
                "jobs": [dict(row) for row in rows[:limit]],
                "next_offset": offset + limit if len(rows) > limit else None,
            }

    def get(self, job_id: str) -> dict[str, Any]:
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT job_id,status,request_hash,result,result_hash,error_code "
                "FROM jobs WHERE job_id=?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise JobStoreError("store.not_found")
            result = None
            if row["result"] is not None:
                if sha256(row["result"]).hexdigest() != row["result_hash"]:
                    raise JobStoreError("store.result_integrity")
                result = parse_json(row["result"])
            return {
                "job_id": row["job_id"],
                "status": row["status"],
                "request_sha256": row["request_hash"],
                "result_sha256": row["result_hash"],
                "result": result,
                "error_code": row["error_code"],
            }
