"""Independent boundary and identity checks on hand-authored relation artifacts."""

import ast
from copy import deepcopy
from dataclasses import FrozenInstanceError
from hashlib import sha256
from pathlib import Path

import pytest
from test_analytic_claims import _digest, _source
from test_analytic_solver import PROVENANCE
from test_semantic_equivalence import _alpha_rename

from crochet_ai import prototype_final_relation as relation_module
from crochet_ai.backend_api import BackendAPI
from crochet_ai.canonical import jcs_bytes
from crochet_ai.job_store import JobStore
from crochet_ai.job_worker import execute_one
from crochet_ai.prototype_final_relation import (
    PrototypeRelationInputError,
    inspect_prototype_final_relation,
    unique_original_proposal,
)


@pytest.fixture
def pair():
    design, material, original, validator = _source()
    final = deepcopy(original)
    final["provenance"]["solver_parameters"].extend(
        [
            {"name": "prototype.phase_policy", "value": "FIXED_ZERO_CONTINUOUS_V1"},
            {"name": "prototype.count_schedule", "value": "6"},
            {"name": "prototype.final_phases", "value": ""},
        ]
    )
    _digest(final)
    return {
        "api_version": "1.0.0",
        "operation": "inspect_prototype_final_relation",
        "design_spec": design,
        "material_profile": material,
        "original_proposal": original,
        "crochet_ir": final,
    }, validator


def inspect(pair):
    request, validator = pair
    return inspect_prototype_final_relation(
        request["design_spec"],
        request["material_profile"],
        request["original_proposal"],
        request["crochet_ir"],
        validator=validator,
    )


def test_report_is_immutable_input_bound_and_does_not_mutate_artifacts(pair):
    request, _ = pair
    before = deepcopy(request)
    report = inspect(pair)
    assert report.status == "PASS"
    payload = report.to_dict()
    assert (
        report.sha256
        == sha256(
            b"Crochet.AI\0PROTOTYPE_FINAL_RELATION_AUDIT_V1\0" + jcs_bytes(payload)
        ).hexdigest()
    )
    assert payload["source_authentication"] == "NOT_VERIFIED"
    assert payload["physical_status"] == "UNTESTED"
    payload["assertions"].clear()
    payload["budgets"]["max_events"] = 0
    assert report.to_dict()["assertions"]
    assert report.to_dict()["budgets"]["max_events"] == 30_000
    with pytest.raises(FrozenInstanceError):
        report.status = "FAIL"
    assert request == before


def test_alpha_names_entity_table_permutations_and_labels_preserve_relation(pair):
    request, validator = pair
    final = _alpha_rename(request["crochet_ir"], "delivery")
    for table in (
        "stitches",
        "frontiers",
        "attachment_locations",
        "construction_sequence",
        "frontier_transitions",
        "derivations",
        "courses",
    ):
        final[table].reverse()
    final["colors"][0]["label"] = "Presentation label"
    request["crochet_ir"] = final
    assert validator.validate_crochet_ir(final).ok
    assert inspect(pair).status == "PASS"


@pytest.mark.parametrize("mutation", ["color", "commit", "parameter"])
def test_valid_same_count_mutations_cannot_pass_relation(pair, mutation):
    request, validator = pair
    final = request["crochet_ir"]
    if mutation == "color":
        original_color = final["colors"][0]["srgb_hex"]
        final["colors"][0]["srgb_hex"] = "#000000" if original_color != "#000000" else "#FFFFFF"
    elif mutation == "commit":
        final["provenance"]["software_commit"] = "b" * 40
        assert (
            final["provenance"]["software_commit"]
            != request["original_proposal"]["provenance"]["software_commit"]
        )
    else:
        final["provenance"]["solver_parameters"].append(
            {"name": "source.unbound_lineage_marker", "value": 1}
        )
        _digest(final)
    assert validator.validate_crochet_ir(final).ok
    assert inspect(pair).status == "FAIL"


