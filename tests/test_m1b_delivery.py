from __future__ import annotations

import json
from copy import deepcopy

import pytest
from conftest import make_reserve_ir, resolved_artifacts, resolved_validator
from test_analytic_solver import PROVENANCE

from crochet_ai.backend_api import BackendAPI
from crochet_ai.equivalence import semantic_bytes
from crochet_ai.job_store import JobStore
from crochet_ai.job_worker import execute_one


def request():
    design, material = resolved_artifacts()
    return {
        "api_version": "1.0.0",
        "operation": "export_m1b",
        "design_spec": design,
        "yarn_bindings": [
            {
                "symbol": "Yarn A",
                "material_profile": material,
                "color_label": "Natural",
                "srgb_hex": "#C8B08A",
            }
        ],
        "crochet_ir": make_reserve_ir(),
        "terminology": "US_EN",
    }


def test_wire_export_import_preserves_structure_and_never_promotes_physical_state():
    api, payload = BackendAPI(PROVENANCE), request()
    exported = api.handle_json(json.dumps(payload))
    assert exported["ok"], exported
    data = exported["data"]
    assert data["semantic_round_trip"] == "PASS"
    assert data["verification_state"] == "NOT_VERIFIED"
    imported = api.handle(
        {
            "api_version": "1.0.0",
            "operation": "import_m1b",
            "design_spec": payload["design_spec"],
            "yarn_bindings": payload["yarn_bindings"],
            "pattern": data["pattern"],
        }
    )
    assert imported["ok"], imported
    result = imported["data"]
    assert result["physical_status"] == "UNTESTED"
    assert result["provenance_status"] == "UNAUTHENTICATED_IMPORT"
    assert result["crochet_ir"]["provenance"]["software_commit"] == "0" * 40
    validator = resolved_validator()
    assert semantic_bytes(result["crochet_ir"], validator=validator) == semantic_bytes(
        payload["crochet_ir"], validator=validator
    )


@pytest.mark.parametrize(
    "mutation", ["identity", "material_identity", "bindings", "profile", "extra", "color"]
)
def test_closed_wire_contract_rejects_bad_source_and_bindings(mutation):
    payload = request()
    if mutation == "identity":
        payload["design_spec"]["design_spec_id"] = []
    elif mutation == "material_identity":
        payload["yarn_bindings"][0]["material_profile"]["profile_id"] = []
    elif mutation == "bindings":
        payload["yarn_bindings"] = []
    elif mutation == "profile":
        payload["terminology"] = "unknown"
    elif mutation == "color":
        payload["yarn_bindings"][0]["srgb_hex"] = "#123456"
    else:
        payload["source_ir"] = payload["crochet_ir"]
    before = deepcopy(payload)
    result = BackendAPI(PROVENANCE).handle_json(json.dumps(payload))
    assert result["ok"] is False
    assert payload == before


def test_export_is_durable_and_missing_structural_text_cannot_be_repaired(tmp_path):
    payload = request()
    store = JobStore(tmp_path / "m1b.sqlite")
    job = store.submit(json.dumps(payload), "m1b-export")
    assert execute_one(store, BackendAPI(PROVENANCE))
    restored = JobStore(tmp_path / "m1b.sqlite").get(job)
    assert restored["status"] == "SUCCEEDED"
    text = restored["result"]["data"]["pattern"]
    payload = {
        "api_version": "1.0.0",
        "operation": "import_m1b",
        "design_spec": payload["design_spec"],
        "yarn_bindings": payload["yarn_bindings"],
        "pattern": "\n".join(line for line in text.split("\n") if ": Reserve;" not in line),
    }
    response = BackendAPI(PROVENANCE).handle_json(json.dumps(payload))
    assert response["ok"] is False
