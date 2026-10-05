from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest
import rfc8785
from test_analytic_solver import PROVENANCE
from test_prototype_backend import DEFAULT_REQUEST, _commit

from crochet_ai.backend_api import BackendAPI
from crochet_ai.job_store import JobStore
from crochet_ai.job_worker import execute_one
from crochet_ai.prototype_backend import LocalPrototype
from crochet_ai.prototype_storage import PrototypeStore
from crochet_ai.verification_pipeline import GateOutcome, OverallState, verify_artifacts


@pytest.fixture(scope="module")
def claims_project(tmp_path_factory):
    store = PrototypeStore(tmp_path_factory.mktemp("claims-prototype"))
    try:
        yield LocalPrototype(store, _commit()).generate(DEFAULT_REQUEST)
    finally:
        store.close()


def request_for(project: dict) -> dict:
    return {
        "api_version": "1.0.0", "operation": "inspect_analytic_candidate_claims",
        **{key: project[key] for key in ("design_spec", "material_profile", "crochet_ir")},
    }


def change_claim(ir: dict, name: str, value: object) -> None:
    parameters = ir["provenance"]["solver_parameters"]
    parameter = next(item for item in parameters if item["name"] == name)
    parameter["value"] = value
    ir["provenance"]["solver_parameters_sha256"] = sha256(
        b"Crochet.AI\0ANALYTIC_COMPILER_PARAMETERS_V1\0"
        + rfc8785.dumps(sorted(parameters, key=lambda item: item["name"]))
    ).hexdigest()


def test_claims_api_json_and_durable_job_return_the_same_partial_proof(
    claims_project, tmp_path: Path,
) -> None:
    request = request_for(claims_project)
    api = BackendAPI(PROVENANCE)
    result = api.handle(request)
    assert result["ok"], result
    data = result["data"]
    assert data["candidate_claims"]["status"] == "INDETERMINATE"
    assert data["candidate_claims"]["missing_checks"]
    assert len(data["candidate_claims_sha256"]) == 64
    assert data["verification_state"] == "NOT_VERIFIED"
    assert data["physical_status"] == "UNTESTED"
    assert api.handle_json(rfc8785.dumps(request)) == result
    store = JobStore(tmp_path / "claims-job.sqlite3")
    job_id = store.submit(rfc8785.dumps(request), "candidate-claims")
    assert execute_one(store, api)
    completed = store.get(job_id)
    assert completed["status"] == "SUCCEEDED"
    assert completed["result"] == result


def test_v5_retains_reconstructed_claims_without_accepting_the_search(claims_project) -> None:
    project = claims_project
    result = verify_artifacts(
        project["design_spec"], project["material_profile"], project["crochet_ir"],
    )
    assert result.gates[4].outcome is GateOutcome.PASS
    v5 = result.gates[5]
    assert v5.outcome is GateOutcome.INDETERMINATE
    assert v5.assertions and all(value for _, value in v5.assertions)
    assert v5.missing_checks
    assert v5.implementation_version == "analytic-claims-adapter/1.0.0"
    direct = BackendAPI(PROVENANCE).handle(request_for(project))["data"]
    assert json.loads(v5.linked_evidence_json) == direct["candidate_claims"]
    assert dict(v5.produced_artifact_hashes)["analytic_candidate_claims"] == (
        direct["candidate_claims_sha256"]
    )
    assert result.overall_state is OverallState.NOT_VERIFIED
    assert result.physical_validation_status == "UNTESTED"


@pytest.mark.parametrize(
    "mutation", ["course_count", "shaping_limit", "parameter_hash", "work_counter", "numeric_type"],
)
def test_false_claims_cannot_hide_behind_valid_ir_or_refreshed_hashes(
    claims_project, mutation: str,
) -> None:
    project = deepcopy(claims_project)
    ir = project["crochet_ir"]
    if mutation == "course_count":
        change_claim(ir, "solver.course_count", len(ir["courses"]) + 1)
    elif mutation == "shaping_limit":
        change_claim(ir, "run.max_decreases_per_course", 0)
    elif mutation == "work_counter":
        change_claim(ir, "solver.count_transitions", 2_000_001)
    elif mutation == "numeric_type":
        change_claim(ir, "run.numerics.arc_length_abs_tolerance_mm", "invalid")
    else:
        ir["provenance"]["solver_parameters_sha256"] = "a" * 64
    inspected = BackendAPI(PROVENANCE).handle(request_for(project))
    assert inspected["ok"], inspected
    assert inspected["data"]["candidate_claims"]["status"] == "FAIL"
    assert inspected["data"]["verification_state"] == "REJECTED"
    result = verify_artifacts(project["design_spec"], project["material_profile"], ir)
    assert result.gates[4].outcome is GateOutcome.PASS
    assert result.gates[5].outcome is GateOutcome.FAIL
    assert result.gates[5].diagnostics
    assert result.gates[9].outcome is GateOutcome.NOT_RUN
    assert result.overall_state is OverallState.REJECTED


def test_v5_never_runs_after_failed_v4_even_in_diagnostic_mode(claims_project, monkeypatch) -> None:
    from crochet_ai.cell_conformance import CellConformanceInputError

    def malformed(*args, **kwargs):
        raise CellConformanceInputError("cell_conformance.invalid_surface_envelope")

    monkeypatch.setattr(
        "crochet_ai.verification_pipeline.inspect_closed_cell_conformance", malformed,
    )
    project = claims_project
    result = verify_artifacts(
        project["design_spec"], project["material_profile"], project["crochet_ir"],
        diagnostic_mode=True,
    )
    assert result.gates[4].outcome is GateOutcome.FAIL
    assert result.gates[5].outcome is GateOutcome.NOT_RUN
    assert result.overall_state is OverallState.REJECTED


@pytest.mark.parametrize("field", ["solver_trace", "evidence", "max_events", "candidate_claims"])
def test_claims_boundary_rejects_client_evidence_and_budget_overrides(
    claims_project, field,
) -> None:
    request = request_for(claims_project)
    request[field] = {}
    response = BackendAPI(PROVENANCE).handle(request)
    assert response["ok"] is False
    assert response["error"]["reason"] == "request.fields"


@pytest.mark.parametrize("reason", [
    "claims.event_budget_exceeded", "stitches_resource_ceiling_exceeded",
])
def test_v5_exhausted_audit_budget_is_indeterminate_without_partial_proof(
    claims_project, monkeypatch, reason,
) -> None:
    from crochet_ai.analytic_claims import AnalyticClaimsInputError

    def exhausted(*args, **kwargs):
        raise AnalyticClaimsInputError(reason)

    monkeypatch.setattr(
        "crochet_ai.verification_pipeline.inspect_analytic_candidate_claims", exhausted,
    )
    project = claims_project
    result = verify_artifacts(
        project["design_spec"], project["material_profile"], project["crochet_ir"],
    )
    v5 = result.gates[5]
    assert v5.outcome is GateOutcome.INDETERMINATE
    assert "budget exhausted" in v5.missing_checks[0]
    assert not v5.produced_artifact_hashes
    assert result.overall_state is OverallState.NOT_VERIFIED