@pytest.mark.parametrize("unsupported", ["policy", "extra_prototype", "solver", "scope"])
def test_unsupported_semantics_are_incomplete_and_never_pass(pair, unsupported):
    request, validator = pair
    final = request["crochet_ir"]
    original = request["original_proposal"]
    if unsupported == "policy":
        next(
            row
            for row in final["provenance"]["solver_parameters"]
            if row["name"] == "prototype.phase_policy"
        )["value"] = "FIXED_ZERO_CONTINUOUS_V2"
    elif unsupported == "extra_prototype":
        final["provenance"]["solver_parameters"].append(
            {"name": "prototype.future_semantics", "value": True}
        )
    elif unsupported == "solver":
        for artifact in (original, final):
            artifact["provenance"]["solver_parameters"].append(
                {"name": "solver.future_semantics", "value": True}
            )
    else:
        for artifact in (original, final):
            artifact["provenance"]["generator"]["version"] = "2"
    _digest(original)
    _digest(final)
    assert validator.validate_crochet_ir(original).ok
    assert validator.validate_crochet_ir(final).ok
    report = inspect(pair)
    assert report.status == "INDETERMINATE"
    assert report.to_dict()["missing_checks"]


@pytest.mark.parametrize(
    "fields",
    [
        {"budget": 1},
        {"max_parameters": 999},
        {"status": "PASS"},
        {"final_relation": {"status": "PASS"}},
        {"candidate_proposals": []},
    ],
)
def test_api_rejects_client_reports_and_budget_overrides(pair, fields):
    request, _ = pair
    result = BackendAPI(PROVENANCE).handle({**request, **fields})
    assert result["ok"] is False
    assert result["error"]["code"] == "E_INPUT"


def test_unknown_solver_semantics_cannot_mask_known_color_contradiction(pair):
    request, validator = pair
    for artifact in (request["original_proposal"], request["crochet_ir"]):
        artifact["provenance"]["solver_parameters"].append(
            {"name": "solver.future_semantics", "value": True}
        )
        _digest(artifact)
    final = request["crochet_ir"]
    original_color = final["colors"][0]["srgb_hex"]
    final["colors"][0]["srgb_hex"] = "#000000" if original_color != "#000000" else "#FFFFFF"
    assert validator.validate_crochet_ir(final).ok
    report = inspect(pair)
    assert report.status == "FAIL"
    assert report.to_dict()["assertions"]["phase_normalized_semantics_equal"] is False


@pytest.mark.parametrize(
    "limits",
    [
        {"max_events": True},
        {"max_events": 0},
        {"max_events": 30_001},
        {"max_courses": 513},
        {"max_parameters": 257},
        {"max_events": 1},
    ],
)
def test_internal_resource_limits_reject_before_hashing(pair, limits, monkeypatch):
    request, validator = pair

    def forbidden_hash(*args, **kwargs):
        pytest.fail("over-budget input reached hashing")

    monkeypatch.setattr(relation_module, "canonical_hash", forbidden_hash)
    with pytest.raises(PrototypeRelationInputError):
        inspect_prototype_final_relation(
            request["design_spec"],
            request["material_profile"],
            request["original_proposal"],
            request["crochet_ir"],
            validator=validator,
            **limits,
        )


@pytest.mark.parametrize("excess", ["nodes", "depth", "string", "key", "table"])
def test_input_complexity_limits_precede_hashing(pair, excess, monkeypatch):
    request, _ = pair
    design = request["design_spec"]
    if excess == "nodes":
        design["extra_unadmitted"] = [0] * 100_001
    elif excess == "depth":
        nested = {}
        for _ in range(70):
            nested = {"nested": nested}
        design["extra_unadmitted"] = nested
    elif excess == "string":
        design["extra_unadmitted"] = "s" * 4097
    elif excess == "key":
        design["k" * 4097] = 0
    else:
        request["crochet_ir"]["stitches"] = [{}] * 30_001

    def forbidden_hash(*args, **kwargs):
        pytest.fail("over-budget input reached hashing")

    monkeypatch.setattr(relation_module, "canonical_hash", forbidden_hash)
    with pytest.raises(PrototypeRelationInputError):
        inspect(pair)


def test_lineage_lookup_does_not_select_first_ambiguous_or_foreign_origin(pair):
    request, _ = pair
    original, final = request["original_proposal"], request["crochet_ir"]
    assert unique_original_proposal(final, [original]) is original
    assert unique_original_proposal(final, []) is None
    assert unique_original_proposal(final, [original, _alpha_rename(original, "another")]) is None
    foreign = deepcopy(original)
    foreign["provenance"]["software_commit"] = "b" * 40
    assert unique_original_proposal(final, [foreign]) is None


