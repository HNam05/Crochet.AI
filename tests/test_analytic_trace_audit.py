from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path

import pytest
from test_analytic_trace import PROVENANCE, _config, _inputs

from crochet_ai.analytic_counts import CountSearchBudget
from crochet_ai.analytic_placement import PlacementBudget
from crochet_ai.analytic_solver import generate_analytic
from crochet_ai.analytic_trace_audit import AUDIT_DOMAIN, inspect_analytic_search_trace
from crochet_ai.backend_api import BackendAPI
from crochet_ai.canonical import jcs_bytes
from crochet_ai.job_store import JobStore
from crochet_ai.job_worker import execute_one
from crochet_ai.trace_verification_types import TraceAuditInputError
from crochet_ai.validation import SemanticValidator
from crochet_ai.verification_pipeline import GateOutcome, OverallState, verify_artifacts


def evidence(config=None, *, equal_ellipsoid=False, unequal_ellipsoid=False):
    design, material = _inputs()
    if equal_ellipsoid or unequal_ellipsoid:
        target = design["target_geometry"]
        target["primitive"] = "ELLIPSOID"
        radius_id = target["parameters"][0]["measurement_id"]
        target["parameters"] = [
            {"parameter": "EQUATORIAL_RADIUS", "measurement_id": radius_id},
            {"parameter": "POLAR_RADIUS", "measurement_id": radius_id},
        ]
        if unequal_ellipsoid:
            polar = deepcopy(design["dimensions"]["measurements"][0])
            polar.update(measurement_id="dim_fixture_polar", value_mm=5)
            design["dimensions"]["measurements"].append(polar)
            target["parameters"][1]["measurement_id"] = "dim_fixture_polar"
    config = _config() if config is None else config
    batch = generate_analytic(design, material, config, PROVENANCE)
    assert batch.search_trace is not None
    wire = asdict(config)
    fraction = config.minimum_shaping_separation_turns
    wire["minimum_shaping_separation_turns"] = f"{fraction.numerator}/{fraction.denominator}"
    return {
        "design_spec": design,
        "material_profile": material,
        "run_config": wire,
        "search_trace": batch.search_trace.to_dict(),
        "candidate_proposals": [item.crochet_ir.to_dict() for item in batch.candidates],
    }


@pytest.fixture(scope="module")
def valid_evidence():
    return evidence()


def audit(values, **kwargs):
    design, material = values["design_spec"], values["material_profile"]
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={material["profile_id"]: material},
    )
    return inspect_analytic_search_trace(
        design,
        material,
        values["run_config"],
        values["search_trace"],
        values["candidate_proposals"],
        validator=validator,
        **kwargs,
    )


def test_complete_sphere_audit_is_immutable_exact_and_hash_bound(valid_evidence):
    report = audit(valid_evidence)
    assert report.status == "PASS", report.to_dict()
    assert report.assertions and all(value for _, value in report.assertions)
    assert not report.missing_checks
    assert report.sha256 == sha256(AUDIT_DOMAIN + report.canonical_bytes).hexdigest()
    assert audit(valid_evidence).canonical_bytes == report.canonical_bytes
    copied = report.to_dict()
    copied["assertions"].clear()
    assert report.to_dict()["assertions"]


@pytest.mark.parametrize(
    "mutation",
    [
        "window",
        "count_work",
        "phase_tie",
        "phase_work",
        "prefix",
        "terminal",
        "source",
        "config",
        "material",
        "proposal",
        "seed",
        "type",
    ],
)
def test_refreshed_hash_does_not_hide_false_claims(valid_evidence, mutation):
    values = deepcopy(valid_evidence)
    trace = values["search_trace"]
    first = trace["hypotheses"][0]
    if mutation == "window":
        first["count_windows"][0]["minimum"] = "1"
    elif mutation == "count_work":
        first["count_layers"][0]["retained_states"] += 1
    elif mutation == "phase_tie":
        first["phase"]["phases"][0] += 1
    elif mutation == "phase_work":
        first["phase"]["layers"][0]["transition_evaluations"] += 1
    elif mutation == "prefix":
        trace["hypotheses"].pop()
    elif mutation == "terminal":
        trace["terminal"]["work"]["count_transition_evaluations"] += 1
    elif mutation == "source":
        trace["source"]["source_snapshot_sha256"] = "c" * 64
    elif mutation == "config":
        trace["bindings"]["run_config_sha256"] = "c" * 64
    elif mutation == "material":
        trace["material_response"]["stitch_pitch_mm"] = "1/1"
    elif mutation == "proposal":
        first["proposal_ir_sha256"] = "c" * 64
        trace["terminal"]["proposal_ir_sha256"][0] = "c" * 64
    elif mutation == "seed":
        trace["random_seed"] = 123
    else:
        first["count_layers"][0]["completed"] = 1
    refreshed_digest = sha256(
        b"Crochet.AI\0ANALYTIC_SEARCH_TRACE_V1\0" + jcs_bytes(trace)
    ).hexdigest()
    assert len(refreshed_digest) == 64
    assert audit(values).status == "FAIL"


