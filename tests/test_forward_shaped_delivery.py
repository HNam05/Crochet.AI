"""Independent mechanical oracles and delivery for shaped elastic preparation."""

from copy import deepcopy
from math import fsum, sqrt

import pytest
from conftest import resolved_artifacts
from test_forward_pipeline import _recipe

from crochet_ai.analytic_compile import CompileProvenance, compile_closed_schedule
from crochet_ai.backend_api import BackendAPI
from crochet_ai.canonical import jcs_bytes
from crochet_ai.job_store import JobStore
from crochet_ai.job_worker import execute_one_isolated

PROVENANCE = CompileProvenance("a" * 40, "b" * 64, (("fixture", "shaped-delivery"),))


def shaped_request(counts=(3, 4, 3)):
    design, material = resolved_artifacts()
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    ir = compile_closed_schedule(
        design, material, counts, (0,) * (len(counts) - 1), PROVENANCE, max_stitches=100
    )
    recipe = _recipe()
    del recipe["shear_parameters"]
    del recipe["bending_parameters"]
    recipe["profile"] = "FORWARD_SHAPED_ELASTIC_DIAGNOSTIC_V1"
    recipe["config"]["work_budgets"]["max_initialization_vertices"] = 512
    recipe["rest_parameters"] = {
        "schema_version": "1.0.0",
        "status": "HYPOTHESIS",
        "provenance_id": "synthetic-shaping-study",
        "wale_rest_length_factors": {"PLAIN": 1.1, "INCREASE": 1.5, "DECREASE": 1.9},
        "wale_stiffness_factors": {"PLAIN": 0.5, "INCREASE": 1.0, "DECREASE": 2.0},
        "ring_rest_length_mm": 0.6,
        "ring_stiffness_n_per_mm": 0.3,
        "ring_initial_chord_mm": 1.2,
        "ring_initial_offset_mm": 2.0,
    }
    return {
        "api_version": "1.0.0",
        "operation": "inspect_shaped_forward_model",
        "design_spec": design,
        "material_profile": material,
        "crochet_ir": ir,
        "forward_run": recipe,
    }


@pytest.fixture(scope="module")
def request_fixture():
    return shaped_request()


@pytest.fixture(scope="module")
def result_fixture(request_fixture):
    result = BackendAPI(PROVENANCE).handle(request_fixture)
    assert result["ok"], result
    return result


def _energy(terms, points):
    return fsum(
        0.5
        * term["stiffness_n_per_mm"]
        * (
            sqrt(
                fsum(
                    (a - b) ** 2
                    for a, b in zip(
                        points[term["source_location_id"]],
                        points[term["target_location_id"]],
                        strict=True,
                    )
                )
            )
            - term["rest_length_mm"]
        )
        ** 2
        for term in terms
    )


def test_published_forces_are_negative_energy_gradient_and_balance(result_fixture):
    bundle = result_fixture["data"]["experimental_forward_bundle"]
    points = {row["attachment_location_id"]: row["position_mm"] for row in bundle["coordinates_mm"]}
    terms = bundle["spring_terms"]
    assert bundle["energy_n_mm"] > 0
    assert bundle["energy_n_mm"] == pytest.approx(_energy(terms, points), rel=1e-12)
    forces = {row["attachment_location_id"]: row["force_n"] for row in bundle["forces_n"]}
    assert set(points) == set(forces)
    assert set(points) == {vertex for face in bundle["faces"] for vertex in face}
    # Synthetic numerical oracle: central step 1e-5 mm, gradient error 1e-7 N.
    # These tolerances test the spring derivative, not physical acceptance.
    step = 1e-5
    for vertex, force in forces.items():
        for axis in range(3):
            plus, minus = deepcopy(points), deepcopy(points)
            plus[vertex][axis] += step
            minus[vertex][axis] -= step
            derivative = (_energy(terms, plus) - _energy(terms, minus)) / (2 * step)
            assert force[axis] == pytest.approx(-derivative, abs=1e-7)
    for axis in range(3):
        assert abs(fsum(force[axis] for force in forces.values())) < 1e-10
    assert bundle["comparison_eligible"] is False
    assert result_fixture["data"]["v6_outcome"] == "NOT_RUN"
    assert result_fixture["data"]["verification_state"] == "NOT_VERIFIED"
    assert result_fixture["data"]["physical_status"] == "UNTESTED"


