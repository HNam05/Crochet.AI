from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest
import rfc8785
from test_analytic_solver import PROVENANCE
from test_backend_api import request
from test_prototype_backend import DEFAULT_REQUEST, _commit

from crochet_ai.backend_api import BackendAPI
from crochet_ai.canonical import CanonicalProfile, canonical_hash, jcs_bytes
from crochet_ai.job_store import JobStore
from crochet_ai.job_worker import execute_one
from crochet_ai.prototype_backend import LocalPrototype
from crochet_ai.prototype_storage import PrototypeStore
from crochet_ai.validation import SemanticValidator


def test_wire_and_durable_job_preserve_identical_unverified_producer_trace(tmp_path: Path) -> None:
    api = BackendAPI(PROVENANCE)
    payload = request()
    response = api.handle_json(rfc8785.dumps(payload))
    assert response["ok"], response
    data = response["data"]
    trace = data["search_trace"]
    assert trace["profile"] == "ANALYTIC_SEARCH_TRACE_V1"
    assert data["search_trace_sha256"] == sha256(
        b"Crochet.AI\0ANALYTIC_SEARCH_TRACE_V1\0" + jcs_bytes(trace)
    ).hexdigest()
    assert trace["bindings"]["design_spec_sha256"] == canonical_hash(
        payload["design_spec"], CanonicalProfile.DESIGN_SPEC,
    )
    assert trace["bindings"]["material_profile_sha256"] == canonical_hash(
        payload["material_profile"], CanonicalProfile.MATERIAL_PROFILE,
    )
    assert trace["terminal"]["proposal_ir_sha256"] == [
        candidate["sha256"] for candidate in data["candidates"]
    ]
    assert trace["terminal"]["work"] == {
        "count_transition_evaluations": data["work"]["count_transitions"],
        "placement_transition_evaluations": data["work"]["placement_transitions"],
        "placement_pair_evaluations": data["work"]["placement_pairs"],
    }
    assert trace["terminal"]["completed_prefix_count"] == data["completed_course_hypotheses"]
    assert data["verification_state"] == "NOT_VERIFIED"
    assert data["physical_status"] == "UNTESTED"
    store = JobStore(tmp_path / "trace-jobs.sqlite3")
    job_id = store.submit(rfc8785.dumps(payload), "trace-generation")
    assert execute_one(store, api)
    job = store.get(job_id)
    assert job["status"] == "SUCCEEDED"
    assert job["result"] == response


@pytest.mark.parametrize("admitted", [True, False])
def test_trace_distinguishes_interrupted_search_from_unadmitted_run(admitted: bool) -> None:
    payload = request()
    if admitted:
        payload["run_config"]["max_course_hypotheses"] = 1
    else:
        payload["run_config"]["tension_profile_id"] = "missing_tension_profile"
    response = BackendAPI(PROVENANCE).handle(payload)
    assert response["ok"], response
    data = response["data"]
    if admitted:
        assert data["generation_status"] == "SEARCH_BUDGET_EXHAUSTED"
        assert len(data["candidates"]) == 1
        assert data["search_trace"] is not None
        assert len(data["search_trace_sha256"]) == 64
    else:
        assert data["generation_status"] == "INVALID_SOLVER_INPUT"
        assert data["search_trace"] is None
        assert data["search_trace_sha256"] is None
    assert data["verification_state"] == "NOT_VERIFIED"


def test_prototype_persists_proposal_final_link_and_preserves_legacy_project(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "new"
    store = PrototypeStore(directory)
    project = LocalPrototype(store, _commit()).generate(DEFAULT_REQUEST)
    generation = project["generation"]
    link = generation["proposal_to_final"]
    validator = SemanticValidator(
        design_specs={project["design_spec"]["design_spec_id"]: project["design_spec"]},
        material_profiles={project["material_profile"]["profile_id"]: project["material_profile"]},
    )
    assert link["final_crochet_ir_sha256"] == canonical_hash(
        project["crochet_ir"], CanonicalProfile.CROCHET_IR, validator=validator,
    ) == project["project_id"]
    assert link["search_trace_sha256"] == generation["search_trace_sha256"]
    assert generation["search_trace"]["terminal"]["proposal_ir_sha256"] == [
        link["proposal_crochet_ir_sha256"],
    ]
    assert link["phase_policy"] == "FIXED_ZERO_CONTINUOUS_V1"
    assert link["final_phases"] == [0] * (len(link["counts"]) - 1)
    assert link["proposal_phases"] == generation["work"]["proposal_phases"]
    assert link["verification_state"] == "NOT_VERIFIED"
    assert generation["proposal_to_final_sha256"] == sha256(
        b"Crochet.AI\0PROTOTYPE_GENERATION_LINK_V1\0" + jcs_bytes(link)
    ).hexdigest()
    legacy = deepcopy(project)
    for key in (
        "search_trace", "search_trace_sha256", "proposal_to_final", "proposal_to_final_sha256",
    ):
        del legacy["generation"][key]
    store.close()
    restored = PrototypeStore(directory)
    assert restored.get_project(project["project_id"])["generation"] == generation
    restored.close()
    legacy_store = PrototypeStore(tmp_path / "legacy")
    legacy_store.save_project(legacy, "2026-10-05T00:00:00+00:00")
    returned = LocalPrototype(legacy_store, _commit()).generate(DEFAULT_REQUEST)
    assert returned["generation"] == legacy["generation"]
    assert "search_trace" not in returned["generation"]
    legacy_store.close()
