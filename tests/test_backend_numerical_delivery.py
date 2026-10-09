from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import resolved_artifacts
from test_analytic_solver import PROVENANCE
from test_forward_closed_f0 import _recipe
from test_geometry_comparison import policy, tetra

from crochet_ai.analytic_compile import compile_closed_schedule
from crochet_ai.backend_api import BackendAPI
from crochet_ai.backend_provenance import runtime_provenance
from crochet_ai.canonical import CanonicalProfile, canonical_hash
from crochet_ai.job_store import JobStore
from crochet_ai.job_worker import execute_one
from crochet_ai.validation import SemanticValidator


@pytest.mark.parametrize("operation", ["sample_analytic_target_surface", "generate_geodesic_draft"])
@pytest.mark.parametrize("identity", [[], {}, None, 42])
def test_new_target_operations_reject_non_string_design_identity(operation, identity) -> None:
    design, material = resolved_artifacts()
    design["design_spec_id"] = identity
    payload = (
        {"sampling_policy": {}}
        if operation == "sample_analytic_target_surface"
        else {
            "mesh_json": "{}",
            "run_config": {},
        }
    )
    response = BackendAPI(PROVENANCE).handle_json(
        json.dumps(
            {
                "api_version": "1.0.0",
                "operation": operation,
                "design_spec": design,
                "material_profile": material,
                **payload,
            }
        )
    )
    assert response["ok"] is False
    assert response["error"]["code"] == "E_INPUT"
    assert response["error"]["reason"] == "request.design_spec.design_spec_id"


def f0_request():
    design, material = resolved_artifacts()
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    ir = compile_closed_schedule(design, material, (3, 4, 3), (0, 0), PROVENANCE, max_stitches=100)
    recipe = _recipe()
    elastic = recipe["closed_recipe"]["elastic_recipe"]
    # Explicit synthetic compliant model: small residuals are due to small stated
    # stiffnesses, never inflated convergence thresholds or claimed calibration.
    elastic["model_profile"]["stiffness_course_n_per_mm"] = 1e-12
    elastic["model_profile"]["stiffness_wale_n_per_mm"] = 1e-12
    elastic["rest_parameters"]["ring_stiffness_n_per_mm"] = 1e-12
    for name in ("ring_stiffness_n_per_mm", "close_stiffness_n_per_mm"):
        recipe["closed_recipe"]["closure_parameters"][name] = 1e-12
    recipe["closed_recipe"]["pressure_loading"]["pressure_n_per_mm2"] = 0
    recipe["closed_recipe"]["pressure_loading"]["volume_limit_mm3"] = 1e8
    recipe["shell_parameters"]["shear_stiffness_n_mm"] = 1e-12
    recipe["shell_parameters"]["bending_stiffness_n_mm"] = 1e-12
    recipe["contact_parameters"]["stiffness_n_per_mm"] = 1e-12
    recipe["solver_parameters"]["perturbation_mm"] = 1e-9
    return {
        "api_version": "1.0.0",
        "operation": "run_closed_f0",
        "design_spec": design,
        "material_profile": material,
        "crochet_ir": ir,
        "forward_run": recipe,
    }


def test_wire_f0_positive_synthetic_model_has_no_physical_or_v6_claim() -> None:
    request = f0_request()
    response = BackendAPI(PROVENANCE).handle_json(json.dumps(request))
    assert response["ok"], response
    data = response["data"]
    bundle = data["experimental_forward_bundle"]
    assert bundle["status"] == "CONVERGED"
    assert bundle["comparison_eligible"] is True
    assert bundle["coordinates_mm"] and bundle["faces"]
    assert bundle["final_mechanics"]["energy_n_mm"] != 0
    assert data["physical_status"] == "UNTESTED"
    assert data["verification_state"] == "NOT_VERIFIED"
    assert data["v6_outcome"] == "NOT_RUN"
    assert all(
        s["stationary_checks"] == 2 and s["energy_evaluations"] == 2 for s in bundle["starts"]
    )
    validator = SemanticValidator(
        design_specs={request["design_spec"]["design_spec_id"]: request["design_spec"]},
        material_profiles={request["material_profile"]["profile_id"]: request["material_profile"]},
    )
    assert data["source_crochet_ir_sha256"] == canonical_hash(
        request["crochet_ir"], CanonicalProfile.CROCHET_IR, validator=validator
    )


def test_new_f0_operation_persists_through_generic_job_reopen(tmp_path: Path) -> None:
    request = f0_request()
    store = JobStore(tmp_path / "jobs.sqlite")
    job = store.submit(json.dumps(request), "numerical-f0-fixture")
    assert execute_one(store, BackendAPI(PROVENANCE))
    result = JobStore(tmp_path / "jobs.sqlite").get(job)
    assert result["status"] == "SUCCEEDED"
    assert result["result"]["data"]["experimental_forward_bundle"]["status"] == "CONVERGED"
    assert result["result_sha256"]


def test_wire_geometry_comparison_remains_diagnostic_and_rejects_undeclared_registration() -> None:
    request = {
        "api_version": "1.0.0",
        "operation": "compare_geometry",
        "predicted_mesh": tetra(),
        "target_mesh": tetra(),
        "comparison_policy": policy(),
    }
    api = BackendAPI(PROVENANCE)
    response = api.handle_json(json.dumps(request))
    assert response["ok"], response
    assert response["data"]["physical_status"] == "UNTESTED"
    request["comparison_policy"]["initial_alignment"] = "SCALE_TO_FIT"
    assert api.handle(request)["ok"] is False


