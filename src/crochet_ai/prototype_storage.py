"""Bounded SQLite persistence for local prototype projects and user reports."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any

import rfc8785

from .canonical import parse_json

MAX_PROJECTS = 100
MAX_FEEDBACK = 10_000
MAX_TOTAL_PAYLOAD_BYTES = 64 * 1024 * 1024
MAX_PROJECT_PAYLOAD_BYTES = 4 * 1024 * 1024


class PrototypeStoreError(RuntimeError):
    pass


class PrototypeStore:
    def __init__(self, data_dir: Path) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / "prototype.sqlite3"
        self.lock = RLock()
        self.db = sqlite3.connect(
            self.path, timeout=5, isolation_level=None, check_same_thread=False
        )
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute("PRAGMA max_page_count=16384")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                source_sha256 TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                project_id TEXT PRIMARY KEY REFERENCES projects(project_id),
                revision INTEGER NOT NULL, cursor INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS feedback (
                feedback_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(project_id),
                source_sha256 TEXT NOT NULL, payload TEXT NOT NULL
            );
            """
        )

    @staticmethod
    def _dump(value: Any) -> str:
        return rfc8785.dumps(value).decode("utf-8")

    def list_projects(self) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.db.execute(
                "SELECT project_id, source_sha256, created_at, payload "
                "FROM projects ORDER BY created_at DESC"
            ).fetchall()
        summaries = []
        for row in rows:
            request = self._parse_object(row[3])["request"]
            summaries.append(
                {
                    "project_id": row[0],
                    "source_crochet_ir_sha256": row[1],
                    "created_at": row[2],
                    "shape": request["shape"],
                    "diameter_mm": request["diameter_mm"],
                    "height_mm": request["height_mm"],
                    "yarn_label": request["yarn_label"],
                }
            )
        return summaries

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.db.execute(
                "SELECT payload FROM projects WHERE project_id=?", (project_id,)
            ).fetchone()
        return None if row is None else self._parse_object(row[0])

    @staticmethod
    def _parse_object(payload: str) -> dict[str, Any]:
        value = parse_json(payload)
        if not isinstance(value, dict):
            raise PrototypeStoreError("store.invalid_payload")
        return value

    def save_project(self, project: dict[str, Any], created_at: str) -> dict[str, Any]:
        pid = project["project_id"]
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                prior = self.db.execute(
                    "SELECT revision, cursor FROM sessions WHERE project_id=?", (pid,)
                ).fetchone()
                if prior is None:
                    count = self.db.execute("SELECT count(*) FROM projects").fetchone()[0]
                    if count >= MAX_PROJECTS:
                        raise PrototypeStoreError("store.project_limit")
                    revision, cursor = 0, 0
                    project["session"] = {"project_id": pid, "revision": revision, "cursor": cursor}
                    payload = self._dump(project)
                    payload_bytes = len(payload.encode("utf-8"))
                    used = (
                        self.db.execute(
                            "SELECT coalesce(sum(length(CAST(payload AS BLOB))), 0) FROM projects"
                        ).fetchone()[0]
                        + self.db.execute(
                            "SELECT coalesce(sum(length(CAST(payload AS BLOB))), 0) FROM feedback"
                        ).fetchone()[0]
                    )
                    if (
                        payload_bytes > MAX_PROJECT_PAYLOAD_BYTES
                        or used + payload_bytes > MAX_TOTAL_PAYLOAD_BYTES
                    ):
                        raise PrototypeStoreError("store.byte_limit")
                    self.db.execute(
                        "INSERT INTO projects VALUES (?, ?, ?, ?)",
                        (pid, payload, project["source_crochet_ir_sha256"], created_at),
                    )
                    self.db.execute(
                        "INSERT INTO sessions VALUES (?, ?, ?)", (pid, revision, cursor)
                    )
                else:
                    revision, cursor = prior
                    row = self.db.execute(
                        "SELECT payload, source_sha256 FROM projects WHERE project_id=?", (pid,)
                    ).fetchone()
                    if row is None or row[1] != project["source_crochet_ir_sha256"]:
                        raise PrototypeStoreError("store.source_conflict")
                    project = self._parse_object(row[0])
                    project["session"] = {"project_id": pid, "revision": revision, "cursor": cursor}
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
        return project

    def set_session(
        self, project_id: str, expected_revision: object, cursor: object
    ) -> dict[str, Any]:
        if (
            type(expected_revision) is not int
            or expected_revision < 0
            or type(cursor) is not int
            or cursor < 0
        ):
            raise ValueError("session.bounds")
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                row = self.db.execute(
                    "SELECT revision FROM sessions WHERE project_id=?", (project_id,)
                ).fetchone()
                project = self.get_project(project_id)
                if row is None or project is None:
                    raise KeyError("project.not_found")
                if row[0] != expected_revision:
                    raise PrototypeStoreError("E_CONFLICT")
                if cursor > len(project["steps"]):
                    raise ValueError("session.cursor")
                revision = expected_revision + 1
                session = {"project_id": project_id, "revision": revision, "cursor": cursor}
                self.db.execute(
                    "UPDATE sessions SET revision=?, cursor=? WHERE project_id=?",
                    (revision, cursor, project_id),
                )
                project["session"] = session
                self.db.execute(
                    "UPDATE projects SET payload=? WHERE project_id=?",
                    (self._dump(project), project_id),
                )
                self.db.execute("COMMIT")
                return session
            except Exception:
                self.db.execute("ROLLBACK")
                raise

    def add_feedback(self, record: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            count = self.db.execute("SELECT count(*) FROM feedback").fetchone()[0]
            if count >= MAX_FEEDBACK:
                raise PrototypeStoreError("store.feedback_limit")
            payload = self._dump(record)
            used = (
                self.db.execute(
                    "SELECT coalesce(sum(length(CAST(payload AS BLOB))), 0) FROM projects"
                ).fetchone()[0]
                + self.db.execute(
                    "SELECT coalesce(sum(length(CAST(payload AS BLOB))), 0) FROM feedback"
                ).fetchone()[0]
            )
            if used + len(payload.encode("utf-8")) > MAX_TOTAL_PAYLOAD_BYTES:
                raise PrototypeStoreError("store.byte_limit")
            self.db.execute(
                "INSERT INTO feedback VALUES (?, ?, ?, ?)",
                (
                    record["feedback_id"],
                    record["project_id"],
                    record["source_crochet_ir_sha256"],
                    payload,
                ),
            )
        return record

    def feedback(self, project_id: str) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.db.execute(
                "SELECT payload FROM feedback WHERE project_id=? ORDER BY rowid", (project_id,)
            ).fetchall()
        return [self._parse_object(row[0]) for row in rows]

    def close(self) -> None:
        self.db.close()
