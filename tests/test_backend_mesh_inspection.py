"""Untrusted, UI-independent boundary for diagnostic-only opening inspection."""

import json
from hashlib import sha256

import pytest
import rfc8785
from test_analytic_solver import PROVENANCE
from test_target_mesh_openings import documents, mesh_bytes

from crochet_ai.backend_api import BackendAPI
from crochet_ai.canonical import parse_json, validate_ijson
from crochet_ai.job_store import JobStore
from crochet_ai.job_worker import execute_one


def request() -> dict:
    raw = mesh_bytes()
    design, material, _ = documents(raw)
    return {
        "api_version": "1.0.0", "operation": "inspect_mesh_openings",
        "design_spec": design.to_dict(), "material_profile": material.to_dict(),
        "mesh_json": raw.decode("utf-8"),
    }


def test_inspection_is_discoverable_and_roundtrips_as_json() -> None:
    api = BackendAPI(PROVENANCE)
    capabilities = api.handle({"api_version": "1.0.0", "operation": "capabilities"})
    assert "inspect_mesh_openings" in capabilities["data"]["operations"]
    response = api.handle(request())
    assert response["ok"], response
    data = response["data"]
    assert data["diagnostic"]["classification"] == "UNIQUE"
    assert data["diagnostic"]["status"] == "OPENING_BINDING_DIAGNOSTIC_ONLY"
    assert data["verification_state"] == "NOT_VERIFIED"
    assert data["mesh_preflight_state"] == "INDETERMINATE"
    assert data["physical_status"] == "UNTESTED"
    validate_ijson(response)
    assert parse_json(rfc8785.dumps(response)) == response
    assert api.handle_json(json.dumps(request())) == response


@pytest.mark.parametrize("field,value", [
    ("mesh_json", {}), ("mesh_json", "file:///private/mesh.json"),
    ("mesh_json", "https://example.test/mesh.json"),
    ("design_spec", None), ("material_profile", []),
    ("max_faces", 10_000_000), ("server_provenance", {}),
])
def test_inspection_rejects_bad_inputs_and_client_budget_overrides(field, value) -> None:
    payload = request()
    payload[field] = value
    result = BackendAPI(PROVENANCE).handle(payload)
    assert result["ok"] is False
    assert result["error"]["code"].startswith("E_")


def test_inspection_rejects_large_mesh_even_when_digest_matches() -> None:
    payload = request()
    payload["mesh_json"] += " " * 262_144
    payload["design_spec"]["target_geometry"]["artifact"]["sha256"] = sha256(
        payload["mesh_json"].encode(),
    ).hexdigest()
    response = BackendAPI(PROVENANCE).handle(payload)
    assert response["ok"] is False
    assert response["error"]["reason"] == "openings.mesh_diagnostic_invalid"


def test_supplied_material_must_match_inline_binding() -> None:
    payload = request()
    payload["material_profile"]["revision"] += 1
    result = BackendAPI(PROVENANCE).handle(payload)
    assert result["ok"] is False
    assert result["error"]["reason"] == "openings.supplied_material_profile_mismatch"


def test_ambiguous_inspection_is_handled_without_mesh_acceptance() -> None:
    payload = request()
    landmark = payload["design_spec"]["landmarks"][0]
    landmark.update(position_mm=[0., 0., 0.], tolerance_mm=3.)
    result = BackendAPI(PROVENANCE).handle(payload)
    assert result["ok"] is True
    assert result["data"]["diagnostic"]["classification"] == "AMBIGUOUS"
    assert result["data"]["mesh_preflight_state"] == "INDETERMINATE"


def test_inspection_persists_through_local_job_execution(tmp_path) -> None:
    api = BackendAPI(PROVENANCE)
    payload = request()
    store = JobStore(tmp_path / "inspection.sqlite")
    job_id = store.submit(json.dumps(payload), idempotency_key="mesh-inspection-1")
    assert execute_one(store, api) is True
    completed = store.get(job_id)
    assert completed["status"] == "SUCCEEDED"
    assert completed["result"] == api.handle(payload)
