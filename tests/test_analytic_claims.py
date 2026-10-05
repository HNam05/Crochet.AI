from copy import deepcopy
from hashlib import sha256

import pytest
import rfc8785
from conftest import resolved_artifacts
from ring_fixtures import make_multi_ring_ir
from test_analytic_solver import PROVENANCE, config, inputs

from crochet_ai.analytic_claims import (
    AnalyticClaimsInputError,
    inspect_analytic_candidate_claims,
)
from crochet_ai.analytic_compile import compile_closed_schedule
from crochet_ai.analytic_solver import generate_analytic
from crochet_ai.canonical import CanonicalProfile, canonical_hash, jcs_bytes
from crochet_ai.validation import SemanticValidator


def _digest(ir: dict) -> None:
    parameters = sorted(ir["provenance"]["solver_parameters"], key=lambda row: row["name"])
    ir["provenance"]["solver_parameters_sha256"] = sha256(
        b"Crochet.AI\0ANALYTIC_COMPILER_PARAMETERS_V1\0" + rfc8785.dumps(parameters)
    ).hexdigest()


def _source():
    design, material = resolved_artifacts()
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    ir = make_multi_ring_ir(6)
    ir["design_spec_ref"]["sha256"] = canonical_hash(design, CanonicalProfile.DESIGN_SPEC)
    ir["provenance"]["generator"] = {
        "solver_family": "ANALYTIC",
        "name": "analytic-closed-sc",
        "version": "1",
    }
    ir["provenance"]["search_budget"] = {
        "budget_type": "CANDIDATE_EVALUATIONS",
        "limit": 1,
        "consumed": 1,
        "exhausted": False,
    }
    ir["provenance"]["solver_parameters"] = [
        {"name": "solver.course_count", "value": 1},
        {
            "name": "solver.material_response_id",
            "value": material["calibration_responses"][0]["response_id"],
        },
        {
            "name": "solver.parameter_profile_id",
            "value": design["solver_options"]["parameter_profile_id"],
        },
        {"name": "run.tension_profile_id", "value": "tension_fixture_default"},
        {"name": "run.fabric_state", "value": "RELAXED_UNSTUFFED"},
    ]
    _digest(ir)
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={material["profile_id"]: material},
    )
    return design, material, ir, validator


def test_hand_authored_schedule_yields_only_incomplete_v5_evidence() -> None:
    design, material, ir, validator = _source()
    report = inspect_analytic_candidate_claims(design, material, ir, validator=validator)
    assert report.status == "INDETERMINATE"
    assert report.to_dict()["schedule"]["counts"] == [6]
    assert report.to_dict()["construction"] == {"sewn_seams": 0, "yarn_cuts": 0, "reattachments": 0}
    assert "count_window_admission" in report.missing_checks
    assert (
        report.sha256
        == sha256(
            b"Crochet.AI\0ANALYTIC_CANDIDATE_CLAIMS_V1\0" + report.canonical_bytes
        ).hexdigest()
    )
    assert report.canonical_bytes == jcs_bytes(report.to_dict())


def test_false_solver_course_count_fails_even_with_refreshed_parameter_digest() -> None:
    design, material, ir, validator = _source()
    next(
        row for row in ir["provenance"]["solver_parameters"] if row["name"] == "solver.course_count"
    )["value"] = 2
    _digest(ir)
    report = inspect_analytic_candidate_claims(design, material, ir, validator=validator)
    assert report.status == "FAIL"
    assert (
        "E_COUNT",
        "solver course-count claim disagrees with source schedule",
    ) in report.diagnostics


@pytest.mark.parametrize(
    ("name", "value", "expected"),
    [
        ("run.max_stitches", 5, "observed schedule exceeds or misses run bounds"),
        (
            "solver.material_response_id",
            "wrong-response",
            "selected material response does not uniquely match run conditions",
        ),
        (
            "prototype.final_phases",
            "1",
            "prototype final_phases disagrees with the source schedule",
        ),
    ],
)
def test_false_bound_material_and_phase_claims_fail(
    name: str, value: object, expected: str
) -> None:
    design, material, ir, validator = _source()
    if name.startswith("prototype."):
        ir["provenance"]["solver_parameters"].extend(
            [
                {"name": "prototype.count_schedule", "value": "6"},
                {"name": "prototype.final_phases", "value": ""},
                {"name": "prototype.phase_policy", "value": "FIXED_ZERO_CONTINUOUS_V1"},
            ]
        )
    existing = next(
        (row for row in ir["provenance"]["solver_parameters"] if row["name"] == name), None
    )
    if existing is None:
        ir["provenance"]["solver_parameters"].append({"name": name, "value": value})
    else:
        existing["value"] = value
    _digest(ir)
    report = inspect_analytic_candidate_claims(design, material, ir, validator=validator)
    assert report.status == "FAIL"
    assert expected in {reason for _, reason in report.diagnostics}


