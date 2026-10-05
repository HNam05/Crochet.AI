from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from crochet_ai import calibration_store as calibration_store_module
from crochet_ai.calibration_campaign import CalibrationCampaign, CalibrationMeasurement
from crochet_ai.calibration_store import CalibrationStore, CalibrationStoreError


def campaign(identifier: str = "pilot") -> CalibrationCampaign:
    return CalibrationCampaign(
        {
            "record_version": "1.0.0",
            "campaign_id": identifier,
            "protocol_id": "CALIBRATION_TUBE_GAUGE_PILOT_V1",
            "scope": {
                "yarn_description": "cotton",
                "yarn_lot": "lot1",
                "hook_diameter_mm": 4.0,
                "tension_profile_id": "maker1",
                "fabric_state": "RELAXED_UNSTUFFED",
            },
            "plan": {
                "stitches_per_course": 12,
                "total_courses": 12,
                "exclude_start_courses": 1,
                "exclude_end_courses": 1,
                "circumference_courses": [3, 8],
                "course_span_start": 3,
                "course_span_intervals": 4,
                "repeats": 2,
            },
            "specimens": [
                {"specimen_id": f"s{i}", "role": "CALIBRATION", "fixture": "CALIBRATION_TUBE"}
                for i in range(1, 4)
            ],
            "instrument": {
                "instrument_id": "ruler",
                "resolution_mm": 0.1,
                "calibration_status": "UNKNOWN",
                "circumference_method": "FLEXIBLE_TAPE_RELAXED_PERIMETER_V1",
            },
            "artifact_bindings": {
                "design_spec_sha256": None,
                "crochet_ir_sha256": None,
                "instructions_sha256": None,
                "verification_profile_id": "verify1",
                "threshold_profile_id": "threshold1",
            },
            "software_commit": "unknown",
            "source_snapshot_sha256": "a" * 64,
        }
    )


def measurement(
    campaign_record: CalibrationCampaign,
    identifier: str = "m1",
    *,
    specimen: str = "s1",
    parent: str | None = None,
    length: float = 38.0,
) -> CalibrationMeasurement:
    plan = campaign_record.to_dict()["plan"]
    return CalibrationMeasurement(
        {
            "record_version": "1.0.0",
            "record_id": identifier,
            "campaign_sha256": campaign_record.sha256,
            "specimen_id": specimen,
            "instrument_id": "ruler",
            "observed_at": "2026-10-05T10:00:00Z",
            "circumferences": [
                {
                    "course": band,
                    "orientation_degrees": orientation,
                    "repeat_index": repeat,
                    "length_mm": length,
                }
                for band in plan["circumference_courses"]
                for orientation in (0, 90)
                for repeat in (1, 2)
            ],
            "course_spans": [
                {
                    "start_course": plan["course_span_start"],
                    "interval_count": plan["course_span_intervals"],
                    "repeat_index": repeat,
                    "length_mm": 20.0,
                }
                for repeat in (1, 2)
            ],
            "specimen_mass_g": 10.0,
            "rest_hours": 24.0,
            "stuffing_mass_g": 0,
            "treatment": "UNWASHED_UNBLOCKED",
            "deviations": [],
            "media": [],
            "supersedes_sha256": parent,
        },
        campaign_record,
    )


def test_reopen_durability_and_idempotency(tmp_path: Path) -> None:
    path = tmp_path / "calibration.sqlite3"
    frozen = campaign()
    record = measurement(frozen)
    with CalibrationStore(path) as store:
        assert store.register_campaign(frozen) == frozen.sha256
        assert store.register_campaign(frozen) == frozen.sha256
        assert store.add_measurement(record) == record.sha256
        assert store.add_measurement(record) == record.sha256
    with CalibrationStore(path) as store:
        assert store.get_campaign(frozen.sha256) == frozen
        assert store.get_measurement(record.sha256) == record
        assert store.list_measurements(frozen.sha256) == (record,)


