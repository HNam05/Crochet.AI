"""API and durable delivery for independently replayed coordinate evidence."""

from copy import deepcopy
from pathlib import Path

import pytest
from test_analytic_solver import PROVENANCE
from test_coordinate_trace_adversarial import coordinate_evidence
from test_prototype_backend import DEFAULT_REQUEST, _commit

from crochet_ai.backend_api import BackendAPI
from crochet_ai.canonical import jcs_bytes
from crochet_ai.job_store import JobStore
from crochet_ai.job_worker import execute_one_isolated
from crochet_ai.prototype_backend import LocalPrototype
from crochet_ai.prototype_storage import PrototypeStore


@pytest.fixture(scope="module")
def audit_request():
    return {"api_version": "1.0.0", "operation": "inspect_analytic_search_trace",
            **coordinate_evidence()}


def test_wire_and_reopened_isolated_job_preserve_complete_coordinate_proof(audit_request, tmp_path):
    api = BackendAPI(PROVENANCE)
    direct = api.handle(audit_request)
    assert direct["ok"] and direct["data"]["status"] == "PASS", direct
    assert direct["data"]["physical_status"] == "UNTESTED"
    assert direct["data"]["source_authentication"] == "NOT_VERIFIED"
    assert api.handle_json(jcs_bytes(audit_request)) == direct
    store = JobStore(tmp_path / "coordinate-replay.sqlite3")
    job = store.submit(jcs_bytes(audit_request), "coordinate-replay")
    assert execute_one_isolated(store, api, max_wall_seconds=30)
    restored = JobStore(tmp_path / "coordinate-replay.sqlite3").get(job)
    assert restored["status"] == "SUCCEEDED"
    assert restored["result"] == direct


def test_coordinate_prototype_verification_removes_only_completed_computational_checks(tmp_path):
    store = PrototypeStore(Path(tmp_path) / "prototype")
    project = LocalPrototype(store, _commit()).generate(
        {**DEFAULT_REQUEST, "shape": "cylinder", "diameter_mm": 20, "height_mm": 20}
    )
    generation = project["generation"]
    originals = generation["proposal_bundle"]["candidate_proposals"]
    params = {p["name"]: p["value"] for p in originals[0]["provenance"]["solver_parameters"]}
    config = {}
    for key, value in params.items():
        if key.startswith("run."):
            path = key[4:].split(".")
            if len(path) == 1:
                config[path[0]] = value
            else:
                config.setdefault(path[0], {})[path[1]] = value
    request = {"api_version": "1.0.0", "operation": "verify_candidate",
               "design_spec": project["design_spec"],
               "material_profile": project["material_profile"],
               "crochet_ir": project["crochet_ir"], "mesh_json": None, "diagnostic_mode": True,
               "search_evidence": {"run_config": config, "search_trace": generation["search_trace"],
                                   "candidate_proposals": originals}}
    api = BackendAPI(PROVENANCE)
    result = api.handle(request)
    assert result["ok"], result
    data = result["data"]
    v5 = next(g for g in data["gates"] if g["gate_id"] == "V5")
    assert v5["outcome"] == "INDETERMINATE", v5
    assert v5["linked_evidence"]["search_audit"]["status"] == "PASS", v5
    assert v5["linked_evidence"]["final_relation"]["status"] == "PASS", v5
    assert set(v5["missing_checks"]) == {
        "deterministic_candidate_selection_and_tie_break", "physical_verification"}
    assert data["verification_state"] == "NOT_VERIFIED"
    assert data["physical_status"] == "UNTESTED"
    assert store.get_project(project["project_id"]) == project
    false = deepcopy(request)
    false["search_evidence"]["search_trace"]["hypotheses"][0]["samples"][0]["axial_mm"] = "1/1"
    rejected = api.handle(false)
    assert rejected["ok"], rejected
    bad_v5 = next(g for g in rejected["data"]["gates"] if g["gate_id"] == "V5")
    assert bad_v5["outcome"] == "FAIL"
    assert rejected["data"]["verification_state"] == "REJECTED"
    assert store.get_project(project["project_id"]) == project
    store.close()
