from __future__ import annotations

import hashlib
import sqlite3
import struct
from pathlib import Path

import pytest
import rfc8785

from crochet_ai.prototype_backup import (
    MAGIC,
    BackupError,
    backup,
    restore,
)
from crochet_ai.prototype_storage import PrototypeStore


def _seed_store(path: Path) -> tuple[PrototypeStore, dict[str, object], dict[str, object]]:
    store = PrototypeStore(path)
    project: dict[str, object] = {"project_id": "p1", "steps": [], "request": {"shape": "sphere"}}
    feedback: dict[str, object] = {"feedback_id": "f1", "project_id": "p1", "notes": "ok"}
    store.db.execute(
        "INSERT INTO projects VALUES (?, ?, ?, ?)",
        ("p1", store._dump(project), "a" * 64, "2026-10-09T00:00:00Z"),
    )
    store.db.execute("INSERT INTO sessions VALUES (?, ?, ?)", ("p1", 4, 2))
    store.db.execute(
        "INSERT INTO feedback VALUES (?, ?, ?, ?)",
        ("f1", "p1", "a" * 64, store._dump(feedback)),
    )
    return store, project, feedback


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_wal_backup_restores_projects_sessions_and_feedback(tmp_path: Path) -> None:
    source_dir = tmp_path / "live"
    store, project, feedback = _seed_store(source_dir)
    source = source_dir / "prototype.sqlite3"
    wal = Path(f"{source}-wal")
    assert wal.exists() and wal.stat().st_size > 0
    before = {path: _file_hash(path) for path in (source, wal)}
    bundle = tmp_path / "snapshot.cpbackup"
    manifest = backup(source, bundle)
    assert manifest["row_counts"] == {"projects": 1, "sessions": 1, "feedback": 1}
    assert {path: _file_hash(path) for path in (source, wal)} == before

    restored_path = tmp_path / "recovered" / "prototype.sqlite3"
    restore(bundle, restored_path.parent)
    restored = PrototypeStore(restored_path.parent)
    assert restored.get_project("p1") == project
    assert restored.db.execute("SELECT revision, cursor FROM sessions").fetchone() == (4, 2)
    assert restored.feedback("p1") == [feedback]
    restored.close()
    store.close()


def test_bundle_rejects_wrong_hash_and_existing_restore_target(tmp_path: Path) -> None:
    store, _, _ = _seed_store(tmp_path / "source")
    source = tmp_path / "source" / "prototype.sqlite3"
    bundle = tmp_path / "backup.cpbackup"
    backup(source, bundle)
    original = bundle.read_bytes()
    damaged = bytearray(original)
    damaged[-1] ^= 1
    bundle.write_bytes(damaged)
    with pytest.raises(BackupError, match="database_hash_mismatch"):
        restore(bundle, tmp_path / "new.sqlite3")
    target = tmp_path / "existing.sqlite3"
    target.write_bytes(b"keep this file")
    bundle.write_bytes(original)
    with pytest.raises(BackupError, match=r"destination\.exists"):
        restore(bundle, target)
    assert target.read_bytes() == b"keep this file"
    store.close()