@pytest.mark.parametrize(
    "column,value", [("specimen_id", "s2"), ("record_id", "wrong"), ("supersedes_sha256", "SELF")]
)
def test_sql_metadata_cannot_disagree_with_hashed_record(
    tmp_path: Path, column: str, value: str
) -> None:
    frozen = campaign()
    record = measurement(frozen)
    with CalibrationStore(tmp_path / "db") as store:
        store.register_campaign(frozen)
        store.add_measurement(record)
        value = record.sha256 if value == "SELF" else value
        store.db.execute(
            f"UPDATE measurements SET {column}=? WHERE measurement_sha256=?", (value, record.sha256)
        )
        with pytest.raises(CalibrationStoreError, match="corrupt_measurement_binding"):
            store.get_measurement(record.sha256)


def test_campaign_identity_is_also_bound_to_sql_metadata(tmp_path: Path) -> None:
    frozen = campaign()
    with CalibrationStore(tmp_path / "db") as store:
        store.register_campaign(frozen)
        store.db.execute("UPDATE campaigns SET campaign_id='changed'")
        with pytest.raises(CalibrationStoreError, match="corrupt_campaign_binding"):
            store.get_campaign(frozen.sha256)


def test_forged_campaign_hash_is_rejected_before_persistence(tmp_path: Path) -> None:
    frozen = campaign()
    object.__setattr__(frozen, "sha256", "b" * 64)
    with CalibrationStore(tmp_path / "db") as store:
        with pytest.raises(CalibrationStoreError, match="campaign_hash_mismatch"):
            store.register_campaign(frozen)
        assert store.db.execute("SELECT count(*) FROM campaigns").fetchone()[0] == 0


def test_conflicting_ids_and_unregistered_campaign_fail(tmp_path: Path) -> None:
    first = campaign()
    changed = campaign()
    changed_value = changed.to_dict()
    changed_value["software_commit"] = "different"
    changed = CalibrationCampaign(changed_value)
    with CalibrationStore(tmp_path / "db") as store:
        with pytest.raises(CalibrationStoreError, match="unregistered_campaign"):
            store.add_measurement(measurement(first))
        store.register_campaign(first)
        with pytest.raises(CalibrationStoreError, match="campaign_id_conflict"):
            store.register_campaign(changed)
        original = measurement(first)
        store.add_measurement(original)
        with pytest.raises(CalibrationStoreError, match="record_id_conflict"):
            store.add_measurement(measurement(first, length=39.0))


def test_correction_chain_preserves_all_and_returns_active(tmp_path: Path) -> None:
    frozen = campaign()
    first = measurement(frozen)
    correction = measurement(frozen, "m2", parent=first.sha256, length=39.0)
    with CalibrationStore(tmp_path / "db") as store:
        store.register_campaign(frozen)
        store.add_measurement(first)
        store.add_measurement(correction)
        assert {item.sha256 for item in store.list_measurements(frozen.sha256)} == {
            first.sha256,
            correction.sha256,
        }
        assert store.active_measurements(frozen.sha256) == (correction,)


def test_correction_parent_binding_and_forks_rejected(tmp_path: Path) -> None:
    frozen = campaign()
    first = measurement(frozen)
    second = measurement(frozen, "m2", parent=first.sha256, length=39.0)
    fork = measurement(frozen, "m3", parent=first.sha256, length=40.0)
    with CalibrationStore(tmp_path / "db") as store:
        store.register_campaign(frozen)
        store.add_measurement(first)
        store.add_measurement(second)
        with pytest.raises(CalibrationStoreError, match="correction_fork"):
            store.add_measurement(fork)
        wrong_specimen = measurement(frozen, "m4", specimen="s2", parent=first.sha256)
        with pytest.raises(CalibrationStoreError, match="correction_binding"):
            store.add_measurement(wrong_specimen)


def test_concurrent_campaign_registration_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "db"
    frozen = campaign()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _register(path, frozen), range(2)))
    assert results == [frozen.sha256, frozen.sha256]


def _register(path: Path, value: CalibrationCampaign) -> str:
    with CalibrationStore(path) as store:
        return store.register_campaign(value)