def test_api_json_and_durable_job_deliver_same_report(pair, tmp_path):
    request, _ = pair
    api = BackendAPI(PROVENANCE)
    direct = api.handle(request)
    assert direct["ok"] is True
    assert set(direct["data"]) == {
        "final_relation",
        "final_relation_sha256",
        "verification_state",
        "physical_status",
    }
    assert direct["data"]["verification_state"] == "NOT_VERIFIED"
    assert direct["data"]["physical_status"] == "UNTESTED"
    assert api.handle_json(jcs_bytes(request)) == direct
    store = JobStore(tmp_path / "final-relation.sqlite3")
    job_id = store.submit(jcs_bytes(request), "pair-audit")
    assert execute_one(store, api)
    assert store.get(job_id)["result"] == direct


def test_auditor_never_imports_or_calls_generation_code():
    tree = ast.parse(Path(relation_module.__file__).read_text(encoding="utf-8"))
    forbidden = {
        "analytic_compile",
        "analytic_solver",
        "analytic_counts",
        "analytic_placement",
        "prototype_backend",
        "prototype_proposals",
    }
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert not (imports & forbidden)
    calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not (calls & {"generate_analytic", "compile_closed_schedule", "balanced_course"})


@pytest.fixture(scope="module")
def routing_evidence():
    from test_analytic_trace_audit import evidence

    return evidence()


def _verify_routing(values, candidate):
    from crochet_ai.verification_pipeline import verify_artifacts

    return verify_artifacts(
        values["design_spec"],
        values["material_profile"],
        candidate,
        search_evidence={
            key: values[key] for key in ("run_config", "search_trace", "candidate_proposals")
        },
    )


def _routing_final(values):
    original = values["candidate_proposals"][1]
    final = deepcopy(original)
    frontiers = {row["frontier_id"]: row for row in original["frontiers"]}
    courses = {row["course_id"]: row for row in original["courses"]}
    counts = [
        len(frontiers[courses[cid]["output_frontier_ids"][0]]["attachment_location_ids"])
        for cid in original["course_order"]
    ]
    final["provenance"]["solver_parameters"].extend(
        [
            {"name": "prototype.phase_policy", "value": "FIXED_ZERO_CONTINUOUS_V1"},
            {"name": "prototype.count_schedule", "value": ",".join(map(str, counts))},
            {"name": "prototype.final_phases", "value": ",".join("0" for _ in counts[1:])},
        ]
    )
    _digest(final)
    return final


def test_native_proposal_keeps_existing_membership_path(routing_evidence, monkeypatch):
    from crochet_ai import verification_pipeline as pipeline

    def forbidden_relation(*args, **kwargs):
        pytest.fail("native proposal unnecessarily entered prototype relation audit")

    monkeypatch.setattr(pipeline, "inspect_prototype_final_relation", forbidden_relation)
    result = _verify_routing(routing_evidence, routing_evidence["candidate_proposals"][1])
    gate = result.gates[5]
    assert gate.outcome.value == "INDETERMINATE"
    assert dict(gate.assertions)["search.candidate_is_emitted_proposal"]
    assert "final_candidate_to_original_proposal_relation" not in gate.missing_checks


def test_failed_search_never_enters_relation_audit(routing_evidence, monkeypatch):
    from crochet_ai import verification_pipeline as pipeline

    values = deepcopy(routing_evidence)
    values["search_trace"]["terminal"]["work"]["count_transition_evaluations"] += 1

    def forbidden_relation(*args, **kwargs):
        pytest.fail("failed search evidence entered prototype relation audit")

    monkeypatch.setattr(pipeline, "inspect_prototype_final_relation", forbidden_relation)
    result = _verify_routing(values, _routing_final(values))
    gate = result.gates[5]
    assert gate.outcome.value == "FAIL"
    assert "prototype_final_relation" not in dict(gate.produced_artifact_hashes)


def test_relation_budget_exhaustion_cannot_remove_missing_check(routing_evidence, monkeypatch):
    from crochet_ai import verification_pipeline as pipeline

    def exhausted(*args, **kwargs):
        raise PrototypeRelationInputError("input_complexity_exceeded")

    monkeypatch.setattr(pipeline, "inspect_prototype_final_relation", exhausted)
    result = _verify_routing(routing_evidence, _routing_final(routing_evidence))
    gate = result.gates[5]
    assert gate.outcome.value == "INDETERMINATE"
    assert "final_candidate_to_original_proposal_relation" in gate.missing_checks
    assert "physical_verification" in gate.missing_checks
    assert "prototype_final_relation" not in dict(gate.produced_artifact_hashes)