def test_restore_rejects_corrupt_database_and_wrong_schema(tmp_path: Path) -> None:
    store, _, _ = _seed_store(tmp_path / "source")
    source = tmp_path / "source" / "prototype.sqlite3"
    bundle = tmp_path / "backup.cpbackup"
    backup(source, bundle)
    raw = bundle.read_bytes()
    manifest_size = struct.unpack(">I", raw[len(MAGIC) : len(MAGIC) + 4])[0]
    database_offset = len(MAGIC) + 4 + manifest_size
    corrupt_bundle = tmp_path / "corrupt.cpbackup"
    corrupted = bytearray(raw)
    corrupted[database_offset] ^= 1
    corrupt_bundle.write_bytes(corrupted)
    with pytest.raises(BackupError, match="database_hash_mismatch"):
        restore(corrupt_bundle, tmp_path / "corrupt-destination.sqlite3")

    wrong_db = tmp_path / "wrong.sqlite3"
    with sqlite3.connect(wrong_db) as connection:
        connection.execute("CREATE TABLE customer_data(value TEXT)")
    wrong_bytes = wrong_db.read_bytes()
    manifest = {
        "format": "CROCHET_PROTOTYPE_BACKUP_V1",
        "database_bytes": len(wrong_bytes),
        "database_sha256": hashlib.sha256(wrong_bytes).hexdigest(),
        "row_counts": {"projects": 0, "sessions": 0, "feedback": 0},
    }
    manifest_bytes = rfc8785.dumps(manifest)
    wrong_bundle = tmp_path / "wrong.cpbackup"
    wrong_bundle.write_bytes(
        MAGIC + struct.pack(">I", len(manifest_bytes)) + manifest_bytes + wrong_bytes
    )
    with pytest.raises(BackupError, match="unexpected_schema"):
        restore(wrong_bundle, tmp_path / "wrong-destination.sqlite3")
    store.close()


def test_rehashed_non_database_is_rejected_before_publication(tmp_path: Path) -> None:
    database = b"not a SQLite database"
    manifest = {
        "format": "CROCHET_PROTOTYPE_BACKUP_V1",
        "database_bytes": len(database),
        "database_sha256": hashlib.sha256(database).hexdigest(),
        "row_counts": {"projects": 0, "sessions": 0, "feedback": 0},
    }
    encoded = rfc8785.dumps(manifest)
    bundle = tmp_path / "forged.cpbackup"
    bundle.write_bytes(MAGIC + struct.pack(">I", len(encoded)) + encoded + database)
    destination = tmp_path / "restored.sqlite3"
    with pytest.raises(BackupError, match="sqlite_error"):
        restore(bundle, destination)
    assert not destination.exists()


def test_invalid_manifest_and_pre_copy_byte_budget_reject_without_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import crochet_ai.prototype_backup as module

    invalid = tmp_path / "invalid.cpbackup"
    invalid.write_bytes(MAGIC + struct.pack(">I", 1) + b"{")
    with pytest.raises(BackupError, match=r"manifest\.invalid_json"):
        restore(invalid, tmp_path / "bad.sqlite3")
    store, _, _ = _seed_store(tmp_path / "source")
    destination = tmp_path / "oversize.cpbackup"
    monkeypatch.setattr(module, "MAX_DATABASE_BYTES", 100)
    with pytest.raises(BackupError, match=r"database\.byte_limit"):
        backup(store.path, destination)
    assert not destination.exists()
    assert not list(tmp_path.glob(".prototype-backup*"))
    store.close()


def test_online_backup_work_exhaustion_cleans_unpublished_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import crochet_ai.prototype_backup as module

    store, _, _ = _seed_store(tmp_path / "source")
    destination = tmp_path / "limited.cpbackup"
    monkeypatch.setattr(module, "MAX_BACKUP_CALLBACKS", 0)
    with pytest.raises(BackupError, match="work_or_timeout_limit"):
        backup(store.path, destination)
    assert not destination.exists()
    assert not list(tmp_path.glob(".prototype-backup*"))
    store.close()


def test_backup_rejects_same_source_and_symlink_without_modifying_source(tmp_path: Path) -> None:
    store, _, _ = _seed_store(tmp_path / "source")
    source = tmp_path / "source" / "prototype.sqlite3"
    before = _file_hash(source)
    with pytest.raises(BackupError, match=r"destination\.exists"):
        backup(source, source)
    alias = tmp_path / "alias.sqlite3"
    try:
        alias.symlink_to(source)
    except OSError:
        store.close()
        pytest.skip("symlinks are unavailable on this host")
    with pytest.raises(BackupError, match="not_regular_file"):
        backup(alias, tmp_path / "alias.cpbackup")
    assert _file_hash(source) == before
    store.close()
