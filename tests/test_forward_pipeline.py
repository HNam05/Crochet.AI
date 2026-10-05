from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest
from conftest import resolved_artifacts

from crochet_ai.analytic_compile import CompileProvenance, compile_closed_schedule
from crochet_ai.backend_api import BackendAPI
from crochet_ai.canonical import CanonicalProfile, canonical_hash
from crochet_ai.forward_pipeline import PROFILE, ForwardPipelineError, admit_forward_pipeline_recipe
from crochet_ai.job_store import JobStore
from crochet_ai.physical_projection import PhysicalSemanticProjection
from crochet_ai.validation import SemanticValidator


def _recipe(
    *, energy_budget: int = 100, pair_budget: int = 276, force_tolerance: float = 1e10
) -> dict[str, Any]:
    units = {
        "force_residual_n": "N",
        "position_step_mm": "mm",
        "relative_energy_change": "dimensionless",
        "contact_penetration_mm": "mm",
        "volume_orientation_epsilon_mm3": "mm^3",
        "mode_equivalence_rms_mm": "mm",
    }
    return {
        "profile": PROFILE,
        "tension_profile_id": "tension_fixture_default",
        "fabric_state": "RELAXED_UNSTUFFED",
        "loading": {
            "schema_version": "1.0.0",
            "loading_profile_id": "pipeline-unloaded",
            "state": "UNLOADED_UNPRESSURIZED",
        },
        "model_profile": {
            "schema_version": "1.0.0",
            "model_profile_id": "pipeline-model",
            "status": "HYPOTHESIS",
            "source_provenance_id": "pipeline-study",
            "stiffness_course_n_per_mm": 0.8,
            "stiffness_wale_n_per_mm": 0.4,
        },
        "config": {
            "schema_version": "1.0.0",
            "config_id": "pipeline-config",
            "model_version": "F0_STRETCH_PROTOTYPE",
            "work_budgets": {
                "max_initializations": 1,
                "max_initialization_vertices": 128,
                "max_line_search_trials": 32,
                "max_optimizer_iterations": 128,
                "max_energy_evaluations": energy_budget,
                "max_linear_iterations": 2048,
                "max_contact_pairs_evaluated": pair_budget,
            },
            "tolerances": {
                name: {
                    "value": force_tolerance if name == "force_residual_n" else 0.01,
                    "unit": unit,
                    "rationale": f"Explicit test tolerance for {name}.",
                    "owner": "forward-model",
                    "validation_path_id": f"pipeline-{name}",
                }
                for name, unit in units.items()
            },
        },
        "shear_parameters": {
            "schema_version": "1.0.0",
            "status": "HYPOTHESIS",
            "provenance_id": "shear-study",
            "stiffness_n_mm": 0.05,
            "rest_cosine": 0.0,
        },
        "bending_parameters": {
            "schema_version": "1.0.0",
            "status": "HYPOTHESIS",
            "provenance_id": "bending-study",
            "stiffness_n_mm": 0.05,
            "rest_dihedral_rad": 0.0,
        },
    }


def _source(seed: int = 0) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    design, material = resolved_artifacts()
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["solver_options"]["random_seed"] = seed
    ir = compile_closed_schedule(
        design,
        material,
        (6, 6, 6),
        (0, 0),
        CompileProvenance("a" * 40, "b" * 64, (("fixture", "forward-pipeline"),)),
        max_stitches=100,
    )
    return design, material, ir


def _request() -> dict[str, Any]:
    design, material, ir = _source()
    return {
        "api_version": "1.0.0",
        "operation": "run_forward_prototype",
        "design_spec": design,
        "material_profile": material,
        "crochet_ir": ir,
        "forward_run": _recipe(),
    }


def _run(request: dict[str, Any]) -> dict[str, Any]:
    design, material, ir = (
        request["design_spec"],
        request["material_profile"],
        request["crochet_ir"],
    )
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={material["profile_id"]: material},
    )
    projection = PhysicalSemanticProjection(ir, material, validator=validator)
    recipe = admit_forward_pipeline_recipe(request["forward_run"])
    material_validator = SemanticValidator(material_profiles={material["profile_id"]: material})
    from crochet_ai.forward_pipeline import run_forward_pipeline

    return run_forward_pipeline(projection, material, recipe, validator=material_validator)


def test_pipeline_is_deterministic_and_returns_experimental_geometry_only() -> None:
    request = _request()
    first = _run(request)
    second = _run(request)
    assert first == second
    assert first["profile"] == PROFILE
    assert first["geometry_role"] == "EXPERIMENTAL_DEBUG_ONLY"
    assert first["coordinates_mm"] is not None
    assert first["triangles"] is not None
    assert first["lower_boundary_location_ids"]
    assert first["upper_boundary_location_ids"]
    coordinate_ids = {row["attachment_location_id"] for row in first["coordinates_mm"]}
    triangle_ids = {
        location_id
        for triangle in first["triangles"]
        for location_id in triangle["attachment_location_ids"]
    }
    assert coordinate_ids == triangle_ids
    assert all(
        location_id in coordinate_ids
        for location_id in first["lower_boundary_location_ids"]
        + first["upper_boundary_location_ids"]
    )
    assert len({triangle["face_index"] for triangle in first["triangles"]}) == len(
        first["triangles"]
    )
    assert len(coordinate_ids) == 18
    assert len(first["triangles"]) == 24
    assert len(first["lower_boundary_location_ids"]) == 6
    assert len(first["upper_boundary_location_ids"]) == 6
    assert first["final_contact_adapter"]["profile"] == "FORWARD_SURFACE_COORDINATE_RESTRICTION_V1"
    assert (
        first["final_contact_adapter"]["contact_optimizer_sha256"]
        == (first["final_contact"]["optimization_sha256"])
    )
    assert first["final_contact_adapter"]["optimizer_sha256"] == first["optimizer_sha256"]


