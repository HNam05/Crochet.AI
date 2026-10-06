from copy import deepcopy
from hashlib import sha256

import pytest
from test_analytic_claims import _digest, _source
from test_analytic_solver import PROVENANCE
from test_analytic_trace_audit import evidence

from crochet_ai.analytic_claims import inspect_analytic_candidate_claims
from crochet_ai.backend_api import BackendAPI
from crochet_ai.equivalence import semantic_projection
from crochet_ai.prototype_final_relation import inspect_prototype_final_relation
from crochet_ai.verification_pipeline import verify_artifacts


@pytest.fixture(scope="module")
def relation_trace_evidence():
    return evidence()


def _final(native: dict, *, count_schedule: object = "6") -> dict:
    final = deepcopy(native)
    final["provenance"]["solver_parameters"].extend(
        [
            {"name": "prototype.count_schedule", "value": count_schedule},
            {"name": "prototype.final_phases", "value": ""},
            {"name": "prototype.phase_policy", "value": "FIXED_ZERO_CONTINUOUS_V1"},
        ]
    )
    _digest(final)
    return final


def test_hand_authored_phase_zero_final_relation_passes() -> None:
    design, material, native, validator = _source()
    final = _final(native)
    report = inspect_prototype_final_relation(design, material, native, final, validator=validator)
    assert report.status == "PASS"
    assert report.to_dict()["physical_status"] == "UNTESTED"
    assert (
        report.sha256
        == sha256(b"Crochet.AI\0PROTOTYPE_FINAL_RELATION_AUDIT_V1\0" + report._payload).hexdigest()
    )


def test_canonical_parameter_strings_reject_noncanonical_numeric_spellings() -> None:
    design, material, native, validator = _source()
    report = inspect_prototype_final_relation(
        design, material, native, _final(native, count_schedule="06"), validator=validator
    )
    assert report.status == "FAIL"
    assert report.to_dict()["assertions"]["canonical_prototype_schedule_strings"] is False


def test_valid_semantic_frontier_rotation_fails_raw_anchor_replay() -> None:
    design, material, native, validator = _source()
    final = _final(native)
    frontier = next(row for row in final["frontiers"] if row["frontier_id"] == "frontier_ring_1")
    frontier["attachment_location_ids"] = (
        frontier["attachment_location_ids"][1:] + frontier["attachment_location_ids"][:1]
    )
    frontier["anchor_attachment_location_id"] = frontier["attachment_location_ids"][0]
    _digest(final)
    assert validator.validate_crochet_ir(final).ok
    claims = inspect_analytic_candidate_claims(design, material, final, validator=validator)
    assert claims.status == "INDETERMINATE"
    assert all(claims.to_dict()["assertions"].values())
    original_projection = semantic_projection(native, validator=validator)
    final_projection = semantic_projection(final, validator=validator)
    for value in (original_projection, final_projection):
        for stitch in value["stitches"]:
            stitch.pop("base_attachment_location_ids", None)
        for row in value["frontiers"]:
            row.pop("attachment_location_ids", None)
            row.pop("anchor_attachment_location_id", None)
        for row in value["frontier_transitions"]:
            if row["transition_type"] in {"ADVANCE", "CLOSE"}:
                row.pop("retired_attachment_location_ids", None)
    assert original_projection == final_projection
    report = inspect_prototype_final_relation(design, material, native, final, validator=validator)
    assert report.status == "FAIL"
    assert report.to_dict()["assertions"]["actual_execution_chains"] is False
    assert all(
        passed
        for name, passed in report.to_dict()["assertions"].items()
        if name != "actual_execution_chains"
    )


def test_api_operation_and_capability_discovery_are_exact_and_budget_private() -> None:
    design, material, native, _ = _source()
    final = _final(native)
    api = BackendAPI(PROVENANCE)
    request = {
        "api_version": "1.0.0",
        "operation": "inspect_prototype_final_relation",
        "design_spec": design,
        "material_profile": material,
        "original_proposal": native,
        "crochet_ir": final,
    }
    response = api.handle(request)
    assert response["ok"] is True
    assert response["data"]["final_relation"]["status"] == "PASS"
    assert response["data"]["final_relation_sha256"]
    capabilities = api.handle({"api_version": "1.0.0", "operation": "capabilities"})
    assert "inspect_prototype_final_relation" in capabilities["data"]["operations"]
    assert api.handle({**request, "max_events": 1})["ok"] is False


def test_v5_links_relation_only_after_trace_pass_and_keeps_selection_missing(
    relation_trace_evidence,
) -> None:
    valid_evidence = relation_trace_evidence
    design = valid_evidence["design_spec"]
    material = valid_evidence["material_profile"]
    proposals = valid_evidence["candidate_proposals"]
    original = proposals[1]
    frontiers = {row["frontier_id"]: row for row in original["frontiers"]}
    courses = {row["course_id"]: row for row in original["courses"]}
    counts = [
        len(frontiers[courses[course_id]["output_frontier_ids"][0]]["attachment_location_ids"])
        for course_id in original["course_order"]
    ]
    final = _final(original, count_schedule=",".join(str(count) for count in counts))
    # All represented post-initial courses have zero phase in this fixture.
    zero_phases = ",".join("0" for _ in range(len(original["courses"]) - 1))
    final["provenance"]["solver_parameters"] = [
        row
        for row in final["provenance"]["solver_parameters"]
        if row["name"] != "prototype.final_phases"
    ] + [{"name": "prototype.final_phases", "value": zero_phases}]
    _digest(final)
    result = verify_artifacts(
        design,
        material,
        final,
        search_evidence={
            key: valid_evidence[key]
            for key in ("run_config", "search_trace", "candidate_proposals")
        },
    )
    gate = next(item for item in result.gates if item.gate_id == "V5")
    assert result.overall_state.value == "NOT_VERIFIED"
    assert "final_candidate_to_original_proposal_relation" not in gate.missing_checks
    assert "deterministic_candidate_selection_and_tie_break" in gate.missing_checks
    assert "physical_verification" in gate.missing_checks
    assert dict(gate.produced_artifact_hashes)["prototype_final_relation"]