def test_compiler_preserves_reference_design_hash_and_rejects_wrong_revision() -> None:
    import pytest

    from crochet_ai.diagnostics import ArtifactValidationError

    request = f0_request()
    design, material = request["design_spec"], request["material_profile"]
    design["material_profile"] = {
        "binding_type": "REFERENCE",
        "profile_id": material["profile_id"],
        "revision": material["revision"],
        "sha256": canonical_hash(material, CanonicalProfile.MATERIAL_PROFILE),
    }
    validator = SemanticValidator(
        material_profiles={(material["profile_id"], material["revision"]): material}
    )
    expected = canonical_hash(design, CanonicalProfile.DESIGN_SPEC, validator=validator)
    ir = compile_closed_schedule(design, material, (3, 4, 3), (0, 0), PROVENANCE, max_stitches=100)
    assert ir["design_spec_ref"]["sha256"] == expected
    assert design["material_profile"]["binding_type"] == "REFERENCE"
    design["material_profile"]["revision"] += 1
    with pytest.raises(ArtifactValidationError):
        compile_closed_schedule(design, material, (3, 4, 3), (0, 0), PROVENANCE, max_stitches=100)


def test_wire_sampled_target_is_source_bound_discretization() -> None:
    request = f0_request()
    response = BackendAPI(runtime_provenance(PROVENANCE.software_commit)).handle(
        {
            "api_version": "1.0.0",
            "operation": "sample_analytic_target_surface",
            "design_spec": request["design_spec"],
            "material_profile": request["material_profile"],
            "sampling_policy": {
                "profile": "ANALYTIC_TARGET_SURFACE_SAMPLING_V1",
                "schema_version": "1.0.0",
                "ring_count": 4,
                "azimuth_sectors": 8,
            },
        }
    )
    assert response["ok"], response
    data = response["data"]
    assert data["status"] == "SAMPLED_DISCRETIZATION_ONLY"
    assert data["v0_certificate"] == "NOT_PROVIDED"
    assert data["approximation"]["binary64_rounding_included"] is False
    assert data["sampled_mesh"]["vertices"]


def test_saved_project_f0_http_route_is_read_only_and_rejects_source_override(
    tmp_path: Path,
) -> None:
    from threading import Thread
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen

    import pytest

    from crochet_ai.prototype_server import make_server

    request = f0_request()
    server = make_server(0, tmp_path, PROVENANCE.software_commit)
    project_id = "c" * 64
    validator = SemanticValidator(
        material_profiles={request["material_profile"]["profile_id"]: request["material_profile"]},
        design_specs={request["design_spec"]["design_spec_id"]: request["design_spec"]},
    )
    source_hash = canonical_hash(
        request["crochet_ir"], CanonicalProfile.CROCHET_IR, validator=validator
    )
    project = {
        "project_id": project_id,
        "source_crochet_ir_sha256": source_hash,
        "steps": [],
        "generation": {},
        **{key: request[key] for key in ("design_spec", "material_profile", "crochet_ir")},
    }
    saved = server.prototype_store.save_project(project, "2026-10-08T00:00:00Z")
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(base + "/api/bootstrap", timeout=15) as response:
            token = json.load(response)["data"]["csrf_token"]
        headers = {"Origin": base, "X-CSRF-Token": token, "Content-Type": "application/json"}
        body = {"project_id": project_id, "forward_run": request["forward_run"]}
        with urlopen(
            Request(
                base + "/api/forward/f0",
                data=json.dumps(body).encode(),
                headers=headers,
                method="POST",
            ),
            timeout=30,
        ) as response:
            delivered = json.load(response)
        assert delivered["ok"], delivered
        assert delivered["data"]["experimental_forward_bundle"]["status"] == "CONVERGED"
        assert server.prototype_store.get_project(project_id) == saved
        from test_numerical_verification import _context

        numerical = _context()
        numerical["forward_run"] = request["forward_run"]
        with urlopen(
            Request(
                base + "/api/verification/numerical",
                data=json.dumps({"project_id": project_id, "numerical_run": numerical}).encode(),
                headers=headers,
                method="POST",
            ),
            timeout=90,
        ) as response:
            checked = json.load(response)
        assert checked["ok"], checked
        gates = {gate["gate_id"]: gate for gate in checked["data"]["gates"]}
        assert gates["V6"]["outcome"] == "PASS", gates["V6"]
        assert gates["V6"]["linked_evidence"]["independent_audit"]["status"] == "PASS"
        assert gates["V7"]["outcome"] == "FAIL", gates["V7"]
        assert gates["V7"]["metric_vector"]
        assert checked["data"]["input_hashes"]["crochet_ir"] == source_hash
        assert checked["data"]["verification_state"] != "VERIFIED"
        assert checked["data"]["physical_status"] == "UNTESTED"
        assert server.prototype_store.get_project(project_id) == saved
        body["crochet_ir"] = request["crochet_ir"]
        with pytest.raises(HTTPError) as error:
            urlopen(
                Request(
                    base + "/api/forward/f0",
                    data=json.dumps(body).encode(),
                    headers=headers,
                    method="POST",
                ),
                timeout=15,
            )
        assert error.value.code == 400
        assert server.prototype_store.get_project(project_id) == saved
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        server.prototype_store.close()


def test_wire_obj_adapter_preserves_raw_source_and_reports_unadmitted_topology() -> None:
    from test_mesh_import import TETRA_OBJ, _params

    request = {
        "api_version": "1.0.0",
        "operation": "import_mesh_obj",
        "source_text": TETRA_OBJ,
        "import_parameters": _params().to_dict(),
    }
    api = BackendAPI(PROVENANCE)
    response = api.handle_json(json.dumps(request))
    assert response["ok"], response
    assert response["data"]["topology_status"] == "NOT_AUDITED_V0_REQUIRED"
    assert response["data"]["raw_source_sha256"] != response["data"]["mesh_jcs_sha256"]
    request["source_text"] += "vt 0 1\n"
    assert api.handle(request)["ok"] is False
