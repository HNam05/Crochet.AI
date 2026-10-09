"""Append-only local review admission for calibration and physical evidence.

Stored hashes prove content integrity only. Reviewer IDs are allowlist-checked
assertions supplied by the local caller; they are not cryptographic identities.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal, NoReturn

import rfc8785

from .calibration_campaign import CalibrationCampaign, CalibrationError
from .canonical import CanonicalProfile, canonical_hash, validate_ijson
from .validation import SemanticValidator

PROFILE = "CALIBRATION_PHYSICAL_REVIEW_REGISTRY_V1"
RECORD_DOMAIN = b"Crochet.AI\0CALIBRATION_PHYSICAL_REVIEW_RECORD_V1\0"
ATTESTATION_DOMAIN = b"Crochet.AI\0CALIBRATION_REVIEW_ATTESTATION_V1\0"
SPECIMEN_DOMAIN = b"Crochet.AI\0PHYSICAL_SPECIMEN_EVIDENCE_V1\0"
APPLICATION_ID = 0x43525031
MAX_RECORD_BYTES = 2_000_000
MAX_SPECIMENS = 64
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_CALIBRATION_CHECKS = frozenset({"effective_stitch_pitch_mm", "effective_course_pitch_mm"})
_BINDING_KEYS = frozenset(
    {
        "software_commit",
        "source_snapshot_sha256",
        "campaign_sha256",
        "design_spec_sha256",
        "crochet_ir_sha256",
        "material_profile_sha256",
        "instructions_sha256",
        "fixture_id",
        "fixture_profile_id",
        "scenario_id",
        "loading_recipe_sha256",
        "verification_profile_id",
        "threshold_profile_id",
    }
)
_FIXTURE_CHECKS = {
    "CALIBRATION_TUBE": _CALIBRATION_CHECKS,
    "SPHERE": frozenset({"diameters", "closure", "silhouettes"}),
    "HOURGLASS": frozenset({"cross_sections", "waist", "silhouettes"}),
    "Y_BRANCH": frozenset({"branch_geometry", "openings", "construction_trace"}),
}
_FIXTURE_PROFILES = {
    "CALIBRATION_TUBE": "CALIBRATION_TUBE_GAUGE_PILOT_V1",
    "SPHERE": "PHYSICAL_SPHERE_REVIEW_V1",
    "HOURGLASS": "PHYSICAL_HOURGLASS_REVIEW_V1",
    "Y_BRANCH": "PHYSICAL_Y_BRANCH_REVIEW_V1",
}


class CalibrationRegistryError(ValueError):
    """Invalid review input, untrusted approval, conflicting record, or corrupt store."""


def _reject(code: str) -> NoReturn:
    raise CalibrationRegistryError(code)


def _object(value: object, expected: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        _reject(f"registry.{name}_fields")
    return value


def _safe_id(value: object, name: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        _reject(f"registry.{name}_id")
    return value


def _hash(value: object, name: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        _reject(f"registry.{name}_sha256")
    return value


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _reject(f"registry.{name}_number")
    result = float(value)
    if not math.isfinite(result):
        _reject(f"registry.{name}_finite")
    return result


def _timestamp(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _reject(f"registry.{name}_timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise CalibrationRegistryError(f"registry.{name}_timestamp") from error
    if parsed.tzinfo is None or "T" not in value:
        _reject(f"registry.{name}_timezone")
    return value


def _digest(domain: bytes, value: Mapping[str, Any]) -> str:
    try:
        payload = rfc8785.dumps(dict(value))
    except (TypeError, ValueError) as error:
        raise CalibrationRegistryError("registry.canonicalization") from error
    return sha256(domain + payload).hexdigest()


def _check_path(path: Path) -> Path:
    raw = Path(path)
    if ".." in raw.parts:
        _reject("registry.path_traversal")
    absolute = raw if raw.is_absolute() else Path.cwd() / raw
    absolute = Path(absolute.anchor, *absolute.parts[1:])
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            _reject("registry.symlink_path")
    if absolute.exists() and not absolute.is_file():
        _reject("registry.path_not_file")
    if not absolute.parent.is_dir():
        _reject("registry.parent_missing")
    return absolute


def _validate_source_artifacts(record: dict[str, Any], bindings: dict[str, Any]) -> None:
    artifacts = _object(
        record["source_artifacts"],
        {"design_spec", "material_profile", "crochet_ir"},
        "source_artifacts",
    )
    design = artifacts["design_spec"]
    material = artifacts["material_profile"]
    ir = artifacts["crochet_ir"]
    for role, artifact in artifacts.items():
        if not isinstance(artifact, dict) or set(artifact) != {"payload", "sha256"}:
            _reject(f"registry.{role}_artifact_shape")
        _hash(artifact["sha256"], f"{role}_artifact")
        if not isinstance(artifact["payload"], dict):
            _reject(f"registry.{role}_artifact_payload")
    if bindings["design_spec_sha256"] != design["sha256"]:
        _reject("registry.design_binding")
    if bindings["material_profile_sha256"] != material["sha256"]:
        _reject("registry.material_binding")
    if bindings["crochet_ir_sha256"] != ir["sha256"]:
        _reject("registry.ir_binding")
    material_value = material["payload"]
    design_value = design["payload"]
    if not isinstance(material_value.get("profile_id"), str) or not isinstance(
        design_value.get("design_spec_id"), str
    ):
        _reject("registry.source_identity")
    validator = SemanticValidator(
        material_profiles={material_value["profile_id"]: material_value},
        design_specs={design_value["design_spec_id"]: design_value},
    )
    profiles = {
        "design_spec": CanonicalProfile.DESIGN_SPEC,
        "material_profile": CanonicalProfile.MATERIAL_PROFILE,
        "crochet_ir": CanonicalProfile.CROCHET_IR,
    }
    for role, artifact in artifacts.items():
        try:
            computed = canonical_hash(artifact["payload"], profiles[role], validator=validator)
        except (ValueError, TypeError) as error:
            raise CalibrationRegistryError(f"registry.{role}_semantic_validation") from error
        if computed != artifact["sha256"]:
            _reject(f"registry.{role}_digest_mismatch")


def _validate_record(value: object) -> tuple[dict[str, Any], str]:
    if not isinstance(value, dict):
        _reject("registry.record_object")
    try:
        validate_ijson(value)
    except ValueError as error:
        raise CalibrationRegistryError("registry.record_ijson") from error
    record = _object(
        value,
        {
            "profile",
            "record_version",
            "record_id",
            "evidence_class",
            "claim",
            "bindings",
            "campaign",
            "source_artifacts",
            "specimens",
            "required_checks",
        },
        "record",
    )
    if record["profile"] != PROFILE or record["record_version"] != "1.0.0":
        _reject("registry.record_version")
    _safe_id(record["record_id"], "record")
    if not isinstance(record["evidence_class"], str) or record["evidence_class"] not in {
        "MEASURED_EVIDENCE",
        "SYNTHETIC_TEST_ONLY",
    }:
        _reject("registry.evidence_class")
    if not isinstance(record["claim"], str) or record["claim"] not in {
        "CALIBRATED",
        "PHYSICALLY_VERIFIED",
        "FAILED_PHYSICAL_TRIAL",
    }:
        _reject("registry.claim")
    bindings = _object(
        record["bindings"],
        {
            "software_commit",
            "source_snapshot_sha256",
            "campaign_sha256",
            "design_spec_sha256",
            "crochet_ir_sha256",
            "material_profile_sha256",
            "instructions_sha256",
            "fixture_id",
            "fixture_profile_id",
            "scenario_id",
            "loading_recipe_sha256",
            "verification_profile_id",
            "threshold_profile_id",
        },
        "bindings",
    )
    if (
        not isinstance(bindings["software_commit"], str)
        or _COMMIT.fullmatch(bindings["software_commit"]) is None
    ):
        _reject("registry.software_commit")
    for key in (
        "source_snapshot_sha256",
        "campaign_sha256",
        "design_spec_sha256",
        "crochet_ir_sha256",
        "material_profile_sha256",
        "instructions_sha256",
        "loading_recipe_sha256",
    ):
        _hash(bindings[key], key)
    for key in (
        "fixture_id",
        "fixture_profile_id",
        "scenario_id",
        "verification_profile_id",
        "threshold_profile_id",
    ):
        _safe_id(bindings[key], key)
    campaign_record = _object(record["campaign"], {"payload", "sha256"}, "campaign")
    _hash(campaign_record["sha256"], "campaign")
    try:
        campaign = CalibrationCampaign(campaign_record["payload"])
    except (CalibrationError, TypeError, ValueError) as error:
        raise CalibrationRegistryError("registry.campaign_validation") from error
    if (
        campaign.sha256 != campaign_record["sha256"]
        or bindings["campaign_sha256"] != campaign.sha256
    ):
        _reject("registry.campaign_digest_mismatch")
    campaign_value = campaign.to_dict()
    campaign_bindings = campaign_value["artifact_bindings"]
    if (
        campaign_value["software_commit"] != bindings["software_commit"]
        or campaign_value["source_snapshot_sha256"] != bindings["source_snapshot_sha256"]
        or campaign_value["campaign_id"] != bindings["scenario_id"]
        or campaign_bindings["design_spec_sha256"] != bindings["design_spec_sha256"]
        or campaign_bindings["crochet_ir_sha256"] != bindings["crochet_ir_sha256"]
        or campaign_bindings["instructions_sha256"] != bindings["instructions_sha256"]
        or campaign_bindings["verification_profile_id"] != bindings["verification_profile_id"]
        or campaign_bindings["threshold_profile_id"] != bindings["threshold_profile_id"]
    ):
        _reject("registry.campaign_scope_binding")
    assignments = {
        item["specimen_id"]: (item["role"], item["fixture"]) for item in campaign_value["specimens"]
    }
    _validate_source_artifacts(record, bindings)
    campaign_scope = campaign_value["scope"]
    profile_value = record["source_artifacts"]["material_profile"]["payload"]
    conditions = profile_value["calibration_responses"][0]["measurement_conditions"]
    if (
        profile_value["yarn"]["description"] != campaign_scope["yarn_description"]
        or profile_value["hook_diameter_mm"] != campaign_scope["hook_diameter_mm"]
        or conditions["tension_profile_id"] != campaign_scope["tension_profile_id"]
        or conditions["fabric_state"] != campaign_scope["fabric_state"]
    ):
        _reject("registry.campaign_material_scope")
    checks = record["required_checks"]
    if (
        not isinstance(checks, list)
        or not checks
        or any(not isinstance(item, str) for item in checks)
    ):
        _reject("registry.required_checks")
    if len(set(checks)) != len(checks):
        _reject("registry.duplicate_check")
    specimens = record["specimens"]
    if not isinstance(specimens, list) or len(specimens) > MAX_SPECIMENS:
        _reject("registry.specimens")
    seen: set[str] = set()
    calibrations = 0
    holdouts = 0
    holdout_passes = 0
    failed_trial = False
    for specimen in specimens:
        specimen = _object(
            specimen,
            {
                "specimen_id",
                "role",
                "fixture_family",
                "observed_at",
                "outcome",
                "measurements",
                "checks",
                "media",
                "evidence_sha256",
            },
            "specimen",
        )
        sid = _safe_id(specimen["specimen_id"], "specimen")
        if sid in seen:
            _reject("registry.duplicate_specimen")
        seen.add(sid)
        role = specimen["role"]
        family = specimen["fixture_family"]
        if (
            not isinstance(role, str)
            or role not in {"CALIBRATION", "HOLDOUT"}
            or not isinstance(family, str)
            or family not in _FIXTURE_CHECKS
        ):
            _reject("registry.specimen_role_or_fixture")
        campaign_assignment = assignments.get(sid)
        expected_role = "CALIBRATION" if role == "CALIBRATION" else "HOLDOUT"
        if campaign_assignment != (expected_role, family):
            _reject("registry.campaign_specimen_binding")
        evidence_digest = _hash(specimen["evidence_sha256"], "specimen_evidence")
        evidence_payload = {
            key: child for key, child in specimen.items() if key != "evidence_sha256"
        }
        if _digest(SPECIMEN_DOMAIN, evidence_payload) != evidence_digest:
            _reject("registry.specimen_evidence_digest")
        _timestamp(specimen["observed_at"], "specimen.observed_at")
        if not isinstance(specimen["measurements"], list) or not specimen["measurements"]:
            _reject("registry.measurements")
        measured_names: set[str] = set()
        for measurement in specimen["measurements"]:
            measurement = _object(
                measurement, {"metric_id", "value", "units", "method_id"}, "measurement"
            )
            metric_id = _safe_id(measurement["metric_id"], "metric")
            if metric_id in measured_names:
                _reject("registry.duplicate_measurement")
            measured_names.add(metric_id)
            number = _number(measurement["value"], "measurement.value")
            units = _safe_id(measurement["units"], "measurement.units")
            if measurement["metric_id"].endswith("_mm") and units != "mm":
                _reject("registry.measurement_units")
            if metric_id.endswith("_count") and (
                units not in {"1", "count"}
                or type(measurement["value"]) is not int
                or not 0 < measurement["value"] <= 9_007_199_254_740_991
            ):
                _reject("registry.measurement_count")
            if (
                role == "CALIBRATION"
                and measurement["metric_id"] in _CALIBRATION_CHECKS
                and number <= 0
            ):
                _reject("registry.calibration_measurement_positive")
            _safe_id(measurement["method_id"], "measurement.method")
        media = specimen["media"]
        if not isinstance(media, list):
            _reject("registry.media")
        for item in media:
            item = _object(item, {"sha256", "view", "privacy_status", "license_status"}, "media")
            _hash(item["sha256"], "media")
            for key in ("view", "privacy_status", "license_status"):
                _safe_id(item[key], f"media.{key}")
        specimen_checks = specimen["checks"]
        if not isinstance(specimen_checks, dict) or any(
            not isinstance(key, str)
            or key not in _FIXTURE_CHECKS[family]
            or not isinstance(value, str)
            or value not in {"PASS", "FAIL", "NOT_RUN"}
            for key, value in specimen_checks.items()
        ):
            _reject("registry.specimen_checks")
        if role == "CALIBRATION":
            if family != "CALIBRATION_TUBE":
                _reject("registry.calibration_fixture_identifiability")
            if not _CALIBRATION_CHECKS.issubset(measured_names):
                _reject("registry.calibration_measurements")
            if specimen["outcome"] != "PASS":
                _reject("registry.calibration_specimen_not_passed")
            calibrations += 1
        else:
            holdouts += 1
            if set(specimen_checks) != set(checks):
                _reject("registry.holdout_check_coverage")
            if specimen["outcome"] == "PASS" and all(
                value == "PASS" for value in specimen_checks.values()
            ):
                holdout_passes += 1
        if not isinstance(specimen["outcome"], str) or specimen["outcome"] not in {
            "PASS",
            "FAIL",
            "NOT_RUN",
        }:
            _reject("registry.specimen_outcome")
        if specimen["outcome"] == "FAIL":
            failed_trial = True
        if (
            specimen["outcome"] == "FAIL"
            and role == "HOLDOUT"
            and "FAIL" not in specimen_checks.values()
        ):
            _reject("registry.failed_trial_check")
    if calibrations < 3 or holdouts < 1:
        _reject("registry.independent_calibration_and_holdout_required")
    if seen != set(assignments):
        _reject("registry.campaign_specimen_coverage")
    if not checks or any(
        set(checks) != _FIXTURE_CHECKS[item["fixture_family"]]
        for item in specimens
        if item["role"] == "HOLDOUT"
    ):
        _reject("registry.unsupported_claim_capability")
    claim = record["claim"]
    if record["evidence_class"] == "MEASURED_EVIDENCE" and claim in {
        "CALIBRATED",
        "PHYSICALLY_VERIFIED",
    }:
        _check_profile_matches_tubes(record, specimens)
    if claim == "CALIBRATED" and (
        bindings["fixture_profile_id"] != "CALIBRATION_TUBE_GAUGE_PILOT_V1"
        or any(item["fixture_family"] != "CALIBRATION_TUBE" for item in specimens)
    ):
        _reject("registry.calibration_profile_scope")
    if claim == "PHYSICALLY_VERIFIED":
        holdout_families = {
            item["fixture_family"] for item in specimens if item["role"] == "HOLDOUT"
        }
        if (
            holdout_passes != holdouts
            or len(holdout_families) != 1
            or bindings["fixture_profile_id"] != _FIXTURE_PROFILES[next(iter(holdout_families))]
        ):
            _reject("registry.physical_holdout_incomplete_or_scope_mismatch")
    if claim == "FAILED_PHYSICAL_TRIAL" and not failed_trial:
        _reject("registry.failed_trial_missing")
    digest = _digest(RECORD_DOMAIN, record)
    return record, digest


def _check_profile_matches_tubes(record: dict[str, Any], specimens: list[Any]) -> None:
    material = record["source_artifacts"]["material_profile"]["payload"]
    responses = material["calibration_responses"]
    if len(responses) != 1:
        _reject("registry.calibration_response_scope")
    response = responses[0]
    conditions = response["measurement_conditions"]
    if (
        conditions["canonical_stitch_type"] != "SINGLE_CROCHET"
        or conditions["course_mode"] != "CYCLIC"
        or response["uncertainty"]["basis"] != "REPLICATE_COMBINED_STANDARD_UNCERTAINTY"
    ):
        _reject("registry.calibration_identifiability")
    calibration = {item["specimen_id"]: item for item in specimens if item["role"] == "CALIBRATION"}
    observations = response["observations"]
    if len(observations) != len(calibration) or len(observations) < 3:
        _reject("registry.profile_observation_coverage")
    used: set[str] = set()
    for observation in observations:
        specimen_id = observation["specimen_id"]
        if specimen_id not in calibration or specimen_id in used:
            _reject("registry.profile_specimen_binding")
        used.add(specimen_id)
        readings = {
            reading["metric_id"]: reading for reading in calibration[specimen_id]["measurements"]
        }
        for name in (
            "stitch_span_length_mm",
            "stitch_span_count",
            "course_span_length_mm",
            "course_span_count",
        ):
            if name not in readings:
                _reject("registry.profile_measurement_binding")
        for obs_key, metric in (
            ("stitch_span_length_mm", "stitch_span_length_mm"),
            ("stitch_span_count", "stitch_span_count"),
            ("course_span_length_mm", "course_span_length_mm"),
            ("course_span_count", "course_span_count"),
        ):
            if observation[obs_key] != readings[metric]["value"]:
                _reject("registry.profile_measurement_mismatch")
        for family in ("stitch", "course"):
            metric = f"effective_{family}_pitch_mm"
            expected = observation[f"{family}_span_length_mm"] / observation[f"{family}_span_count"]
            if readings[metric]["value"] != expected:
                _reject("registry.profile_pitch_measurement_mismatch")


class CalibrationReviewRegistry:
    """Local append-only registry; caller configures allowlisted reviewer IDs."""

    def __init__(self, path: Path, *, trusted_reviewers: Sequence[str]) -> None:
        if not trusted_reviewers or any(
            not isinstance(item, str) or _ID.fullmatch(item) is None for item in trusted_reviewers
        ):
            _reject("registry.trusted_reviewer_configuration")
        if len(set(trusted_reviewers)) != len(trusted_reviewers):
            _reject("registry.duplicate_trusted_reviewer")
        self.path = _check_path(path)
        self.trusted_reviewers = frozenset(trusted_reviewers)
        try:
            self.db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
            self.db.execute("PRAGMA foreign_keys=ON")
            self.db.execute("PRAGMA busy_timeout=5000")
            self.db.execute("PRAGMA synchronous=FULL")
            with self._transaction():
                version = self.db.execute("PRAGMA user_version").fetchone()[0]
                app_id = self.db.execute("PRAGMA application_id").fetchone()[0]
                if version == 0:
                    tables = self.db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name NOT LIKE 'sqlite_%'"
                    ).fetchall()
                    if app_id != 0 or tables:
                        _reject("registry.unrecognized_database")
                    self.db.execute(
                        "CREATE TABLE records ("
                        "record_sha256 TEXT PRIMARY KEY, "
                        "record_id TEXT NOT NULL UNIQUE, "
                        "payload BLOB NOT NULL)"
                    )
                    self.db.execute(
                        "CREATE TABLE attestations ("
                        "attestation_sha256 TEXT PRIMARY KEY, "
                        "record_sha256 TEXT NOT NULL REFERENCES records(record_sha256), "
                        "reviewer_id TEXT NOT NULL, "
                        "decision TEXT NOT NULL CHECK(decision IN ('APPROVE','REJECT')), "
                        "payload BLOB NOT NULL, UNIQUE(record_sha256, reviewer_id))"
                    )
                    self.db.execute(f"PRAGMA application_id={APPLICATION_ID}")
                    self.db.execute("PRAGMA user_version=1")
                elif version != 1 or app_id != APPLICATION_ID:
                    _reject("registry.unrecognized_database")
                self._check_schema()
        except sqlite3.Error as error:
            if hasattr(self, "db"):
                self.db.close()
            raise CalibrationRegistryError("registry.unrecognized_database") from error
        except BaseException:
            if hasattr(self, "db"):
                self.db.close()
            raise

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def _check_schema(self) -> None:
        expected = {
            "records": ("record_sha256", "record_id", "payload"),
            "attestations": (
                "attestation_sha256",
                "record_sha256",
                "reviewer_id",
                "decision",
                "payload",
            ),
        }
        tables = {
            row[0]
            for row in self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if tables != set(expected):
            _reject("registry.schema_mismatch")
        for table, columns in expected.items():
            rows = self.db.execute(f"PRAGMA table_info({table})").fetchall()
            if tuple(row[1] for row in rows) != columns:
                _reject("registry.schema_mismatch")
            primary = "record_sha256" if table == "records" else "attestation_sha256"
            for row in rows:
                expected_type = "BLOB" if row[1] == "payload" else "TEXT"
                if row[2] != expected_type or row[5] != int(row[1] == primary):
                    _reject("registry.schema_mismatch")
        unique_by_table = {
            table: {
                tuple(
                    item[2]
                    for item in self.db.execute(
                        "SELECT seqno,cid,name FROM pragma_index_info(?) ORDER BY seqno",
                        (row[1],),
                    )
                )
                for row in self.db.execute(f"PRAGMA index_list({table})").fetchall()
                if row[2] and not row[4]
            }
            for table in expected
        }
        if unique_by_table != {
            "records": {("record_sha256",), ("record_id",)},
            "attestations": {("attestation_sha256",), ("record_sha256", "reviewer_id")},
        }:
            _reject("registry.schema_mismatch")
        foreign_keys = {
            (row[2], row[3], row[4])
            for row in self.db.execute("PRAGMA foreign_key_list(attestations)")
        }
        if foreign_keys != {("records", "record_sha256", "record_sha256")}:
            _reject("registry.schema_mismatch")

    @staticmethod
    def _bytes(payload: Mapping[str, Any]) -> bytes:
        data = rfc8785.dumps(dict(payload))
        if len(data) > MAX_RECORD_BYTES:
            _reject("registry.record_capacity")
        return data

    def register(self, value: object) -> dict[str, str]:
        record, digest = _validate_record(value)
        payload = self._bytes(record)
        with self._transaction():
            prior = self.db.execute(
                "SELECT record_sha256 FROM records WHERE record_id=?", (record["record_id"],)
            ).fetchone()
            if prior:
                if prior[0] != digest:
                    _reject("registry.record_id_conflict")
                self._read_record(digest)
                return {"record_sha256": digest, "state": "PENDING_REVIEW"}
            count = self.db.execute("SELECT count(*) FROM records").fetchone()[0]
            total = self.db.execute(
                "SELECT coalesce(sum(length(payload)),0) FROM records"
            ).fetchone()[0]
            if count >= 2_000 or total + len(payload) > 64 * 1024 * 1024:
                _reject("registry.capacity")
            self.db.execute(
                "INSERT INTO records VALUES(?,?,?)", (digest, record["record_id"], payload)
            )
        return {"record_sha256": digest, "state": "PENDING_REVIEW"}

    def _read_record(self, digest: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT payload,record_id FROM records WHERE record_sha256=?", (digest,)
        ).fetchone()
        if row is None:
            return None
        import json

        try:
            value = json.loads(bytes(row[0]).decode("utf-8"))
            checked, computed = _validate_record(value)
        except (UnicodeDecodeError, ValueError, TypeError) as error:
            raise CalibrationRegistryError("registry.corrupt_record") from error
        if checked["record_id"] != row[1] or computed != digest:
            _reject("registry.corrupt_record_hash")
        return checked

    def approve(
        self,
        record_sha256: str,
        *,
        reviewer_id: str,
        decision: Literal["APPROVE", "REJECT"],
        note: str,
        attested_at: str,
        expected_record_sha256: str,
    ) -> str:
        digest = _hash(record_sha256, "record")
        reviewer = _safe_id(reviewer_id, "reviewer")
        if reviewer not in self.trusted_reviewers:
            _reject("registry.untrusted_reviewer")
        if decision not in {"APPROVE", "REJECT"} or not isinstance(note, str) or not note.strip():
            _reject("registry.invalid_attestation")
        _timestamp(attested_at, "attestation")
        if expected_record_sha256 != digest:
            _reject("registry.review_binding_mismatch")
        payload = {
            "profile": "CALIBRATION_REVIEW_ATTESTATION_V1",
            "record_sha256": digest,
            "reviewer_id": reviewer,
            "decision": decision,
            "note": note,
            "attested_at": attested_at,
        }
        attestation_sha = _digest(ATTESTATION_DOMAIN, payload)
        with self._transaction():
            record = self._read_record(digest)
            if record is None:
                _reject("registry.record_not_found")
            prior = self.db.execute(
                "SELECT attestation_sha256 FROM attestations "
                "WHERE record_sha256=? AND reviewer_id=?",
                (digest, reviewer),
            ).fetchone()
            if prior:
                if prior[0] != attestation_sha:
                    _reject("registry.attestation_conflict")
                return attestation_sha
            self.db.execute(
                "INSERT INTO attestations VALUES(?,?,?,?,?)",
                (attestation_sha, digest, reviewer, decision, self._bytes(payload)),
            )
        return attestation_sha

    def lookup(self, bindings: Mapping[str, str]) -> dict[str, Any] | None:
        if not isinstance(bindings, Mapping) or not bindings:
            _reject("registry.lookup_bindings")
        expected = dict(bindings)
        if set(expected) != _BINDING_KEYS:
            _reject("registry.lookup_bindings")
        for key, value in expected.items():
            if key.endswith("sha256"):
                _hash(value, key)
            elif key == "software_commit":
                if not isinstance(value, str) or _COMMIT.fullmatch(value) is None:
                    _reject("registry.software_commit")
            else:
                _safe_id(value, key)
        matches = []
        for (digest,) in self.db.execute(
            "SELECT record_sha256 FROM records ORDER BY record_sha256"
        ):
            record = self._read_record(digest)
            if record is not None and all(
                record["bindings"].get(key) == value for key, value in expected.items()
            ):
                matches.append((digest, record))
        if len(matches) > 1:
            _reject("registry.ambiguous_binding")
        if not matches:
            return None
        digest, record = matches[0]
        attestations = self.db.execute(
            "SELECT attestation_sha256,reviewer_id,decision,payload FROM attestations "
            "WHERE record_sha256=? ORDER BY reviewer_id",
            (digest,),
        ).fetchall()
        decisions = []
        reviewer_ids = []
        for attestation_sha, reviewer, decision, raw in attestations:
            try:
                value = json.loads(bytes(raw).decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as error:
                raise CalibrationRegistryError("registry.corrupt_attestation") from error
            if (
                not isinstance(value, dict)
                or reviewer not in self.trusted_reviewers
                or value.get("record_sha256") != digest
                or value.get("reviewer_id") != reviewer
                or value.get("decision") != decision
                or value.get("profile") != "CALIBRATION_REVIEW_ATTESTATION_V1"
                or _digest(ATTESTATION_DOMAIN, value) != attestation_sha
            ):
                _reject("registry.corrupt_attestation_hash")
            decisions.append(decision)
            reviewer_ids.append(reviewer)
        if not decisions:
            state = "PENDING_REVIEW"
        elif "REJECT" in decisions:
            state = "REJECTED"
        elif record["evidence_class"] == "SYNTHETIC_TEST_ONLY":
            state = "SYNTHETIC_TEST_ONLY"
        else:
            state = record["claim"]
        diagnostics = ["reviewer_identity_is_allowlisted_but_not_cryptographically_authenticated"]
        if record["evidence_class"] == "SYNTHETIC_TEST_ONLY":
            diagnostics.append("synthetic_fixture_cannot_support_physical_status")
        if state == "FAILED_PHYSICAL_TRIAL":
            state = "FAIL"
            diagnostics.append("E_PHYSICAL_VALIDATION")
        reviewed_claim = state if state in {"CALIBRATED", "PHYSICALLY_VERIFIED"} else None
        return {
            "record_sha256": digest,
            "state": "REVIEWED_CLAIM" if reviewed_claim is not None else state,
            "reviewed_claim": reviewed_claim,
            "physical_status": "UNTESTED",
            "release_eligible": False,
            "claim": record["claim"],
            "evidence_class": record["evidence_class"],
            "reviewer_ids": reviewer_ids,
            "review_attestation": "PRESENT" if decisions else "ABSENT",
            "reviewer_identity_authenticity": "NOT_ESTABLISHED",
            "source_authenticity": "NOT_ESTABLISHED",
            "diagnostics": diagnostics,
        }

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> CalibrationReviewRegistry:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> Literal[False]:
        self.close()
        return False