def test_corrupt_payload_fails_closed_and_insert_rolls_back(tmp_path: Path) -> None:
    path = tmp_path / "db"
    frozen = campaign()
    record = measurement(frozen)
    with CalibrationStore(path) as store:
        store.register_campaign(frozen)
        store.add_measurement(record)
    db = sqlite3.connect(path)
    db.execute("UPDATE measurements SET payload=?", (b"{}",))
    db.commit()
    db.close()
    with CalibrationStore(path) as store:
        with pytest.raises(CalibrationStoreError, match="corrupt_measurement"):
            store.get_measurement(record.sha256)
        with pytest.raises(RuntimeError), store._transaction():
            store.db.execute("INSERT INTO campaigns VALUES(?,?,?)", ("x", "x", b"{}"))
            raise RuntimeError("rollback")
        count = store.db.execute("SELECT count(*) FROM campaigns WHERE campaign_id='x'").fetchone()[
            0
        ]
        assert count == 0


def test_unrelated_database_rejected_without_modification(tmp_path: Path) -> None:
    path = tmp_path / "unrelated.sqlite3"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE customer_data (value TEXT)")
    db.execute("INSERT INTO customer_data VALUES('preserve me')")
    db.commit()
    db.close()
    before = path.read_bytes()
    with pytest.raises(CalibrationStoreError, match="unrecognized_database"):
        CalibrationStore(path)
    assert path.read_bytes() == before
    check = sqlite3.connect(path)
    assert check.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    assert check.execute("SELECT value FROM customer_data").fetchone()[0] == "preserve me"
    check.close()


def test_unrelated_version_one_database_rejected(tmp_path: Path) -> None:
    path = tmp_path / "unrelated_v1.sqlite3"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE other (value TEXT)")
    db.execute("PRAGMA user_version=1")
    db.commit()
    db.close()
    before = path.read_bytes()
    with pytest.raises(CalibrationStoreError, match="unrecognized_database"):
        CalibrationStore(path)
    assert path.read_bytes() == before


def test_store_identity_with_wrong_version_one_schema_rejected(tmp_path: Path) -> None:
    path = tmp_path / "wrong_schema.sqlite3"
    db = sqlite3.connect(path)
    db.execute("PRAGMA application_id=1128352817")
    db.execute("PRAGMA user_version=1")
    db.execute("CREATE TABLE campaigns (wrong TEXT)")
    db.commit()
    db.close()
    before = path.read_bytes()
    with pytest.raises(CalibrationStoreError, match="schema_mismatch"):
        CalibrationStore(path)
    assert path.read_bytes() == before


def test_capacity_boundaries_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first_campaign = campaign("first")
    second_campaign = campaign("second")
    path = tmp_path / "db"
    monkeypatch.setattr(calibration_store_module, "MAX_CAMPAIGNS", 1)
    with CalibrationStore(path) as store:
        store.register_campaign(first_campaign)
        with pytest.raises(CalibrationStoreError, match="campaign_capacity"):
            store.register_campaign(second_campaign)

    monkeypatch.setattr(calibration_store_module, "MAX_CAMPAIGNS", 100)
    monkeypatch.setattr(calibration_store_module, "MAX_MEASUREMENTS", 1)
    with CalibrationStore(path) as store:
        store.add_measurement(measurement(first_campaign, "one"))
        with pytest.raises(CalibrationStoreError, match="measurement_capacity"):
            store.add_measurement(measurement(first_campaign, "two", specimen="s2"))

    monkeypatch.setattr(calibration_store_module, "MAX_MEASUREMENTS", 10_000)
    monkeypatch.setattr(calibration_store_module, "MAX_TOTAL_PAYLOAD_BYTES", 1)
    with (
        CalibrationStore(tmp_path / "aggregate.sqlite3") as store,
        pytest.raises(CalibrationStoreError, match="payload_capacity"),
    ):
        store.register_campaign(campaign("aggregate"))
    monkeypatch.setattr(calibration_store_module, "MAX_TOTAL_PAYLOAD_BYTES", 64 * 1024 * 1024)
    monkeypatch.setattr(calibration_store_module, "MAX_RECORD_BYTES", 1)
    with (
        CalibrationStore(tmp_path / "record.sqlite3") as store,
        pytest.raises(CalibrationStoreError, match="record_capacity"),
    ):
        store.register_campaign(campaign("record"))


