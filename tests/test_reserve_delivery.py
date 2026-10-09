from __future__ import annotations

import json
from copy import deepcopy

import pytest
from test_reserve_compile import inputs

from crochet_ai.backend_api import BackendAPI
from crochet_ai.job_store import JobStore
from crochet_ai.job_worker import execute_one
from crochet_ai.pattern import PatternFormatError, TerminologyProfile, export_pattern
from crochet_ai.reserve_compile import PROFILE
from crochet_ai.validation import SemanticValidator


def request():
    design, material, provenance = inputs()
    return {
        "api_version": "1.0.0",
        "operation": "compile_reserve_schedule",
        "design_spec": design,
        "material_profile": material,
        "schedule": {
            "profile": PROFILE,
            "initial_count": 5,
            "reserved_count": 2,
            "continuing_counts": [4],
            "continuing_phases": [0],
            "max_events": 12,
            "max_attachment_locations": 14,
            "max_frontier_location_references": 45,
        },
    }, provenance


def test_wire_compiler_is_structural_and_unchanged_exporter_rejects_it():
    payload, provenance = request()
    response = BackendAPI(provenance).handle_json(json.dumps(payload))
    assert response["ok"], response
    data = response["data"]
    assert data["status"] == "COMPILED_STRUCTURAL_PROPOSAL"
    assert data["verification_state"] == "NOT_VERIFIED"
    assert data["physical_status"] == "UNTESTED"
    assert data["work"] == {
        "events": 12,
        "attachment_locations": 14,
        "frontier_location_references": 45,
    }
    assert data["visible_export_available"] is False
    assert data["forward_simulation_available"] is False
    design, material = payload["design_spec"], payload["material_profile"]
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={(material["profile_id"], material["revision"]): material},
    )
    assert validator.validate_crochet_ir(data["crochet_ir"]).ok
    with pytest.raises(PatternFormatError, match=r"pattern\.unsupported"):
        export_pattern(data["crochet_ir"], TerminologyProfile.US_EN, validator=validator)


@pytest.mark.parametrize(
    "mutation",
    ["extra", "profile", "boolean", "lost_partition", "budget", "identity", "source_override"],
)
def test_wire_schedule_rejects_malformed_or_unbounded_input(mutation):
    payload, provenance = request()
    original = deepcopy(payload)
    if mutation == "extra":
        payload["schedule"]["surprise"] = 1
    elif mutation == "profile":
        payload["schedule"]["profile"] = []
    elif mutation == "boolean":
        payload["schedule"]["initial_count"] = True
    elif mutation == "lost_partition":
        payload["schedule"]["reserved_count"] = 5
    elif mutation == "budget":
        payload["schedule"]["max_frontier_location_references"] = 44
    elif mutation == "identity":
        payload["design_spec"]["design_spec_id"] = []
    else:
        payload["software_commit"] = "f" * 40
    before = deepcopy(payload)
    response = BackendAPI(provenance).handle_json(json.dumps(payload))
    assert response["ok"] is False
    assert payload == before
    assert BackendAPI(provenance).handle(original)["ok"]


def test_reserve_job_is_durable_after_reopening_without_physical_promotion(tmp_path):
    payload, provenance = request()
    path = tmp_path / "reserve-jobs.sqlite"
    store = JobStore(path)
    job_id = store.submit(json.dumps(payload), "reserve-fixture")
    assert execute_one(store, BackendAPI(provenance))
    job = JobStore(path).get(job_id)
    assert job["status"] == "SUCCEEDED"
    assert job["result"]["data"]["work"]["events"] == 12
    assert job["result"]["data"]["physical_status"] == "UNTESTED"
    assert job["result_sha256"]
