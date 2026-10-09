"""Bounded, local backup and restore for the prototype SQLite store."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import struct
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import TypedDict, cast

import rfc8785

from .canonical import CanonicalizationError, parse_json
from .json_types import JSONValue

FORMAT = "CROCHET_PROTOTYPE_BACKUP_V1"
MAGIC = b"CROCHET-PROTOTYPE-BACKUP\x00V1\n"
MAX_DATABASE_BYTES = 128 * 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024
MAX_BUNDLE_BYTES = len(MAGIC) + 4 + MAX_MANIFEST_BYTES + MAX_DATABASE_BYTES
MAX_BACKUP_CALLBACKS = 16_384
BACKUP_TIMEOUT_SECONDS = 30.0
_TABLE_COLUMNS: dict[str, tuple[tuple[str, str, int], ...]] = {
    "projects": (
        ("project_id", "TEXT", 1),
        ("payload", "TEXT", 0),
        ("source_sha256", "TEXT", 0),
        ("created_at", "TEXT", 0),
    ),
    "sessions": (("project_id", "TEXT", 1), ("revision", "INTEGER", 0), ("cursor", "INTEGER", 0)),
    "feedback": (
        ("feedback_id", "TEXT", 1),
        ("project_id", "TEXT", 0),
        ("source_sha256", "TEXT", 0),
        ("payload", "TEXT", 0),
    ),
}


class BackupError(ValueError):
    """Input, integrity, or destination error in the backup tool."""


class _Manifest(TypedDict):
    format: str
    database_bytes: int
    database_sha256: str
    row_counts: dict[str, int]


def _safe_existing_file(path: Path, label: str) -> Path:
    try:
        absolute = Path(os.path.abspath(path))
        if (
            any(part.is_symlink() for part in _path_components(absolute))
            or absolute.resolve(strict=True) != absolute
            or not absolute.is_file()
        ):
            raise BackupError(f"{label}.not_regular_file")
        return absolute
    except OSError as error:
        raise BackupError(f"{label}.path_error") from error


def _path_components(path: Path) -> tuple[Path, ...]:
    components: list[Path] = []
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        components.append(current)
    return tuple(components)


def _safe_parent(path: Path) -> Path:
    absolute = Path(os.path.abspath(path))
    if (
        not absolute.is_dir()
        or any(part.is_symlink() for part in _path_components(absolute))
        or absolute.resolve(strict=True) != absolute
    ):
        raise BackupError("destination.invalid_parent")
    return absolute


def _inspect_database(path: Path) -> dict[str, int]:
    if path.stat().st_size > MAX_DATABASE_BYTES:
        raise BackupError("database.byte_limit")
    connection: sqlite3.Connection | None = None
    try:
        uri = Path(os.path.abspath(path)).as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True, timeout=5)
        connection.execute("PRAGMA query_only=ON")
        if (
            int(connection.execute("PRAGMA page_count").fetchone()[0])
            * int(connection.execute("PRAGMA page_size").fetchone()[0])
            > MAX_DATABASE_BYTES
        ):
            raise BackupError("database.byte_limit")
        integrity = connection.execute("PRAGMA integrity_check").fetchall()
        if integrity != [("ok",)]:
            raise BackupError("database.integrity_check")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise BackupError("database.foreign_key_check")
        objects = connection.execute(
            "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' "
            "ORDER BY type, name"
        ).fetchall()
        if objects != [("table", name) for name in sorted(_TABLE_COLUMNS)]:
            raise BackupError("database.unexpected_schema")
        for table, expected_columns in _TABLE_COLUMNS.items():
            columns = connection.execute(f"PRAGMA table_info({table})").fetchall()
            actual = tuple((str(row[1]), str(row[2]).upper(), int(row[5])) for row in columns)
            expected = tuple(
                (name, kind, primary_key) for name, kind, primary_key in expected_columns
            )
            if actual != expected or any(
                int(row[3]) != (0 if int(row[5]) else 1) for row in columns
            ):
                raise BackupError("database.unexpected_schema")
        expected_foreign_keys = {
            "sessions": [("projects", "project_id", "project_id")],
            "feedback": [("projects", "project_id", "project_id")],
        }
        for table in ("sessions", "feedback"):
            actual_fk = [
                (str(row[2]), str(row[3]), str(row[4]))
                for row in connection.execute(f"PRAGMA foreign_key_list({table})")
            ]
            if actual_fk != expected_foreign_keys[table]:
                raise BackupError("database.unexpected_schema")
        return {
            table: int(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
            for table in _TABLE_COLUMNS
        }
    except sqlite3.Error as error:
        raise BackupError("database.sqlite_error") from error
    finally:
        if connection is not None:
            connection.close()


def _exclusive_publish(temporary: Path, destination: Path) -> None:
    try:
        if os.name == "nt":
            os.rename(temporary, destination)
        else:
            os.link(temporary, destination)
    except FileExistsError as error:
        raise BackupError("destination.exists") from error
    except OSError as error:
        raise BackupError("destination.publish_error") from error
    finally:
        temporary.unlink(missing_ok=True)


def backup(source: Path, destination: Path) -> _Manifest:
    """Snapshot a prototype database and exclusively publish a V1 bundle."""
    source_path = _safe_existing_file(source, "source")
    _inspect_database(source_path)
    if destination.exists() or destination.is_symlink():
        raise BackupError("destination.exists")
    parent = _safe_parent(destination.parent)
    destination = parent / destination.name
    if source_path == destination or source_path == parent / destination.name:
        raise BackupError("path.source_destination_conflict")
    if destination.name in {"", ".", ".."}:
        raise BackupError("destination.invalid_path")
    temporary_db: Path | None = None
    temporary_bundle: Path | None = None
    source_connection: sqlite3.Connection | None = None
    target_connection: sqlite3.Connection | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".prototype-backup-db-", dir=parent, delete=False
        ) as file:
            temporary_db = Path(file.name)
        source_connection = sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True, timeout=5)
        source_connection.execute("PRAGMA query_only=ON")
        page_size = int(source_connection.execute("PRAGMA page_size").fetchone()[0])
        deadline = time.monotonic() + BACKUP_TIMEOUT_SECONDS
        callbacks = 0

        def progress(_status: int, _remaining: int, total: int) -> None:
            nonlocal callbacks
            callbacks += 1
            if total * page_size > MAX_DATABASE_BYTES:
                raise BackupError("database.byte_limit")
            if callbacks > MAX_BACKUP_CALLBACKS or time.monotonic() > deadline:
                raise BackupError("backup.work_or_timeout_limit")

        target_connection = sqlite3.connect(temporary_db)
        source_connection.backup(target_connection, pages=256, sleep=0.01, progress=progress)
        target_connection.close()
        target_connection = None
        source_connection.close()
        source_connection = None
        counts = _inspect_database(temporary_db)
        database = temporary_db.read_bytes()
        manifest: _Manifest = {
            "format": FORMAT,
            "database_bytes": len(database),
            "database_sha256": hashlib.sha256(database).hexdigest(),
            "row_counts": counts,
        }
        manifest_bytes = rfc8785.dumps(cast(JSONValue, manifest))
        if len(manifest_bytes) > MAX_MANIFEST_BYTES:
            raise BackupError("manifest.byte_limit")
        with tempfile.NamedTemporaryFile(
            prefix=".prototype-backup-", dir=parent, delete=False
        ) as file:
            temporary_bundle = Path(file.name)
            file.write(MAGIC)
            file.write(struct.pack(">I", len(manifest_bytes)))
            file.write(manifest_bytes)
            file.write(database)
            file.flush()
            os.fsync(file.fileno())
        _exclusive_publish(temporary_bundle, destination)
        temporary_bundle = None
        return manifest
    except sqlite3.Error as error:
        raise BackupError("backup.sqlite_error") from error
    finally:
        if source_connection is not None:
            source_connection.close()
        if target_connection is not None:
            target_connection.close()
        if temporary_db is not None:
            temporary_db.unlink(missing_ok=True)
        if temporary_bundle is not None:
            temporary_bundle.unlink(missing_ok=True)


def _read_bundle(bundle: Path) -> tuple[_Manifest, bytes]:
    path = _safe_existing_file(bundle, "bundle")
    if path.stat().st_size > MAX_BUNDLE_BYTES:
        raise BackupError("bundle.byte_limit")
    try:
        with path.open("rb") as file:
            raw = file.read(MAX_BUNDLE_BYTES + 1)
    except OSError as error:
        raise BackupError("bundle.read_error") from error
    prefix = len(MAGIC)
    if len(raw) > MAX_BUNDLE_BYTES:
        raise BackupError("bundle.byte_limit")
    if len(raw) < prefix + 4 or raw[:prefix] != MAGIC:
        raise BackupError("bundle.invalid_format")
    manifest_size = struct.unpack(">I", raw[prefix : prefix + 4])[0]
    if not 1 <= manifest_size <= MAX_MANIFEST_BYTES:
        raise BackupError("manifest.byte_limit")
    manifest_end = prefix + 4 + manifest_size
    try:
        parsed = parse_json(raw[prefix + 4 : manifest_end])
    except (CanonicalizationError, ValueError) as error:
        raise BackupError("manifest.invalid_json") from error
    if not isinstance(parsed, dict) or set(parsed) != {
        "format",
        "database_bytes",
        "database_sha256",
        "row_counts",
    }:
        raise BackupError("manifest.invalid")
    format_value = parsed["format"]
    database_bytes = parsed["database_bytes"]
    database_sha256 = parsed["database_sha256"]
    counts = parsed["row_counts"]
    if (
        format_value != FORMAT
        or type(database_bytes) is not int
        or type(database_sha256) is not str
        or len(database_sha256) != 64
        or any(character not in "0123456789abcdef" for character in database_sha256)
        or not 0 < database_bytes <= MAX_DATABASE_BYTES
        or not isinstance(counts, dict)
        or set(counts) != set(_TABLE_COLUMNS)
        or any(
            type(value) is not int or not 0 <= value <= MAX_DATABASE_BYTES
            for value in counts.values()
        )
    ):
        raise BackupError("manifest.invalid")
    row_counts: dict[str, int] = {}
    for key, value in counts.items():
        if not isinstance(key, str) or type(value) is not int or value < 0:
            raise BackupError("manifest.invalid")
        row_counts[key] = value
    database = raw[manifest_end:]
    if len(database) != database_bytes or len(database) > MAX_DATABASE_BYTES:
        raise BackupError("manifest.database_size_mismatch")
    if hashlib.sha256(database).hexdigest() != database_sha256:
        raise BackupError("manifest.database_hash_mismatch")
    manifest: _Manifest = {
        "format": str(format_value),
        "database_bytes": database_bytes,
        "database_sha256": database_sha256,
        "row_counts": row_counts,
    }
    return manifest, database


def restore(bundle: Path, destination: Path) -> _Manifest:
    """Verify a V1 bundle and publish its database only at a new path."""
    manifest, database = _read_bundle(bundle)
    if destination.is_symlink() or destination.exists():
        if destination.is_dir() and not destination.is_symlink():
            raise BackupError("destination.exists")
        raise BackupError("destination.exists")
    destination_is_directory = destination.suffix == ""
    if destination_is_directory:
        parent = _safe_parent(destination.parent)
        final_dir = parent / destination.name
        if final_dir.exists() or final_dir.is_symlink():
            raise BackupError("destination.exists")
        final_file = final_dir / "prototype.sqlite3"
    else:
        parent = _safe_parent(destination.parent)
        final_file = parent / destination.name
    bundle_path = Path(os.path.abspath(bundle))
    if bundle_path == final_file or (destination_is_directory and bundle_path == final_dir):
        raise BackupError("path.bundle_destination_conflict")
    temp_db: Path | None = None
    created_dir = False
    try:
        if destination_is_directory:
            final_dir.mkdir()
            created_dir = True
        with tempfile.NamedTemporaryFile(
            prefix=".prototype-restore-", dir=final_file.parent, delete=False
        ) as file:
            temp_db = Path(file.name)
            file.write(database)
            file.flush()
            os.fsync(file.fileno())
        counts = _inspect_database(temp_db)
        if counts != manifest["row_counts"]:
            raise BackupError("manifest.row_counts_mismatch")
        _exclusive_publish(temp_db, final_file)
        temp_db = None
        return manifest
    except FileExistsError as error:
        raise BackupError("destination.exists") from error
    except OSError as error:
        raise BackupError("restore.io_error") from error
    finally:
        if temp_db is not None:
            temp_db.unlink(missing_ok=True)
        if created_dir:
            with suppress(OSError):
                final_dir.rmdir()