def test_duplicate_active_specimen_is_ambiguous(tmp_path: Path) -> None:
    frozen = campaign()
    first = measurement(frozen, "m1")
    duplicate = measurement(frozen, "m2", length=39.0)
    with CalibrationStore(tmp_path / "db") as store:
        store.register_campaign(frozen)
        store.add_measurement(first)
        store.add_measurement(duplicate)
        with pytest.raises(CalibrationStoreError, match="ambiguous_active_specimen"):
            store.active_measurements(frozen.sha256)


def test_measurement_re_admission_checks_persisted_campaign_and_hash(
    tmp_path: Path,
) -> None:
    original = campaign("original")
    other = campaign("other")
    record = measurement(original)
    with CalibrationStore(tmp_path / "db") as store:
        store.register_campaign(other)
        with pytest.raises(CalibrationStoreError, match="unregistered_campaign"):
            store.add_measurement(record)
        store.register_campaign(original)
        object.__setattr__(record, "sha256", "0" * 64)
        with pytest.raises(CalibrationStoreError, match="measurement_hash_mismatch"):
            store.add_measurement(record)


@pytest.mark.parametrize(
    "definition",
    [
        "CREATE UNIQUE INDEX one_successor_per_measurement ON measurements(record_id)",
        "CREATE UNIQUE INDEX one_successor_per_measurement ON measurements(supersedes_sha256) "
        "WHERE supersedes_sha256 IS NULL",
    ],
)
def test_reopen_rejects_mutated_correction_index(tmp_path: Path, definition: str) -> None:
    path = tmp_path / "db"
    with CalibrationStore(path):
        pass
    with sqlite3.connect(path) as connection:
        connection.execute("DROP INDEX one_successor_per_measurement")
        connection.execute(definition)
    with pytest.raises(CalibrationStoreError, match="schema_mismatch"):
        CalibrationStore(path)


@pytest.mark.parametrize(
    "campaign_columns",
    [
        "campaign_sha256 TEXT, campaign_id TEXT NOT NULL UNIQUE, payload BLOB NOT NULL",
        "campaign_sha256 TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, payload BLOB NOT NULL",
        "campaign_sha256 TEXT PRIMARY KEY, campaign_id TEXT NOT NULL UNIQUE, payload TEXT NOT NULL",
        "campaign_id TEXT NOT NULL UNIQUE, campaign_sha256 TEXT PRIMARY KEY, payload BLOB NOT NULL",
    ],
)
def test_recognized_version_still_rejects_wrong_identity_constraints(
    tmp_path: Path, campaign_columns: str
) -> None:
    path = tmp_path / "db"
    with sqlite3.connect(path) as connection:
        connection.execute(f"CREATE TABLE campaigns ({campaign_columns})")
        connection.execute("""CREATE TABLE measurements (
            measurement_sha256 TEXT PRIMARY KEY,
            record_id TEXT NOT NULL UNIQUE,
            campaign_sha256 TEXT NOT NULL REFERENCES campaigns(campaign_sha256),
            specimen_id TEXT NOT NULL,
            supersedes_sha256 TEXT REFERENCES measurements(measurement_sha256),
            payload BLOB NOT NULL
        )""")
        connection.execute(
            "CREATE UNIQUE INDEX one_successor_per_measurement "
            "ON measurements(supersedes_sha256) WHERE supersedes_sha256 IS NOT NULL"
        )
        connection.execute(f"PRAGMA application_id={calibration_store_module.APPLICATION_ID}")
        connection.execute("PRAGMA user_version=1")
    with pytest.raises(CalibrationStoreError, match="schema_mismatch"):
        CalibrationStore(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
