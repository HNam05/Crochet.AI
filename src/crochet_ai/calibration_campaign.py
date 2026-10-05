"""Frozen pilot protocols and target-independent draft gauge derivation.

Human review and a richer uncertainty model remain necessary for calibration.
These records cannot grant CALIBRATED or PHYSICALLY_VERIFIED status.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any

import rfc8785

from .canonical import CanonicalProfile, canonical_hash, parse_json, validate_ijson
from .diagnostics import ArtifactValidationError
from .json_types import FrozenJSON, freeze_json, thaw_json
from .validation import SemanticValidator

PROTOCOL_ID = "CALIBRATION_TUBE_GAUGE_PILOT_V1"
RECORD_VERSION = "1.0.0"
CAMPAIGN_HASH_PROFILE = "CALIBRATION_CAMPAIGN_JSON_V1"
MEASUREMENT_HASH_PROFILE = "CALIBRATION_MEASUREMENT_JSON_V1"
DERIVATION_VERSION = "TUBE_BASELINE_SPECIMEN_TYPE_A_V1"
CIRCUMFERENCE_METHOD = "FLEXIBLE_TAPE_RELAXED_PERIMETER_V1"
MAX_SPECIMENS = 64
MAX_READINGS = 1024


class CalibrationError(ValueError):
    """A calibration record is unsupported, incomplete, or inconsistent."""


def _object(value: object, fields: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise CalibrationError(f"{name}.fields")
    return value


def _id(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value) is None
    ):
        raise CalibrationError(f"{name}.id")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 500:
        raise CalibrationError(f"{name}.text")
    return value


def _integer(value: object, name: str, low: int = 1, high: int = 1000) -> int:
    if type(value) is not int or not low <= value <= high:
        raise CalibrationError(f"{name}.integer")
    return value


def _number(value: object, name: str, *, zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CalibrationError(f"{name}.number")
    number = float(value)
    if not math.isfinite(number) or (number < 0 if zero else number <= 0):
        raise CalibrationError(f"{name}.number")
    return number


def _hash(value: object, name: str, *, missing: bool = False) -> str | None:
    if value is None and missing:
        return None
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise CalibrationError(f"{name}.sha256")
    return value


def _timestamp(value: object, name: str) -> str:
    text = _text(value, name)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise CalibrationError(f"{name}.timestamp") from error
    if parsed.tzinfo is None or "T" not in text:
        raise CalibrationError(f"{name}.timezone_required")
    return text


def _array(value: object, name: str, maximum: int) -> list[Any]:
    if not isinstance(value, list) or not 1 <= len(value) <= maximum:
        raise CalibrationError(f"{name}.array")
    return value


def record_hash(profile: str, value: dict[str, Any]) -> str:
    validate_ijson(value)
    return sha256(
        b"Crochet.AI\0" + profile.encode("ascii") + b"\0" + rfc8785.dumps(value)
    ).hexdigest()


@dataclass(frozen=True, init=False)
class CalibrationCampaign:
    """Owned frozen record: specimen roles cannot be edited after registration."""

    _payload: FrozenJSON
    sha256: str

    def __init__(self, value: object) -> None:
        validate_ijson(value)
        data = _object(
            value,
            {
                "record_version",
                "campaign_id",
                "protocol_id",
                "scope",
                "plan",
                "specimens",
                "instrument",
                "artifact_bindings",
                "software_commit",
                "source_snapshot_sha256",
            },
            "campaign",
        )
        if data["record_version"] != RECORD_VERSION or data["protocol_id"] != PROTOCOL_ID:
            raise CalibrationError("campaign.version_or_protocol")
        _id(data["campaign_id"], "campaign")
        _text(data["software_commit"], "campaign.software_commit")
        _hash(data["source_snapshot_sha256"], "campaign.source_snapshot")
        scope = _object(
            data["scope"],
            {
                "yarn_description",
                "yarn_lot",
                "hook_diameter_mm",
                "tension_profile_id",
                "fabric_state",
            },
            "scope",
        )
        _text(scope["yarn_description"], "scope.yarn_description")
        _text(scope["yarn_lot"], "scope.yarn_lot")
        _number(scope["hook_diameter_mm"], "scope.hook")
        _id(scope["tension_profile_id"], "scope.tension")
        if scope["fabric_state"] != "RELAXED_UNSTUFFED":
            raise CalibrationError("scope.fabric_state")
        plan = _object(
            data["plan"],
            {
                "stitches_per_course",
                "total_courses",
                "exclude_start_courses",
                "exclude_end_courses",
                "circumference_courses",
                "course_span_start",
                "course_span_intervals",
                "repeats",
            },
            "plan",
        )
        _integer(plan["stitches_per_course"], "plan.stitches", low=6, high=200)
        total = _integer(plan["total_courses"], "plan.courses", low=6, high=200)
        start = _integer(plan["exclude_start_courses"], "plan.exclude_start", high=total)
        end = _integer(plan["exclude_end_courses"], "plan.exclude_end", high=total)
        span_start = _integer(plan["course_span_start"], "plan.span_start", high=total)
        intervals = _integer(plan["course_span_intervals"], "plan.intervals", high=total)
        repeats = _integer(plan["repeats"], "plan.repeats", low=2, high=8)
        bands = _array(plan["circumference_courses"], "plan.bands", 16)
        for band in bands:
            _integer(band, "plan.band", high=total)
        if len(bands) < 2 or len(set(bands)) != len(bands):
            raise CalibrationError("plan.distinct_bands")
        if any(not start < band <= total - end for band in bands) or not (
            start < span_start < span_start + intervals <= total - end
        ):
            raise CalibrationError("plan.end_effect_region")
        if len(bands) * 2 * repeats + repeats > MAX_READINGS:
            raise CalibrationError("plan.reading_budget")
        assignments = _array(data["specimens"], "campaign.specimens", MAX_SPECIMENS)
        seen: set[str] = set()
        tube_count = 0
        for item in assignments:
            assignment = _object(item, {"specimen_id", "role", "fixture"}, "specimen")
            sid = _id(assignment["specimen_id"], "specimen")
            if sid in seen:
                raise CalibrationError("campaign.duplicate_specimen")
            seen.add(sid)
            if assignment["role"] not in ("PILOT", "CALIBRATION", "HOLDOUT", "REPRODUCTION"):
                raise CalibrationError("specimen.role")
            if assignment["fixture"] not in ("CALIBRATION_TUBE", "SPHERE", "HOURGLASS", "Y_BRANCH"):
                raise CalibrationError("specimen.fixture")
            if assignment["role"] == "CALIBRATION":
                if assignment["fixture"] != "CALIBRATION_TUBE":
                    raise CalibrationError("specimen.non_identifying_fixture")
                tube_count += 1
        if tube_count < 3:
            raise CalibrationError("campaign.minimum_three_tubes")
        instrument = _object(
            data["instrument"],
            {
                "instrument_id",
                "resolution_mm",
                "calibration_status",
                "circumference_method",
            },
            "instrument",
        )
        _id(instrument["instrument_id"], "instrument")
        _number(instrument["resolution_mm"], "instrument.resolution")
        if instrument["circumference_method"] != CIRCUMFERENCE_METHOD:
            raise CalibrationError("instrument.unsupported_circumference_method")
        if instrument["calibration_status"] not in ("UNKNOWN", "CHECKED"):
            raise CalibrationError("instrument.calibration_status")
        bindings = _object(
            data["artifact_bindings"],
            {
                "design_spec_sha256",
                "crochet_ir_sha256",
                "instructions_sha256",
                "verification_profile_id",
                "threshold_profile_id",
            },
            "bindings",
        )
        for key in ("design_spec_sha256", "crochet_ir_sha256", "instructions_sha256"):
            _hash(bindings[key], f"bindings.{key}", missing=True)
        for key in ("verification_profile_id", "threshold_profile_id"):
            _id(bindings[key], f"bindings.{key}")
        # Specimen assignment and measurement bands are sets, not execution order.
        owned = _object(parse_json(rfc8785.dumps(data)), set(data), "campaign")
        owned["specimens"] = sorted(assignments, key=lambda item: item["specimen_id"])
        owned["plan"]["circumference_courses"] = sorted(bands)
        object.__setattr__(self, "_payload", freeze_json(owned))
        object.__setattr__(self, "sha256", record_hash(CAMPAIGN_HASH_PROFILE, owned))

    def to_dict(self) -> dict[str, Any]:
        value = thaw_json(self._payload)
        if not isinstance(value, dict):
            raise CalibrationError("campaign.object")
        return value


@dataclass(frozen=True, init=False)
class CalibrationMeasurement:
    _payload: FrozenJSON
    sha256: str

    def __init__(self, value: object, campaign: CalibrationCampaign) -> None:
        validate_ijson(value)
        data = _object(
            value,
            {
                "record_version",
                "record_id",
                "campaign_sha256",
                "specimen_id",
                "instrument_id",
                "observed_at",
                "circumferences",
                "course_spans",
                "specimen_mass_g",
                "rest_hours",
                "stuffing_mass_g",
                "treatment",
                "deviations",
                "media",
                "supersedes_sha256",
            },
            "measurement",
        )
        if data["record_version"] != RECORD_VERSION or data["campaign_sha256"] != campaign.sha256:
            raise CalibrationError("measurement.campaign_binding")
        _id(data["record_id"], "measurement")
        sid = _id(data["specimen_id"], "measurement.specimen")
        context = campaign.to_dict()
        if sid not in {item["specimen_id"] for item in context["specimens"]}:
            raise CalibrationError("measurement.unassigned_specimen")
        assignment = next(item for item in context["specimens"] if item["specimen_id"] == sid)
        if assignment["fixture"] != "CALIBRATION_TUBE":
            raise CalibrationError("measurement.unsupported_fixture")
        if data["instrument_id"] != context["instrument"]["instrument_id"]:
            raise CalibrationError("measurement.instrument_binding")
        _timestamp(data["observed_at"], "measurement.observed_at")
        _hash(data["supersedes_sha256"], "measurement.supersedes", missing=True)
        _number(data["specimen_mass_g"], "measurement.mass")
        _number(data["rest_hours"], "measurement.rest", zero=True)
        if type(data["stuffing_mass_g"]) not in (float, int) or data["stuffing_mass_g"] != 0:
            raise CalibrationError("measurement.stuffed_tube")
        if data["treatment"] != "UNWASHED_UNBLOCKED":
            raise CalibrationError("measurement.treatment")
        if not isinstance(data["deviations"], list) or len(data["deviations"]) > 32:
            raise CalibrationError("measurement.deviations")
        for deviation in data["deviations"]:
            _text(deviation, "measurement.deviation")
        plan = context["plan"]
        circumferences = _array(data["circumferences"], "measurement.circumferences", MAX_READINGS)
        circum_keys: list[tuple[int, int, int]] = []
        for item in circumferences:
            reading = _object(
                item,
                {"course", "orientation_degrees", "repeat_index", "length_mm"},
                "circumference",
            )
            course = _integer(reading["course"], "circumference.course")
            orientation = _integer(
                reading["orientation_degrees"], "circumference.orientation", low=0, high=90
            )
            repeat = _integer(reading["repeat_index"], "circumference.repeat", high=plan["repeats"])
            _number(reading["length_mm"], "circumference.length")
            circum_keys.append((course, orientation, repeat))
        expected = {
            (band, orientation, repeat)
            for band in plan["circumference_courses"]
            for orientation in (0, 90)
            for repeat in range(1, plan["repeats"] + 1)
        }
        if len(circum_keys) != len(set(circum_keys)) or set(circum_keys) != expected:
            raise CalibrationError("measurement.circumference_plan")
        spans = _array(data["course_spans"], "measurement.course_spans", 8)
        span_keys = []
        for item in spans:
            reading = _object(
                item, {"start_course", "interval_count", "repeat_index", "length_mm"}, "course_span"
            )
            _integer(reading["start_course"], "course_span.start")
            _integer(reading["interval_count"], "course_span.intervals")
            repeat = _integer(reading["repeat_index"], "course_span.repeat", high=plan["repeats"])
            if (reading["start_course"], reading["interval_count"]) != (
                plan["course_span_start"],
                plan["course_span_intervals"],
            ):
                raise CalibrationError("measurement.course_span_plan")
            _number(reading["length_mm"], "course_span.length")
            span_keys.append(repeat)
        if sorted(span_keys) != list(range(1, plan["repeats"] + 1)):
            raise CalibrationError("measurement.course_span_repeats")
        if not isinstance(data["media"], list) or len(data["media"]) > 32:
            raise CalibrationError("measurement.media")
        for item in data["media"]:
            media = _object(item, {"sha256", "view", "privacy_status", "license_status"}, "media")
            _hash(media["sha256"], "media")
            for key in ("view", "privacy_status", "license_status"):
                _text(media[key], f"media.{key}")
        owned = _object(parse_json(rfc8785.dumps(data)), set(data), "measurement")
        owned["circumferences"] = sorted(circumferences, key=rfc8785.dumps)
        owned["course_spans"] = sorted(spans, key=rfc8785.dumps)
        owned["media"] = sorted(data["media"], key=rfc8785.dumps)
        object.__setattr__(self, "_payload", freeze_json(owned))
        object.__setattr__(self, "sha256", record_hash(MEASUREMENT_HASH_PROFILE, owned))

    def to_dict(self) -> dict[str, Any]:
        value = thaw_json(self._payload)
        if not isinstance(value, dict):
            raise CalibrationError("measurement.object")
        return value


def _mean(values: Sequence[float]) -> float:
    result = 0.0
    for value in values:
        result += value
    result /= len(values)
    if not math.isfinite(result):
        raise CalibrationError("derivation.numeric_overflow")
    return result


def derive_draft_material(
    campaign: CalibrationCampaign,
    measurements: Sequence[CalibrationMeasurement],
    *,
    profile_id: str,
    response_id: str,
    created_at: str,
) -> dict[str, Any]:
    """Use one predeclared raw observation per independently crocheted specimen."""
    context = campaign.to_dict()
    _id(profile_id, "profile")
    _id(response_id, "response")
    _timestamp(created_at, "created_at")
    calibration_ids = {
        item["specimen_id"] for item in context["specimens"] if item["role"] == "CALIBRATION"
    }
    records: dict[str, CalibrationMeasurement] = {}
    for measurement in measurements:
        value = measurement.to_dict()
        if value["campaign_sha256"] != campaign.sha256:
            raise CalibrationError("derivation.campaign_binding")
        sid = value["specimen_id"]
        if sid not in calibration_ids:
            raise CalibrationError("derivation.holdout_or_non_calibration")
        if sid in records:
            raise CalibrationError("derivation.duplicate_specimen")
        if value["deviations"]:
            raise CalibrationError("derivation.specimen_deviation")
        records[sid] = measurement
    if set(records) != calibration_ids:
        raise CalibrationError("derivation.incomplete_calibration_set")
    if any(
        context["artifact_bindings"][key] is None
        for key in ("design_spec_sha256", "crochet_ir_sha256", "instructions_sha256")
    ):
        raise CalibrationError("derivation.missing_instruction_bindings")
    observations: list[dict[str, Any]] = []
    quality: list[dict[str, Any]] = []
    baseline_course = min(context["plan"]["circumference_courses"])
    for sid, measurement in sorted(records.items()):
        record = measurement.to_dict()
        circumference = next(
            item
            for item in record["circumferences"]
            if (item["course"], item["orientation_degrees"], item["repeat_index"])
            == (baseline_course, 0, 1)
        )
        course_span = next(item for item in record["course_spans"] if item["repeat_index"] == 1)
        observations.append(
            {
                "specimen_id": sid,
                "stitch_span_count": context["plan"]["stitches_per_course"],
                "stitch_span_length_mm": circumference["length_mm"],
                "course_span_count": context["plan"]["course_span_intervals"],
                "course_span_length_mm": course_span["length_mm"],
            }
        )
        quality.append(
            {
                "specimen_id": sid,
                "units": "mm",
                "circumference_range_mm": max(
                    item["length_mm"] for item in record["circumferences"]
                )
                - min(item["length_mm"] for item in record["circumferences"]),
                "course_span_range_mm": max(item["length_mm"] for item in record["course_spans"])
                - min(item["length_mm"] for item in record["course_spans"]),
                "outcome": "REVIEW_REQUIRED",
                "acceptance_threshold": None,
            }
        )
    observations.sort(key=rfc8785.dumps)
    gauge: dict[str, float] = {}
    uncertainties: dict[str, float] = {}
    for dimension in ("stitch", "course"):
        values = [
            item[f"{dimension}_span_length_mm"] / item[f"{dimension}_span_count"]
            for item in observations
        ]
        mean = _mean(values)
        residual_sum = 0.0
        try:
            for value in values:
                residual_sum += (value - mean) ** 2
        except OverflowError as error:
            raise CalibrationError("derivation.numeric_overflow") from error
        uncertainty = math.sqrt(residual_sum / (len(values) * (len(values) - 1)))
        if not math.isfinite(uncertainty) or uncertainty == 0:
            raise CalibrationError("derivation.physical_zero_or_invalid_type_a_uncertainty")
        gauge[f"effective_{dimension}_pitch_mm"] = mean
        uncertainties[f"{dimension}_pitch_standard_uncertainty_mm"] = uncertainty
    material: dict[str, Any] = {
        "schema_version": "1.0.0",
        "profile_id": profile_id,
        "revision": 1,
        "yarn": {
            "description": context["scope"]["yarn_description"],
            "lot_id": context["scope"]["yarn_lot"],
        },
        "hook_diameter_mm": context["scope"]["hook_diameter_mm"],
        "calibration_responses": [
            {
                "response_id": response_id,
                "measurement_conditions": {
                    "canonical_stitch_type": "SINGLE_CROCHET",
                    "course_mode": "CYCLIC",
                    "tension_profile_id": context["scope"]["tension_profile_id"],
                    "fabric_state": context["scope"]["fabric_state"],
                },
                "observations": observations,
                "effective_gauge": gauge,
                "uncertainty": {
                    **uncertainties,
                    "basis": "REPLICATE_COMBINED_STANDARD_UNCERTAINTY",
                    "assumptions": "Draft Type-A of predeclared raw baseline readings on "
                    "independent specimens only. Within-specimen, instrument, correlation and "
                    "model uncertainty are excluded by "
                    "MaterialProfile 1.0. Human review required.",
                },
            }
        ],
        "canonicalization": {
            "profile": "MATERIAL_PROFILE_CANONICAL_JSON_V1",
            "hash_algorithm": "SHA-256",
        },
        "provenance": {
            "created_at": created_at,
            "measurement_protocol_id": PROTOCOL_ID,
            "source_record_ids": [
                record.to_dict()["record_id"] for _, record in sorted(records.items())
            ],
            "software_commit": context["software_commit"],
            "working_tree_dirty": True,
        },
    }
    validator = SemanticValidator()
    report = validator.validate_material_profile(material)
    if not report.ok:
        raise ArtifactValidationError(report)
    return {
        "derivation_version": DERIVATION_VERSION,
        "campaign_sha256": campaign.sha256,
        "measurement_sha256": [record.sha256 for _, record in sorted(records.items())],
        "material_profile": material,
        "material_profile_sha256": canonical_hash(
            material, CanonicalProfile.MATERIAL_PROFILE, validator=validator
        ),
        "verification_state": "NOT_VERIFIED",
        "physical_status": "UNTESTED",
        "calibration_review": "REQUIRED",
        "uncertainty_scope": "BASELINE_SPECIMEN_TYPE_A_ONLY",
        "baseline_selection": {
            "circumference_course": baseline_course,
            "orientation_degrees": 0,
            "repeat_index": 1,
            "course_span_repeat_index": 1,
        },
        "measurement_quality": quality,
        "excluded_parameters": [
            "instrument_type_b",
            "between_maker_variation",
            "within_specimen_repeatability",
            "measurement_method_bias",
            "bending",
            "friction",
            "stuffing_response",
            "stretch",
            "shear",
        ],
    }


def calibration_protocol() -> dict[str, object]:
    return {
        "protocol_id": PROTOCOL_ID,
        "record_version": RECORD_VERSION,
        "scope": "CYCLIC_SINGLE_CROCHET_RELAXED_UNSTUFFED_TUBE",
        "minimum_independent_calibration_specimens": 3,
        "required_orientations_degrees": [0, 90],
        "circumference_method": CIRCUMFERENCE_METHOD,
        "instruction_source": "EXACT_HASHED_CROCHET_IR_AND_EXPORT_REQUIRED",
        "tube_instruction_generator_available": False,
        "fit_parameters": ["effective_stitch_pitch_mm", "effective_course_pitch_mm"],
        "derivation_version": DERIVATION_VERSION,
        "baseline_selection": "LOWEST_INTERIOR_COURSE_ORIENTATION_0_REPEAT_1_AND_AXIAL_REPEAT_1",
        "physical_status": "UNTESTED",
        "calibration_promotion_available": False,
    }