@pytest.mark.parametrize(
    "config",
    [
        replace(_config(), count_budget=CountSearchBudget(32, 32, 32, 1)),
        replace(_config(), count_budget=CountSearchBudget(32, 32, 1, 10000)),
        replace(_config(), count_budget=CountSearchBudget(1, 32, 32, 10000)),
        replace(_config(), count_budget=CountSearchBudget(32, 1, 32, 10000)),
        replace(_config(), placement_budget=PlacementBudget(64, 1, 100000)),
        replace(_config(), placement_budget=PlacementBudget(64, 10000, 1)),
        replace(_config(), placement_budget=PlacementBudget(1, 10000, 100000)),
        replace(_config(), max_stitches=1),
        replace(_config(), max_emitted_candidates=1),
        replace(_config(), max_course_hypotheses=1),
        replace(_config(), initial_ring_min=100, initial_ring_max=101),
    ],
)
def test_interruption_and_empty_domains_are_independently_confirmed(config):
    report = audit(evidence(config))
    assert report.status == "PASS", report.to_dict()


def test_missing_original_proposal_and_proof_exhaustion_are_explicit(valid_evidence):
    values = deepcopy(valid_evidence)
    values["candidate_proposals"] = []
    report = audit(values)
    assert report.status == "INDETERMINATE"
    assert report.missing_checks == ("original_proposal_artifacts",)
    limited = audit(valid_evidence, max_replay_work=1)
    assert limited.status == "INDETERMINATE"
    assert "independent_replay_budget_exhausted" in limited.missing_checks


def test_resource_and_native_scalar_input_limits(valid_evidence):
    values = deepcopy(valid_evidence)
    values["search_trace"]["hypotheses"] = [{}] * 513
    with pytest.raises(TraceAuditInputError):
        audit(values)
    oversized = {
        "run_config": valid_evidence["run_config"],
        "search_trace": {"padding": [0] * 100_000},
        "candidate_proposals": [],
    }
    with pytest.raises(TraceAuditInputError, match="input_complexity"):
        verify_artifacts(
            valid_evidence["design_spec"], valid_evidence["material_profile"],
            valid_evidence["candidate_proposals"][1], search_evidence=oversized,
        )
    values = deepcopy(valid_evidence)
    values["run_config"]["count_budget"]["max_courses"] = True
    with pytest.raises(TraceAuditInputError):
        audit(values)


def test_equal_axis_ellipsoid_is_supported_and_unequal_axis_is_explicitly_open():
    equal = audit(evidence(equal_ellipsoid=True))
    assert equal.status == "PASS", equal.to_dict()
    unequal = audit(evidence(unequal_ellipsoid=True))
    assert unequal.status == "INDETERMINATE", unequal.to_dict()
    assert unequal.missing_checks == ("unsupported_target_sampler",)


def test_api_job_and_gate_evidence_agree_without_physical_acceptance(valid_evidence, tmp_path):
    request = {
        "api_version": "1.0.0",
        "operation": "inspect_analytic_search_trace",
        **valid_evidence,
    }
    api = BackendAPI(PROVENANCE)
    direct = api.handle(request)
    assert direct["ok"] and direct["data"]["status"] == "PASS", direct
    assert api.handle_json(jcs_bytes(request)) == direct
    store = JobStore(tmp_path / "trace-job.sqlite3")
    job_id = store.submit(jcs_bytes(request), "trace-audit")
    assert execute_one(store, api)
    assert store.get(job_id)["result"] == direct
    # The first native proposal's rotated closure is outside the current V4 cell
    # adapter. The second has zero phases and is admitted without changing V4.
    candidate = valid_evidence["candidate_proposals"][1]
    search = {
        key: valid_evidence[key] for key in ("run_config", "search_trace", "candidate_proposals")
    }
    result = verify_artifacts(
        valid_evidence["design_spec"],
        valid_evidence["material_profile"],
        candidate,
        search_evidence=search,
    )
    assert result.gates[4].outcome is GateOutcome.PASS
    gate = result.gates[5]
    assert gate.outcome is GateOutcome.INDETERMINATE
    assert dict(gate.assertions)["search.candidate_is_emitted_proposal"]
    assert "input_bound_search_trace" not in gate.missing_checks
    assert "physical_verification" in gate.missing_checks
    assert result.overall_state is OverallState.NOT_VERIFIED
    assert result.physical_validation_status == "UNTESTED"
    import json

    assert json.loads(gate.linked_evidence_json)["search_audit"] == direct["data"]
    search["search_trace"] = deepcopy(search["search_trace"])
    search["search_trace"]["terminal"]["work"]["count_transition_evaluations"] += 1
    failed = verify_artifacts(
        valid_evidence["design_spec"],
        valid_evidence["material_profile"],
        candidate,
        search_evidence=search,
    )
    assert failed.gates[5].outcome is GateOutcome.FAIL


def test_verifier_imports_no_generation_implementation():
    source = Path(__file__).resolve().parents[1] / "src" / "crochet_ai"
    forbidden = {
        "analytic_solver",
        "analytic_counts",
        "analytic_placement",
        "analytic_compile",
        "analytic_geometry",
        "balanced_course",
        "analytic_trace",
    }
    for name in ("analytic_trace_audit.py", "trace_count_replay.py", "trace_phase_replay.py"):
        tree = ast.parse((source / name).read_text(encoding="utf-8"))
        imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        assert not any(module and module.split(".")[-1] in forbidden for module in imports)


def test_api_rejects_malformed_identity_and_client_proof_budget(valid_evidence):
    request = {
        "api_version": "1.0.0", "operation": "inspect_analytic_search_trace", **valid_evidence,
    }
    api = BackendAPI(PROVENANCE)
    override = {**request, "max_replay_work": 1}
    assert api.handle(override)["error"]["code"] == "E_INPUT"
    malformed = deepcopy(request)
    malformed["design_spec"]["design_spec_id"] = []
    assert api.handle(malformed)["error"]["code"] == "E_INPUT"
