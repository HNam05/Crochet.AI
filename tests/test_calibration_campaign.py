"""Independent data vectors and rejection cases for the pilot material workflow."""

from __future__ import annotations

import math
from copy import deepcopy

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from test_analytic_solver import PROVENANCE
from test_calibration_store import campaign, measurement

from crochet_ai.backend_api import BackendAPI
from crochet_ai.calibration_campaign import (
    CalibrationCampaign,
    CalibrationError,
    CalibrationMeasurement,
    derive_draft_material,
)
from crochet_ai.validation import SemanticValidator


def bound_campaign() -> CalibrationCampaign:
    value = campaign().to_dict()
    for name in ("design_spec_sha256", "crochet_ir_sha256", "instructions_sha256"):
        value["artifact_bindings"][name] = "b" * 64
    value["specimens"].append(
        {"specimen_id": "holdout", "role": "HOLDOUT", "fixture": "CALIBRATION_TUBE"}
    )
    return CalibrationCampaign(value)


def measured_set(context: CalibrationCampaign) -> list[CalibrationMeasurement]:
    records = []
    for index, (circumference, span) in enumerate(((36.0, 8.0), (48.0, 12.0), (60.0, 16.0)), 1):
        data = measurement(
            context, f"m{index}", specimen=f"s{index}", length=circumference
        ).to_dict()
        for reading in data["course_spans"]:
            reading["length_mm"] = span
        records.append(CalibrationMeasurement(data, context))
    return records


def derive(context: CalibrationCampaign, records: list[CalibrationMeasurement]) -> dict:
    return derive_draft_material(
        context,
        records,
        profile_id="mp_pilot",
        response_id="mr_pilot",
        created_at="2026-10-05T12:00:00Z",
    )


def test_independent_specimen_type_a_vector_and_nonpromotion() -> None:
    context = bound_campaign()
    result = derive(context, measured_set(context))
    profile = result["material_profile"]
    response = profile["calibration_responses"][0]
    assert len(response["observations"]) == 3  # Repeated readings are not extra specimens.
    assert response["effective_gauge"] == {
        "effective_stitch_pitch_mm": 4.0,
        "effective_course_pitch_mm": 3.0,
    }
    expected_u = math.sqrt(1 / 3)
    assert response["uncertainty"]["stitch_pitch_standard_uncertainty_mm"] == expected_u
    assert response["uncertainty"]["course_pitch_standard_uncertainty_mm"] == expected_u
    assert SemanticValidator().validate_material_profile(profile).ok
    assert result["physical_status"] == "UNTESTED"
    assert result["verification_state"] == "NOT_VERIFIED"
    assert result["calibration_review"] == "REQUIRED"
    assert "instrument_type_b" in result["excluded_parameters"]


def test_order_permutations_and_owned_record_immutability() -> None:
    original = bound_campaign()
    raw = original.to_dict()
    raw["specimens"].reverse()
    raw["plan"]["circumference_courses"].reverse()
    assert CalibrationCampaign(raw).sha256 == original.sha256
    records = measured_set(original)
    assert derive(original, records) == derive(original, records[::-1])
    value = records[0].to_dict()
    value["circumferences"].reverse()
    assert CalibrationMeasurement(value, original).sha256 == records[0].sha256
    value["circumferences"][0]["length_mm"] = 200
    assert records[0].to_dict()["circumferences"][0]["length_mm"] == 36
    raw["scope"]["yarn_description"] = "changed"
    assert original.to_dict()["scope"]["yarn_description"] == "cotton"


@pytest.mark.parametrize(
    "defect,reason",
    [
        ("missing", "incomplete_calibration_set"),
        ("duplicate", "duplicate_specimen"),
        ("holdout", "holdout_or_non_calibration"),
        ("deviation", "specimen_deviation"),
        ("zero_uncertainty", "physical_zero"),
        ("no_bindings", "missing_instruction_bindings"),
    ],
)
def test_derivation_rejects_insufficient_or_contaminated_evidence(defect: str, reason: str) -> None:
    context = campaign() if defect == "no_bindings" else bound_campaign()
    records = measured_set(context)
    if defect == "missing":
        records.pop()
    elif defect == "duplicate":
        records[-1] = records[0]
    elif defect == "holdout":
        records.append(measurement(context, "mh", specimen="holdout"))
    elif defect == "deviation":
        data = records[0].to_dict()
        data["deviations"] = ["Wrong stitch count in measuring band"]
        records[0] = CalibrationMeasurement(data, context)
    elif defect == "zero_uncertainty":
        records = [measurement(context, f"m{i}", specimen=f"s{i}", length=48) for i in range(1, 4)]
    with pytest.raises(CalibrationError, match=reason):
        derive(context, records)


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("stitches_per_course", True, "integer"),
        ("repeats", 1, "integer"),
        ("circumference_courses", [3, 3], "distinct_bands"),
        ("circumference_courses", [1, 8], "end_effect_region"),
        ("course_span_intervals", 12, "end_effect_region"),
    ],
)
def test_frozen_measurement_plan_rejects_ambiguity(field: str, value: object, reason: str) -> None:
    data = campaign().to_dict()
    data["plan"][field] = value
    with pytest.raises(CalibrationError, match=reason):
        CalibrationCampaign(data)