def test_api_cli_and_durable_job_keep_one_source_identity(tmp_path, capsys) -> None:
    request = _request()
    api = BackendAPI(_provenance())
    response = api.handle(request)
    assert response["ok"], response
    data = response["data"]
    expected_source_hash = canonical_hash(
        request["crochet_ir"],
        CanonicalProfile.CROCHET_IR,
        validator=SemanticValidator(
            design_specs={request["design_spec"]["design_spec_id"]: request["design_spec"]},
            material_profiles={
                request["material_profile"]["profile_id"]: request["material_profile"]
            },
        ),
    )
    assert data["source_crochet_ir_sha256"] == expected_source_hash

    db = tmp_path / "jobs.sqlite"
    store = JobStore(db)
    job_id = store.submit(json.dumps(request), "pipeline-job")
    claim = store.claim()
    assert claim is not None
    assert store.finish(claim, api.handle_json(claim.request))
    durable = store.get(job_id)["result"]
    assert durable == response

    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    from crochet_ai.cli import main

    assert main(["--json", "request", "--request-file", str(request_path)]) == 0
    cli_response = json.loads(capsys.readouterr().out)
    assert cli_response["data"]["source_crochet_ir_sha256"] == expected_source_hash
    assert (
        cli_response["data"]["experimental_forward_bundle"] == data["experimental_forward_bundle"]
    )


@pytest.mark.parametrize(
    "mutation", ["unknown", "wrong-version", "bool-coefficient", "target-override", "oversized"]
)
def test_malformed_or_over_limit_recipe_fails_closed(mutation: str) -> None:
    request = _request()
    run = request["forward_run"]
    if mutation == "unknown":
        run["mystery"] = 1
    elif mutation == "wrong-version":
        run["shear_parameters"]["schema_version"] = "2.0.0"
    elif mutation == "bool-coefficient":
        run["bending_parameters"]["stiffness_n_mm"] = True
    elif mutation == "target-override":
        run["initial_coordinates"] = []
    else:
        run["config"]["work_budgets"]["max_energy_evaluations"] = 4097
    response = BackendAPI(_provenance()).handle(request)
    assert not response["ok"]
    assert response["error"]["code"] == "E_INPUT"
    assert "experimental_forward_bundle" not in response["data"] if "data" in response else True


def test_full_pair_precheck_and_optimizer_budget_return_no_geometry() -> None:
    request = _request()
    request["forward_run"] = _recipe(pair_budget=275)
    response = BackendAPI(_provenance()).handle(request)
    assert not response["ok"] and response["error"]["code"] == "E_INPUT"

    request["forward_run"] = _recipe(energy_budget=1, force_tolerance=0.001)
    request["forward_run"]["shear_parameters"]["stiffness_n_mm"] = 100.0
    request["forward_run"]["shear_parameters"]["rest_cosine"] = -1.0
    result = _run(request)
    assert result["status"] == "BUDGET_EXHAUSTED"
    assert result["coordinates_mm"] is None
    assert result["final_contact"] is None


def test_source_solver_provenance_does_not_change_physical_bundle() -> None:
    first_request = _request()
    second_design, second_material, second_ir = _source(seed=17)
    second_request = {
        "api_version": "1.0.0",
        "operation": "run_forward_prototype",
        "design_spec": second_design,
        "material_profile": second_material,
        "crochet_ir": second_ir,
        "forward_run": _recipe(),
    }
    second_request["crochet_ir"]["provenance"]["software_commit"] = "c" * 40
    first_response = BackendAPI(_provenance()).handle(first_request)
    second_response = BackendAPI(_provenance()).handle(second_request)
    assert first_response["ok"] and second_response["ok"]
    assert (
        first_response["data"]["experimental_forward_bundle"]
        == second_response["data"]["experimental_forward_bundle"]
    )
    assert (
        first_response["data"]["source_crochet_ir_sha256"]
        != second_response["data"]["source_crochet_ir_sha256"]
    )


def test_final_contact_veto_removes_all_returned_geometry(monkeypatch) -> None:
    import crochet_ai.forward_pipeline as pipeline

    monkeypatch.setattr(
        pipeline,
        "diagnose_final_exact_self_contact",
        lambda *_args: _ContactVeto(1, b'{"forbidden_pair_count":1}'),
    )
    result = _run(_request())
    assert result["status"] == "FORBIDDEN_FINAL_INTERSECTION"
    assert result["coordinates_mm"] is None
    assert result["triangles"] is None
    assert result["lower_boundary_location_ids"] is None
    assert result["upper_boundary_location_ids"] is None
    assert result["optimizer"]["coordinates_mm"] is None


def test_unsupported_phase_fails_without_repair() -> None:
    design, material = resolved_artifacts()
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    ir = compile_closed_schedule(
        design,
        material,
        (6, 6, 6),
        (1, 0),
        CompileProvenance("a" * 40, "b" * 64, ()),
        max_stitches=100,
    )
    request = {
        "api_version": "1.0.0",
        "operation": "run_forward_prototype",
        "design_spec": design,
        "material_profile": material,
        "crochet_ir": ir,
        "forward_run": _recipe(),
    }
    response = BackendAPI(_provenance()).handle(request)
    assert not response["ok"] and response["error"]["code"] == "E_UNSUPPORTED_FEATURE"
    with pytest.raises(ForwardPipelineError, match="phase_mismatch"):
        _run(request)


def _provenance():
    from crochet_ai.analytic_compile import CompileProvenance

    return CompileProvenance("a" * 40, "b" * 64, ())


@dataclass(frozen=True)
class _ContactVeto:
    forbidden_pair_count: int
    canonical_bytes: bytes