def test_missing_selected_material_parameters_are_named_incomplete_evidence() -> None:
    design, material, ir, validator = _source()
    ir["provenance"]["solver_parameters"] = [
        row
        for row in ir["provenance"]["solver_parameters"]
        if row["name"] != "solver.material_response_id"
    ]
    _digest(ir)
    report = inspect_analytic_candidate_claims(design, material, ir, validator=validator)
    assert report.status == "INDETERMINATE"
    assert "solver.material_response_id" in report.missing_checks
    assert "selected_material_response" in report.missing_checks


def test_semantically_valid_unbalanced_shaping_order_fails_independent_predicate() -> None:
    design, material = inputs()
    ir = compile_closed_schedule(design, material, (6, 7), (0,), PROVENANCE, max_stitches=100)
    ir["provenance"]["solver_parameters"].extend(
        [
            {"name": "solver.course_count", "value": 2},
            {
                "name": "solver.material_response_id",
                "value": material["calibration_responses"][0]["response_id"],
            },
            {
                "name": "run.parameter_profile_id",
                "value": design["solver_options"]["parameter_profile_id"],
            },
            {"name": "run.tension_profile_id", "value": "tension_fixture_default"},
            {"name": "run.fabric_state", "value": "RELAXED_UNSTUFFED"},
        ]
    )
    stitch_by_id = {item["stitch_id"]: item for item in ir["stitches"]}
    events = {item["event_id"]: item for item in ir["construction_sequence"]}
    course = next(item for item in ir["courses"] if item["ordinal"] == 1)
    ordered = [
        stitch_by_id[events[event_id]["subject_ref"]["stitch_id"]]
        for event_id in course["member_event_ids"]
    ]
    first, last = ordered[0], ordered[-1]
    extra_old = last["top_attachment_location_ids"][1]
    extra_new = "loc_top_unbalanced_extra"
    first["shaping"] = "INCREASE"
    first["top_arity"] = 2
    first["top_attachment_location_ids"].append(extra_new)
    last["shaping"] = "PLAIN"
    last["top_arity"] = 1
    last["top_attachment_location_ids"] = last["top_attachment_location_ids"][:1]
    ir["attachment_locations"] = [
        location
        for location in ir["attachment_locations"]
        if location["attachment_location_id"] != extra_old
    ]
    ir["attachment_locations"].append(
        {
            "attachment_location_id": extra_new,
            "location_type": "TOP_LOOP",
            "producer_ref": {"entity_type": "STITCH", "stitch_id": first["stitch_id"]},
            "ordinal_within_producer": 1,
        }
    )
    transitions = {row["frontier_transition_id"]: row for row in ir["frontier_transitions"]}
    first_event = next(
        event
        for event in course["member_event_ids"]
        if events[event]["subject_ref"].get("stitch_id") == first["stitch_id"]
    )
    last_event = next(
        event
        for event in course["member_event_ids"]
        if events[event]["subject_ref"].get("stitch_id") == last["stitch_id"]
    )
    first_transition = transitions[events[first_event]["frontier_transition_ids"][0]]
    last_transition = transitions[events[last_event]["frontier_transition_ids"][0]]
    if extra_new not in first_transition["created_attachment_location_ids"]:
        first_transition["created_attachment_location_ids"].append(extra_new)
    if extra_old in last_transition["created_attachment_location_ids"]:
        last_transition["created_attachment_location_ids"].remove(extra_old)
    for frontier in ir["frontiers"]:
        creator = transitions[frontier["created_by_transition_id"]]
        available = frontier["attachment_location_ids"]
        first_top = first["top_attachment_location_ids"][0]
        if (
            creator["transition_index"] >= first_transition["transition_index"]
            and first_top in available
            and extra_new not in available
        ):
            pivot = available.index(first_top) + 1
            available.insert(pivot, extra_new)
        if (
            creator["transition_index"] >= last_transition["transition_index"]
            and extra_old in available
        ):
            available.remove(extra_old)
    close_transition = max(ir["frontier_transitions"], key=lambda row: row["transition_index"])
    terminal_input = next(
        frontier
        for frontier in ir["frontiers"]
        if frontier["frontier_id"] == close_transition["input_frontier_ids"][0]
    )
    close_transition["retired_attachment_location_ids"] = list(
        terminal_input["attachment_location_ids"]
    )
    _digest(ir)
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={material["profile_id"]: material},
    )
    validation = validator.validate_crochet_ir(ir)
    assert validation.ok, [
        (item.message_key, item.json_pointers, item.summary)
        for item in validation.diagnostics
    ]
    report = inspect_analytic_candidate_claims(design, material, ir, validator=validator)
    assert report.status == "FAIL"
    assert any("shaping" in reason for _, reason in report.diagnostics)