@pytest.mark.parametrize(
    "defect,reason",
    [
        ("missing_reading", "circumference_plan"),
        ("duplicate_reading", "circumference_plan"),
        ("wrong_intervals", "course_span_plan"),
        ("stuffed", "stuffed_tube"),
        ("naive_date", "timezone_required"),
        ("unknown_specimen", "unassigned_specimen"),
        ("wrong_campaign", "campaign_binding"),
        ("nan", "non-finite"),
    ],
)
def test_raw_readings_retain_complete_protocol_binding(defect: str, reason: str) -> None:
    context = bound_campaign()
    data = measured_set(context)[0].to_dict()
    if defect == "missing_reading":
        data["circumferences"].pop()
    elif defect == "duplicate_reading":
        data["circumferences"].append(deepcopy(data["circumferences"][0]))
    elif defect == "wrong_intervals":
        data["course_spans"][0]["interval_count"] = 3
    elif defect == "stuffed":
        data["stuffing_mass_g"] = 1
    elif defect == "naive_date":
        data["observed_at"] = "2026-10-05T12:00:00"
    elif defect == "unknown_specimen":
        data["specimen_id"] = "alien"
    elif defect == "wrong_campaign":
        data["campaign_sha256"] = "a" * 64
    else:
        data["course_spans"][0]["length_mm"] = float("nan")
    with pytest.raises(ValueError, match=reason):
        CalibrationMeasurement(data, context)


@given(st.permutations((0, 1, 2)))
@settings(max_examples=12, deadline=None)
def test_specimen_order_does_not_change_derived_identity(order: tuple[int, ...]) -> None:
    context = bound_campaign()
    records = measured_set(context)
    assert derive(context, [records[index] for index in order]) == derive(context, records)


def test_versioned_api_returns_draft_and_rejects_external_promotion() -> None:
    context = bound_campaign()
    payload = {
        "api_version": "1.0.0",
        "operation": "derive_calibration_material",
        "campaign": context.to_dict(),
        "measurements": [item.to_dict() for item in measured_set(context)],
        "profile_id": "mp_pilot",
        "response_id": "mr_pilot",
        "created_at": "2026-10-05T12:00:00Z",
    }
    api = BackendAPI(PROVENANCE)
    result = api.handle(payload)
    assert result["ok"], result
    assert result["data"]["physical_status"] == "UNTESTED"
    payload["physical_status"] = "CALIBRATED"
    assert not api.handle(payload)["ok"]


def test_within_specimen_variation_is_visible_without_inflating_sample_count() -> None:
    context = bound_campaign()
    records = measured_set(context)
    original = derive(context, records)
    data = records[0].to_dict()
    # Keep the frozen baseline unchanged while perturbing two other readings in opposite directions.
    secondary = [
        item
        for item in data["circumferences"]
        if (item["course"], item["orientation_degrees"], item["repeat_index"]) != (3, 0, 1)
    ]
    secondary[0]["length_mm"] += 20
    secondary[1]["length_mm"] -= 20
    records[0] = CalibrationMeasurement(data, context)
    changed = derive(context, records)
    assert changed["measurement_quality"][0]["circumference_range_mm"] == 40
    assert original["measurement_quality"][0]["circumference_range_mm"] == 0
    assert changed["measurement_sha256"] != original["measurement_sha256"]
    assert len(changed["material_profile"]["calibration_responses"][0]["observations"]) == 3
    assert "within_specimen_repeatability" in changed["excluded_parameters"]
    assert changed["physical_status"] == "UNTESTED"


def test_unimplemented_fixtures_and_measurement_methods_fail_closed() -> None:
    data = bound_campaign().to_dict()
    data["instrument"]["circumference_method"] = "DOUBLE_FLATTENED_WIDTH"
    with pytest.raises(CalibrationError, match="unsupported_circumference_method"):
        CalibrationCampaign(data)
    data = bound_campaign().to_dict()
    next(item for item in data["specimens"] if item["specimen_id"] == "holdout")["fixture"] = (
        "HOURGLASS"
    )
    context = CalibrationCampaign(data)
    with pytest.raises(CalibrationError, match="unsupported_fixture"):
        measurement(context, "mh", specimen="holdout")
