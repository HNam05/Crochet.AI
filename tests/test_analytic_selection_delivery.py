"""Transport admission and installed-job boundaries for numerical selection."""

import json
from copy import deepcopy
from hashlib import sha256
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from test_analytic_selection import native_cylinder_selection_request

from crochet_ai.backend_api import BackendAPI
from crochet_ai.backend_provenance import runtime_provenance
from crochet_ai.canonical import CanonicalProfile, canonical_hash, jcs_bytes
from crochet_ai.job_store import JobStore
from crochet_ai.job_worker import execute_one_isolated
from crochet_ai.prototype_proposals import create_proposal_bundle, retained_proposals
from crochet_ai.prototype_server import make_server
from crochet_ai.validation import SemanticValidator


def malformed_request():
    return {
        "api_version": "1.0.0",
        "operation": "select_analytic_numerical_candidate",
        "design_spec": {},
        "material_profile": {},
        "search_evidence": {},
        "numerical_run": {},
        "selection_policy": {},
    }


@pytest.mark.parametrize(
    "key", ["runners", "evidence", "calibrated", "source_snapshot", "crochet_ir", "candidates"]
)
def test_selection_wire_rejects_supplied_evidence_or_unbound_members(key):
    payload = malformed_request()
    payload[key] = {}
    before = deepcopy(payload)
    result = BackendAPI(runtime_provenance("c" * 40)).handle(payload)
    assert not result["ok"]
    assert result["error"] == {"code": "E_INPUT", "reason": "request.fields"}
    assert payload == before


@pytest.mark.parametrize(
    "key",
    ["design_spec", "material_profile", "search_evidence", "numerical_run", "selection_policy"],
)
def test_selection_wire_rejects_nonobject_fields_in_declared_order(key):
    payload = malformed_request()
    payload[key] = []
    result = BackendAPI(runtime_provenance("c" * 40)).handle(payload)
    assert result["error"] == {"code": "E_INPUT", "reason": "request." + key}


def test_selection_capability_is_explicit_and_uncalibrated():
    result = BackendAPI(runtime_provenance("c" * 40)).handle(
        {"api_version": "1.0.0", "operation": "capabilities"}
    )
    assert result["ok"]
    data = result["data"]
    assert "select_analytic_numerical_candidate" in data["operations"]
    assert data["verification_profiles"][0]["profile_id"] == "BACKEND_SEMANTIC_CHECKPOINT_V1"
    assert all(not profile["calibrated"] for profile in data["verification_profiles"])
    assert data["numerical_selection"]["max_reserved_scenario_runs"] == 40
    assert not data["capability_matrix"]["backend_release_ready"]


@pytest.fixture(scope="module")
def wire_case():
    values = native_cylinder_selection_request(radius=2, height=12, count=3, sectors=4)
    payload = {
        "api_version": "1.0.0",
        "operation": "select_analytic_numerical_candidate",
        **{k: v for k, v in values.items() if k not in {"software_commit", "source_snapshot"}},
    }
    api = BackendAPI(runtime_provenance("c" * 40))
    response = api.handle_json(json.dumps(payload))
    assert response["ok"], response
    assert response["data"]["status"] == "SELECTED", response["data"]
    return payload, response


def test_selection_survives_isolated_durable_job_reopen(wire_case, tmp_path):
    payload, expected = wire_case
    store = JobStore(tmp_path / "selection.sqlite3")
    job = store.submit(jcs_bytes(payload), "selection-positive")
    assert execute_one_isolated(
        store, BackendAPI(runtime_provenance("c" * 40)), max_wall_seconds=90
    )
    restored = JobStore(tmp_path / "selection.sqlite3").get(job)
    assert restored["status"] == "SUCCEEDED", restored
    assert restored["result"] == expected


def test_new_local_profile_never_promotes_default_or_physical_status(wire_case):
    payload, selected = wire_case
    api = BackendAPI(runtime_provenance("c" * 40))
    ir = payload["search_evidence"]["candidate_proposals"][0]
    old = api.handle(
        {
            "api_version": "1.0.0",
            "operation": "verify_candidate",
            "design_spec": payload["design_spec"],
            "material_profile": payload["material_profile"],
            "crochet_ir": ir,
            "search_evidence": payload["search_evidence"],
            "mesh_json": None,
            "diagnostic_mode": False,
        }
    )
    assert old["ok"], old
    assert old["data"]["verification_profile_id"] == "BACKEND_SEMANTIC_CHECKPOINT_V1"
    old_v5 = next(g for g in old["data"]["gates"] if g["gate_id"] == "V5")
    assert old_v5["outcome"] == "INDETERMINATE"
    assert {"physical_verification", "deterministic_candidate_selection_and_tie_break"} <= set(
        old_v5["missing_checks"]
    )
    for candidate in selected["data"]["candidate_results"]:
        proof = candidate["verification"]
        assert proof["verification_profile_id"] == "ANALYTIC_NUMERICAL_CANDIDATE_V1"
        assert proof["physical_status"] == "UNTESTED"
        if not candidate["eligible"]:
            assert proof["verification_state"] in {"REJECTED", "NOT_VERIFIED"}
            continue
        assert proof["verification_state"] == "EXPERIMENTAL"
        gate = next(g for g in proof["gates"] if g["gate_id"] == "V5")
        assert gate["outcome"] == "PASS" and not gate["missing_checks"]
        assert set(gate["linked_evidence"]["deferred_obligations"]) == {
            "physical_verification",
            "deterministic_candidate_selection_and_tie_break",
        }