def test_nonanalytic_source_does_not_receive_analytic_parameter_hash_claims() -> None:
    design, material = resolved_artifacts()
    ir = make_multi_ring_ir(6)
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={material["profile_id"]: material},
    )
    assert validator.validate_crochet_ir(ir).ok
    report = inspect_analytic_candidate_claims(design, material, ir, validator=validator)
    assert report.status == "NOT_APPLICABLE"
    assert report.assertions == (("construction_limits", True),)


def test_exact_lowered_event_course_and_parameter_budgets_are_admitted() -> None:
    design, material, ir, validator = _source()
    report = inspect_analytic_candidate_claims(
        design,
        material,
        ir,
        validator=validator,
        max_events=len(ir["construction_sequence"]),
        max_courses=len(ir["courses"]),
        max_parameters=len(ir["provenance"]["solver_parameters"]),
    )
    assert report.status == "INDETERMINATE"


@pytest.mark.parametrize(
    ("entries", "missing"),
    [
        ([{"name": "prototype.count_schedule", "value": "6"}], "prototype.final_phases"),
        (
            [{"name": "prototype.phase_policy", "value": "FUTURE_POLICY"}],
            "unsupported_prototype_phase_policy",
        ),
    ],
)
def test_partial_or_unsupported_prototype_metadata_stays_indeterminate(
    entries: list[dict], missing: str
) -> None:
    design, material, ir, validator = _source()
    ir["provenance"]["solver_parameters"].extend(entries)
    _digest(ir)
    report = inspect_analytic_candidate_claims(design, material, ir, validator=validator)
    assert report.status == "INDETERMINATE"
    assert missing in report.missing_checks


def test_malformed_numeric_and_over_budget_recorded_work_fail_without_throwing() -> None:
    design, material, ir, validator = _source()
    ir["provenance"]["solver_parameters"].extend(
        [
            {"name": "run.numerics.arc_length_abs_tolerance_mm", "value": 0.05},
            {"name": "run.numerics.roundoff_allowance_mm", "value": "invalid"},
            {"name": "run.count_budget.max_transition_evaluations", "value": 2_000_000},
            {"name": "solver.count_transitions", "value": 2_000_001},
        ]
    )
    _digest(ir)
    report = inspect_analytic_candidate_claims(design, material, ir, validator=validator)
    assert report.status == "FAIL"
    reasons = {reason for _, reason in report.diagnostics}
    assert "run parameter violates an implementation ceiling" in reasons
    assert "recorded work counter exceeds or contradicts its declared budget" in reasons


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_events": 30_001},
        {"max_courses": 513},
        {"max_parameters": 257},
        {"max_parameters": True},
    ],
)
def test_requested_resource_budgets_cannot_exceed_v1_ceilings(kwargs: dict) -> None:
    design, material, ir, validator = _source()
    with pytest.raises(AnalyticClaimsInputError, match="V1 ceilings"):
        inspect_analytic_candidate_claims(design, material, ir, validator=validator, **kwargs)


def test_resource_rejection_precedes_artifact_validation_and_hashing() -> None:
    design, material, ir, validator = _source()
    with pytest.raises(AnalyticClaimsInputError, match="budget_exceeded"):
        inspect_analytic_candidate_claims({}, {}, ir, validator=validator, max_events=1)
    with pytest.raises(AnalyticClaimsInputError, match="positive integers"):
        inspect_analytic_candidate_claims(
            design, material, ir, validator=validator, max_events=True
        )


def test_unknown_parameter_and_table_permutation_are_explicit_and_deterministic() -> None:
    design, material, ir, validator = _source()
    ir["provenance"]["solver_parameters"].append({"name": "run.future_magic", "value": 4})
    _digest(ir)
    one = inspect_analytic_candidate_claims(design, material, ir, validator=validator)
    assert one.status == "INDETERMINATE"
    assert "unsupported_parameter:run.future_magic" in one.missing_checks
    shuffled = deepcopy(ir)
    for table in (
        "stitches",
        "courses",
        "frontiers",
        "construction_operations",
        "attachment_locations",
        "construction_sequence",
        "frontier_transitions",
    ):
        shuffled[table].reverse()
    two = inspect_analytic_candidate_claims(design, material, shuffled, validator=validator)
    assert one.sha256 == two.sha256


def test_real_solver_candidate_with_nonzero_rotation_is_audited_as_valid_source() -> None:
    design, material = inputs()
    batch = generate_analytic(design, material, config(), PROVENANCE)
    candidates = [candidate.crochet_ir.to_dict() for candidate in batch.candidates]
    # Phase is recorded in the source schedule and may be nonzero even though
    # the solver's selection proof itself remains outside this audit.
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={material["profile_id"]: material},
    )
    reports = [
        inspect_analytic_candidate_claims(design, material, ir, validator=validator)
        for ir in candidates
    ]
    assert reports
    assert any(
        any(phase != 0 for phase in report.to_dict()["schedule"]["phases"]) for report in reports
    )
    assert all(report.status != "FAIL" for report in reports)
