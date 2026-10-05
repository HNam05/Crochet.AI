"""Append-only, bounded local storage for frozen calibration evidence."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Any, Literal, cast

import rfc8785

from .calibration_campaign import (
    CAMPAIGN_HASH_PROFILE,
    MEASUREMENT_HASH_PROFILE,
    CalibrationCampaign,
    CalibrationError,
    CalibrationMeasurement,
    record_hash,
)
from .canonical import parse_json

MAX_RECORD_BYTES = 64 * 1024
MAX_CAMPAIGNS = 100
MAX_MEASUREMENTS = 10_000
MAX_TOTAL_PAYLOAD_BYTES = 64 * 1024 * 1024
APPLICATION_ID = 0x43414C31


class CalibrationStoreError(ValueError):
    """A stored calibration record conflicts, exceeds limits, or is corrupt."""


class CalibrationStore:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.db = sqlite3.connect(
            self.path, timeout=5, isolation_level=None, check_same_thread=False
        )
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute("PRAGMA synchronous=FULL")
        try:
            with self._transaction():
                version = self.db.execute("PRAGMA user_version").fetchone()[0]
                application_id = self.db.execute("PRAGMA application_id").fetchone()[0]
                if version not in (0, 1):
                    raise CalibrationStoreError("store.unsupported_version")
                if version == 1:
                    if application_id != APPLICATION_ID:
                        raise CalibrationStoreError("store.unrecognized_database")
                    self._validate_schema()
                else:
                    tables = self.db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                    if application_id != 0 or tables:
                        raise CalibrationStoreError("store.unrecognized_database")
                    self.db.execute("""CREATE TABLE campaigns (
                        campaign_sha256 TEXT PRIMARY KEY,
                        campaign_id TEXT NOT NULL UNIQUE,
                        payload BLOB NOT NULL
                    )""")
                    self.db.execute("""CREATE TABLE measurements (
                        measurement_sha256 TEXT PRIMARY KEY,
                        record_id TEXT NOT NULL UNIQUE,
                        campaign_sha256 TEXT NOT NULL REFERENCES campaigns(campaign_sha256),
                        specimen_id TEXT NOT NULL,
                        supersedes_sha256 TEXT REFERENCES measurements(measurement_sha256),
                        payload BLOB NOT NULL
                    )""")
                    self.db.execute(
                        "CREATE UNIQUE INDEX one_successor_per_measurement "
                        "ON measurements(supersedes_sha256) WHERE supersedes_sha256 IS NOT NULL"
                    )
                    self.db.execute(f"PRAGMA application_id={APPLICATION_ID}")
                    self.db.execute("PRAGMA user_version=1")
            self.db.execute("PRAGMA journal_mode=WAL")
        except BaseException:
            self.db.close()
            raise

    def _validate_schema(self) -> None:
        expected = {
            "campaigns": {
                "campaign_sha256",
                "campaign_id",
                "payload",
            },
            "measurements": {
                "measurement_sha256",
                "record_id",
                "campaign_sha256",
                "specimen_id",
                "supersedes_sha256",
                "payload",
            },
        }
        actual_tables = {
            row[0]
            for row in self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        if actual_tables != set(expected):
            raise CalibrationStoreError("store.schema_mismatch")
        for table, columns in expected.items():
            table_info = self.db.execute(f"PRAGMA table_info({table})").fetchall()
            actual_columns = {row[1] for row in table_info}
            expected_order = (
                ("campaign_sha256", "campaign_id", "payload")
                if table == "campaigns"
                else (
                    "measurement_sha256",
                    "record_id",
                    "campaign_sha256",
                    "specimen_id",
                    "supersedes_sha256",
                    "payload",
                )
            )
            if actual_columns != columns or tuple(row[1] for row in table_info) != expected_order:
                raise CalibrationStoreError("store.schema_mismatch")
            primary_key = "campaign_sha256" if table == "campaigns" else "measurement_sha256"
            nullable = {primary_key}
            if table == "measurements":
                nullable.add("supersedes_sha256")
            for row in table_info:
                expected_info = (
                    "BLOB" if row[1] == "payload" else "TEXT",
                    int(row[1] not in nullable),
                    None,
                    int(row[1] == primary_key),
                )
                if tuple(row[2:]) != expected_info:
                    raise CalibrationStoreError("store.schema_mismatch")
            expected_unique = {
                (primary_key,),
                ("campaign_id" if table == "campaigns" else "record_id",),
            }
            actual_unique = set()
            for index_row in self.db.execute(f"PRAGMA index_list({table})").fetchall():
                if index_row[2] and not index_row[4]:
                    actual_unique.add(
                        tuple(
                            entry[2]
                            for entry in self.db.execute(
                                "SELECT seqno,cid,name FROM pragma_index_info(?) ORDER BY seqno",
                                (index_row[1],),
                            )
                        )
                    )
            if actual_unique != expected_unique:
                raise CalibrationStoreError("store.schema_mismatch")
        indexes = self.db.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' "
            "AND name='one_successor_per_measurement'"
        ).fetchone()
        expected_index_sql = (
            "CREATE UNIQUE INDEX one_successor_per_measurement "
            "ON measurements(supersedes_sha256) WHERE supersedes_sha256 IS NOT NULL"
        )
        if indexes is None or " ".join(indexes[0].split()).upper() != expected_index_sql.upper():
            raise CalibrationStoreError("store.schema_mismatch")
        expected_foreign_keys = {
            ("campaigns", "campaign_sha256", "campaign_sha256", "NO ACTION", "NO ACTION", "NONE"),
            (
                "measurements",
                "supersedes_sha256",
                "measurement_sha256",
                "NO ACTION",
                "NO ACTION",
                "NONE",
            ),
        }
        actual_foreign_keys = {
            tuple(row[2:]) for row in self.db.execute("PRAGMA foreign_key_list(measurements)")
        }
        if actual_foreign_keys != expected_foreign_keys:
            raise CalibrationStoreError("store.schema_mismatch")

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise

    @staticmethod
    def _payload(value: dict[str, Any]) -> bytes:
        try:
            payload = rfc8785.dumps(value)
        except (TypeError, ValueError) as error:
            raise CalibrationStoreError("store.invalid_payload") from error
        if len(payload) > MAX_RECORD_BYTES:
            raise CalibrationStoreError("store.record_capacity")
        return payload

    def _check_capacity(self, payload_size: int, kind: Literal["campaign", "measurement"]) -> None:
        campaign_count = self.db.execute("SELECT count(*) FROM campaigns").fetchone()[0]
        measurement_count = self.db.execute("SELECT count(*) FROM measurements").fetchone()[0]
        used = (
            self.db.execute("SELECT coalesce(sum(length(payload)),0) FROM campaigns").fetchone()[0]
            + self.db.execute(
                "SELECT coalesce(sum(length(payload)),0) FROM measurements"
            ).fetchone()[0]
        )
        if campaign_count + (kind == "campaign") > MAX_CAMPAIGNS:
            raise CalibrationStoreError("store.campaign_capacity")
        if measurement_count + (kind == "measurement") > MAX_MEASUREMENTS:
            raise CalibrationStoreError("store.measurement_capacity")
        if used + payload_size > MAX_TOTAL_PAYLOAD_BYTES:
            raise CalibrationStoreError("store.payload_capacity")

    def register_campaign(self, campaign: CalibrationCampaign) -> str:
        value = campaign.to_dict()
        if CalibrationCampaign(value).sha256 != campaign.sha256:
            raise CalibrationStoreError("store.campaign_hash_mismatch")
        payload = self._payload(value)
        with self._transaction():
            prior = self.db.execute(
                "SELECT campaign_sha256 FROM campaigns WHERE campaign_id=?",
                (value["campaign_id"],),
            ).fetchone()
            if prior:
                if prior[0] != campaign.sha256:
                    raise CalibrationStoreError("store.campaign_id_conflict")
                self._read_campaign(campaign.sha256)
                return campaign.sha256
            self._check_capacity(len(payload), "campaign")
            self.db.execute(
                "INSERT INTO campaigns VALUES(?,?,?)",
                (campaign.sha256, value["campaign_id"], payload),
            )
        return campaign.sha256

    def _read_campaign(self, digest: str) -> CalibrationCampaign | None:
        row = self.db.execute(
            "SELECT payload,campaign_id FROM campaigns WHERE campaign_sha256=?", (digest,)
        ).fetchone()
        if row is None:
            return None
        try:
            value = cast(dict[str, Any], parse_json(row[0]))
            record = CalibrationCampaign(value)
            if value["campaign_id"] != row[1]:
                raise CalibrationStoreError("store.corrupt_campaign_binding")
            if (
                record.sha256 != digest
                or record_hash(CAMPAIGN_HASH_PROFILE, record.to_dict()) != digest
            ):
                raise CalibrationStoreError("store.corrupt_campaign_hash")
            return record
        except (ValueError, TypeError, CalibrationError) as error:
            if isinstance(error, CalibrationStoreError):
                raise
            raise CalibrationStoreError("store.corrupt_campaign") from error

    def get_campaign(self, digest: str) -> CalibrationCampaign | None:
        with self.lock:
            return self._read_campaign(digest)

    def add_measurement(self, measurement: CalibrationMeasurement) -> str:
        value = measurement.to_dict()
        payload = self._payload(value)
        with self._transaction():
            campaign_hash = value["campaign_sha256"]
            campaign = self._read_campaign(campaign_hash)
            if campaign is None:
                raise CalibrationStoreError("store.unregistered_campaign")
            try:
                checked = CalibrationMeasurement(value, campaign)
            except (ValueError, TypeError) as error:
                raise CalibrationStoreError("store.measurement_campaign_binding") from error
            if checked.sha256 != measurement.sha256:
                raise CalibrationStoreError("store.measurement_hash_mismatch")
            prior_id = self.db.execute(
                "SELECT measurement_sha256 FROM measurements WHERE record_id=?",
                (value["record_id"],),
            ).fetchone()
            if prior_id:
                if prior_id[0] != measurement.sha256:
                    raise CalibrationStoreError("store.record_id_conflict")
                self._read_measurement(measurement.sha256)
                return measurement.sha256
            parent_hash = value["supersedes_sha256"]
            if parent_hash is not None:
                parent = self.db.execute(
                    "SELECT campaign_sha256,specimen_id,supersedes_sha256 FROM measurements "
                    "WHERE measurement_sha256=?",
                    (parent_hash,),
                ).fetchone()
                if parent is None:
                    raise CalibrationStoreError("store.correction_parent_missing")
                if parent[0] != campaign_hash or parent[1] != value["specimen_id"]:
                    raise CalibrationStoreError("store.correction_binding")
                self._read_measurement(parent_hash)
                if self.db.execute(
                    "SELECT 1 FROM measurements WHERE supersedes_sha256=?", (parent_hash,)
                ).fetchone():
                    raise CalibrationStoreError("store.correction_fork")
            self._check_capacity(len(payload), "measurement")
            self.db.execute(
                "INSERT INTO measurements VALUES(?,?,?,?,?,?)",
                (
                    measurement.sha256,
                    value["record_id"],
                    campaign_hash,
                    value["specimen_id"],
                    parent_hash,
                    payload,
                ),
            )
        return measurement.sha256

    def _read_measurement(self, digest: str) -> CalibrationMeasurement | None:
        row = self.db.execute(
            "SELECT payload,campaign_sha256,record_id,specimen_id,supersedes_sha256 "
            "FROM measurements WHERE measurement_sha256=?",
            (digest,),
        ).fetchone()
        if row is None:
            return None
        try:
            value = cast(dict[str, Any], parse_json(row[0]))
            campaign = self._read_campaign(row[1])
            if campaign is None:
                raise CalibrationStoreError("store.corrupt_measurement_campaign")
            record = CalibrationMeasurement(value, campaign)
            if (
                record.sha256 != digest
                or record_hash(MEASUREMENT_HASH_PROFILE, record.to_dict()) != digest
            ):
                raise CalibrationStoreError("store.corrupt_measurement_hash")
            if (
                value["campaign_sha256"],
                value["record_id"],
                value["specimen_id"],
                value["supersedes_sha256"],
            ) != tuple(row[1:]):
                raise CalibrationStoreError("store.corrupt_measurement_binding")
            return record
        except (ValueError, TypeError, CalibrationError) as error:
            if isinstance(error, CalibrationStoreError):
                raise
            raise CalibrationStoreError("store.corrupt_measurement") from error

    def get_measurement(self, digest: str) -> CalibrationMeasurement | None:
        with self.lock:
            return self._read_measurement(digest)

    def list_measurements(self, campaign_hash: str) -> tuple[CalibrationMeasurement, ...]:
        with self.lock:
            hashes = self.db.execute(
                "SELECT measurement_sha256 FROM measurements WHERE campaign_sha256=? "
                "ORDER BY measurement_sha256",
                (campaign_hash,),
            ).fetchall()
            records: list[CalibrationMeasurement] = []
            for row in hashes:
                record = self._read_measurement(row[0])
                if record is None:
                    raise CalibrationStoreError("store.missing_listed_measurement")
                records.append(record)
        return tuple(records)

    def active_measurements(self, campaign_hash: str) -> tuple[CalibrationMeasurement, ...]:
        records = self.list_measurements(campaign_hash)
        superseded = {item.to_dict()["supersedes_sha256"] for item in records}
        active = tuple(item for item in records if item.sha256 not in superseded)
        seen: set[str] = set()
        for item in active:
            value = item.to_dict()
            if value["specimen_id"] in seen:
                raise CalibrationStoreError("store.ambiguous_active_specimen")
            seen.add(value["specimen_id"])
        return active

    def close(self) -> None:
        with self.lock:
            self.db.close()

    def __enter__(self) -> CalibrationStore:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> Literal[False]:
        self.close()
        return False