def test_wale_incidence_and_shape_rules_are_independent_of_initial_points(
    request_fixture,
    result_fixture,
):
    ir = request_fixture["crochet_ir"]
    run = request_fixture["forward_run"]
    rest = run["rest_parameters"]
    gauge = request_fixture["material_profile"]["calibration_responses"][0]["effective_gauge"]
    rings = {
        location["attachment_location_id"]
        for location in ir["attachment_locations"]
        if location["location_type"] == "MAGIC_RING_ANCHOR"
    }
    expected = {}
    for stitch in ir["stitches"]:
        for base in stitch["base_attachment_location_ids"]:
            for top in stitch["top_attachment_location_ids"]:
                if base in rings:
                    length, stiffness = rest["ring_rest_length_mm"], rest["ring_stiffness_n_per_mm"]
                else:
                    length = (
                        gauge["effective_course_pitch_mm"]
                        * rest["wale_rest_length_factors"][stitch["shaping"]]
                    )
                    stiffness = (
                        run["model_profile"]["stiffness_wale_n_per_mm"]
                        * rest["wale_stiffness_factors"][stitch["shaping"]]
                    )
                expected[base, top] = (length, stiffness)
    terms = result_fixture["data"]["experimental_forward_bundle"]["spring_terms"]
    actual = {
        (term["source_location_id"], term["target_location_id"]): (
            term["rest_length_mm"],
            term["stiffness_n_per_mm"],
        )
        for term in terms
        if term["edge_type"] == "WALE"
    }
    assert actual == expected
    changed = deepcopy(request_fixture)
    changed["forward_run"]["rest_parameters"]["ring_initial_offset_mm"] = 5.0
    result = BackendAPI(PROVENANCE).handle(changed)
    assert result["ok"], result
    bundle = result["data"]["experimental_forward_bundle"]
    assert bundle["spring_terms"] == terms
    assert (
        bundle["coordinates_mm"]
        != result_fixture["data"]["experimental_forward_bundle"]["coordinates_mm"]
    )


@pytest.mark.parametrize("mutation", ["generator", "seed", "target", "color"])
def test_api_source_binding_cannot_leak_into_physical_bundle(
    request_fixture,
    result_fixture,
    mutation,
):
    changed = deepcopy(request_fixture)
    ir = changed["crochet_ir"]
    if mutation == "generator":
        ir["provenance"]["generator"]["name"] = "different-source"
    elif mutation == "seed":
        ir["provenance"]["random_seed"] = 321
    elif mutation == "target":
        ir["provenance"]["input_artifacts"] = [
            {
                "artifact_id": "asset_different_target",
                "artifact_role": "TARGET_GEOMETRY",
                "sha256": "f" * 64,
            }
        ]
    else:
        ir["colors"][0]["srgb_hex"] = "#FF0000"
    result = BackendAPI(PROVENANCE).handle(changed)
    assert result["ok"], result
    assert (
        result["data"]["source_crochet_ir_sha256"]
        != result_fixture["data"]["source_crochet_ir_sha256"]
    )
    assert (
        result["data"]["experimental_forward_bundle"]
        == result_fixture["data"]["experimental_forward_bundle"]
    )


def test_wire_and_reopened_isolated_job_preserve_exact_bundle(
    request_fixture,
    result_fixture,
    tmp_path,
):
    api = BackendAPI(PROVENANCE)
    assert api.handle_json(jcs_bytes(request_fixture)) == result_fixture
    store = JobStore(tmp_path / "shaped.sqlite3")
    job = store.submit(jcs_bytes(request_fixture), "shaped-forward")
    assert execute_one_isolated(store, api, max_wall_seconds=30)
    restored = JobStore(tmp_path / "shaped.sqlite3").get(job)
    assert restored["status"] == "SUCCEEDED"
    assert restored["result"] == result_fixture


@pytest.mark.parametrize("field", ["target_geometry", "coordinates_mm", "embedding"])
def test_external_coordinate_override_returns_error_without_bundle(request_fixture, field):
    changed = deepcopy(request_fixture)
    changed["forward_run"][field] = {}
    result = BackendAPI(PROVENANCE).handle(changed)
    assert result["ok"] is False
    assert result["error"]["code"] == "E_INPUT"
    assert "data" not in result