@pytest.mark.parametrize("bad_value", [None, [], "not an object", True])
def test_nested_malformed_design_is_controlled_at_wire_boundary(wire_case, bad_value):
    payload = deepcopy(wire_case[0])
    payload["design_spec"]["solver_options"] = bad_value
    result = BackendAPI(runtime_provenance("c" * 40)).handle(payload)
    assert not result["ok"], result
    assert result["error"]["code"] in {"E_SCHEMA", "E_INPUT"}


def _stored_native_project(payload):
    """Source-bound minimal saved project; the real retention auditor is the oracle."""
    design, material = payload["design_spec"], payload["material_profile"]
    evidence = payload["search_evidence"]
    proposals, trace = evidence["candidate_proposals"], evidence["search_trace"]
    ir = proposals[0]
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={material["profile_id"]: material},
    )
    ir_hash = canonical_hash(ir, CanonicalProfile.CROCHET_IR, validator=validator)
    trace_hash = sha256(b"Crochet.AI\0ANALYTIC_SEARCH_TRACE_V1\0" + jcs_bytes(trace)).hexdigest()
    hypothesis = next(
        row for row in trace["hypotheses"] if row.get("proposal_ir_sha256") == ir_hash
    )
    link = {
        "profile": "PROTOTYPE_GENERATION_LINK_V1",
        "search_trace_sha256": trace_hash,
        "proposal_crochet_ir_sha256": ir_hash,
        "final_crochet_ir_sha256": ir_hash,
        "phase_policy": "FIXED_ZERO_CONTINUOUS_V1",
        "counts": hypothesis["counts"],
        "proposal_phases": hypothesis["phase"]["phases"],
        "final_phases": [0] * (len(hypothesis["counts"]) - 1),
        "verification_state": "NOT_VERIFIED",
        "physical_status": "UNTESTED",
    }
    link_hash = sha256(b"Crochet.AI\0PROTOTYPE_GENERATION_LINK_V1\0" + jcs_bytes(link)).hexdigest()
    bundle, bundle_hash = create_proposal_bundle(
        trace, trace_hash, link, link_hash, proposals, validator
    )
    project = {
        "project_id": ir_hash,
        "source_crochet_ir_sha256": ir_hash,
        "design_spec": design,
        "material_profile": material,
        "crochet_ir": ir,
        "steps": [],
        "courses": [{"total_stitches": n} for n in hypothesis["counts"]],
        "run_config": {**evidence["run_config"], "phase_policy": "FIXED_ZERO_CONTINUOUS_V1"},
        "generation": {
            "search_trace": trace,
            "search_trace_sha256": trace_hash,
            "proposal_to_final": link,
            "proposal_to_final_sha256": link_hash,
            "proposal_bundle": bundle,
            "proposal_bundle_sha256": bundle_hash,
        },
    }
    assert retained_proposals(project) == proposals
    return project


def test_saved_project_selection_is_bound_and_read_only(wire_case, tmp_path):
    payload, expected = wire_case
    project = _stored_native_project(payload)
    server = make_server(0, tmp_path / "http", "c" * 40)
    saved = server.prototype_store.save_project(project, "2026-10-19T00:00:00Z")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(base + "/api/bootstrap", timeout=10) as response:
            token = json.load(response)["data"]["csrf_token"]
        body = {
            "project_id": project["project_id"],
            "numerical_run": payload["numerical_run"],
            "selection_policy": payload["selection_policy"],
        }
        headers = {"Origin": base, "X-CSRF-Token": token, "Content-Type": "application/json"}
        with urlopen(
            Request(base + "/api/selection/numerical", json.dumps(body).encode(), headers=headers),
            timeout=90,
        ) as response:
            assert json.load(response) == expected
        assert server.prototype_store.get_project(project["project_id"]) == saved
        body["crochet_ir"] = {}
        with pytest.raises(HTTPError) as error:
            urlopen(
                Request(
                    base + "/api/selection/numerical", json.dumps(body).encode(), headers=headers
                ),
                timeout=10,
            )
        assert error.value.code == 400
        assert server.prototype_store.get_project(project["project_id"]) == saved
    finally:
        server.shutdown()
        thread.join(5)
        server.server_close()
        server.prototype_store.close()
