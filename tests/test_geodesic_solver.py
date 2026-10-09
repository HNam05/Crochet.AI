from __future__ import annotations

import hashlib
from typing import Any

import pytest
import rfc8785
from conftest import resolved_artifacts
from test_v0_mesh_preflight import FRAME
from test_v0_mesh_preflight import _inputs as _mesh_inputs

from crochet_ai.analytic_compile import CompileProvenance
from crochet_ai.analytic_target import admit_analytic_target
from crochet_ai.analytic_target_surface import POLICY_PROFILE, sample_analytic_target_surface
from crochet_ai.canonical import CanonicalProfile, canonical_hash, parse_json
from crochet_ai.geodesic_solver import PROFILE, generate_geodesic_draft
from crochet_ai.schema import validate_schema
from crochet_ai.validation import SemanticValidator


def _source_mesh() -> tuple[dict[str, Any], dict[str, Any], bytes, int, int]:
    analytic_design, material = resolved_artifacts()
    analytic_design["dimensions"]["measurements"][0]["value_mm"] = 2.5
    analytic_design["dimensions"]["measurements"].append(
        {
            "measurement_id": "dim_polar",
            "semantic": "CUSTOM",
            "label": "Polar radius",
            "value_mm": 4.25,
            "tolerance_mm": 0,
        }
    )
    analytic_design["target_geometry"]["primitive"] = "ELLIPSOID"
    analytic_design["target_geometry"]["parameters"] = [
        {"parameter": "EQUATORIAL_RADIUS", "measurement_id": "dim_fixture_radius"},
        {"parameter": "POLAR_RADIUS", "measurement_id": "dim_polar"},
    ]
    analytic_design["target_geometry"]["origin_mm"] = [10.0, -3.0, 7.5]
    analytic_design["target_geometry"]["coordinate_frame"]["coordinate_frame_id"] = FRAME
    analytic_design["target_geometry"]["coordinate_frame"]["up_axis"] = "NEGATIVE_Y"
    analytic_design["target_geometry"]["coordinate_frame"]["front_axis"] = "POSITIVE_X"
    validator = SemanticValidator(material_profiles={material["profile_id"]: material})
    target = admit_analytic_target(analytic_design, validator)
    sampled = sample_analytic_target_surface(
        analytic_design,
        target,
        {
            "profile": POLICY_PROFILE,
            "schema_version": "1.0.0",
            "ring_count": 4,
            "azimuth_sectors": 6,
        },
        validator=validator,
    )
    mesh = parse_json(sampled.sampled_mesh_jcs_bytes)
    vertices = mesh["vertices"]
    # Deterministic, small, pole-preserving perturbation removes rotational ties.
    for index, vertex in enumerate(vertices):
        if index in (sampled.start_pole_vertex, sampled.end_pole_vertex):
            continue
        point = vertex["position_mm"]
        point[0] += ((index % 5) - 2) * 0.013
        point[1] += ((index % 7) - 3) * 0.009
        point[2] += ((index % 3) - 1) * 0.011
    source_bytes = rfc8785.dumps(mesh)
    return (
        analytic_design,
        material,
        source_bytes,
        sampled.start_pole_vertex,
        sampled.end_pole_vertex,
    )


def _inputs() -> tuple[dict[str, Any], dict[str, Any], bytes, int, int]:
    _analytic_design, _sample_material, source_bytes, start, end = _source_mesh()
    design_model, resolved_material = _mesh_inputs(source_bytes)
    design = design_model.to_dict()
    if "CLOSE" not in design["difficulty_constraints"]["allowed_construction_operations"]:
        design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    solver_options = design["solver_options"]
    solver_options["allowed_solver_families"].append("GEODESIC")
    solver_options["solver_family_preference"].append("GEODESIC")
    return design, resolved_material.to_dict(), source_bytes, start, end


def _config(source: bytes, start: int, end: int) -> dict[str, Any]:
    return {
        "profile": PROFILE,
        "schema_version": "1.0.0",
        "software_commit": "a" * 40,
        "parameter_profile_id": "solver_params_fixture_minimal",
        "random_seed": 0,
        "source_mesh_sha256": hashlib.sha256(source).hexdigest(),
        "start_pole_source_vertex_index": start,
        "end_pole_source_vertex_index": end,
        "tension_profile_id": "tension_fixture_default",
        "fabric_state": "RELAXED_UNSTUFFED",
        "count_window_radius": 3,
        "max_increases_per_course": 64,
        "max_decreases_per_course": 64,
        "max_graph_edge_visits": 100_000,
        "max_graph_heap_pops": 10_000,
        "max_level_intervals": 32,
        "max_contour_face_tests": 50_000,
        "max_count_values_per_course": 16,
        "max_dp_states_per_course": 64,
        "max_transition_evaluations": 50_000,
        "max_stitches": 10_000,
        "v0_budgets": {
            "max_bytes": 100_000,
            "max_vertices": 512,
            "max_faces": 1024,
            "max_vertex_pairs": 100_000,
            "max_face_pairs": 1_000_000,
            "max_distance_piece_pairs": 2_000_000,
            "max_lambda_bits": 512,
            "max_orientation_tests": 2_400_000,
            "max_openings": 16,
            "max_landmark_refs": 64,
            "max_landmarks": 32,
            "max_landmark_edge_tests": 16_384,
        },
    }


def _generate(
    design: dict[str, Any],
    material: dict[str, Any],
    source: bytes,
    config: dict[str, Any],
    *,
    provenance: CompileProvenance | None = None,
) -> dict[str, Any]:
    compile_provenance = provenance or CompileProvenance(
        str(config["software_commit"]),
        hashlib.sha256(b"test implementation snapshot").hexdigest(),
        (("fixture", True),),
    )
    return generate_geodesic_draft(design, material, source, config, provenance=compile_provenance)


def _run() -> tuple[dict[str, Any], dict[str, Any]]:
    design, material, source, start, end = _inputs()
    result = _generate(design, material, source, _config(source, start, end))
    return result, design


def test_closed_mesh_emits_deterministic_semantically_valid_geodesic_draft() -> None:
    result, design = _run()
    repeat, _ = _run()
    assert result == repeat
    assert result["status"] == "CANDIDATES_EMITTED", (
        result.get("status"),
        result.get("reason_code"),
        result.get("reason"),
    )
    assert result["verification_state"] == "NOT_VERIFIED"
    assert result["physical_status"] == "UNTESTED"
    assert result["comparison_eligible"] is False
    assert result["geodesic_claim"] == "GRAPH_DISTANCE_APPROXIMATION_NOT_EXACT_SURFACE_GEODESIC"
    assert result["distance_interval_count"] >= 2
    assert len(result["contour_lengths_mm"]) == result["contour_count"]
    assert result["count_proposal"]["counts"] == [3, 3]
    assert result["work"]["contour_face_tests"] <= 50_000
    ir = result["candidate_crochet_ir"]
    ir_provenance = ir["provenance"]
    assert ir_provenance["generator"] == {
        "solver_family": "GEODESIC",
        "name": "geodesic-graph-distance-closed-sc",
        "version": "1",
    }
    assert ir_provenance["random_seed"] == design["solver_options"]["random_seed"]
    assert ir_provenance["search_budget"] == {
        "budget_type": "CANDIDATE_EVALUATIONS",
        "limit": design["solver_options"]["max_candidate_evaluations"],
        "consumed": 1,
        "exhausted": False,
    }
    material = _inputs()[1]
    assert design["material_profile"]["binding_type"] == "REFERENCE"
    assert design["material_profile"]["profile_id"] == material["profile_id"]
    assert design["material_profile"]["revision"] == material["revision"]
    assert result["material_profile_sha256"] == canonical_hash(
        material, CanonicalProfile.MATERIAL_PROFILE
    )
    assert result["design_spec_sha256"] == ir["design_spec_ref"]["sha256"]
    provenance_parameters = {
        item["name"]: item["value"] for item in ir["provenance"]["solver_parameters"]
    }
    assert provenance_parameters["compiler_generation_profile"] == "GEODESIC_CLOSED_SC_V1"
    assert (
        provenance_parameters["source_snapshot_sha256"]
        == result["implementation_source_snapshot_sha256"]
    )
    assert (
        provenance_parameters["geodesic_design_parameter_profile_id"]
        == "solver_params_fixture_minimal"
    )
    assert provenance_parameters["geodesic_design_random_seed"] == 0
    assert provenance_parameters["geodesic_design_max_candidate_evaluations"] == 1
    derivations = ir["derivations"]
    assert derivations
    assert all(item["method"] == "GEODESIC_COUPLING" for item in derivations)
    assert all(item["rule_id"] == "geodesic.graph-distance.closed-sc" for item in derivations)
    assert all(
        item["parameter_sha256"] == ir_provenance["solver_parameters_sha256"]
        for item in derivations
    )
    assert result["implementation_source_snapshot_sha256"] != result["source_mesh_sha256"]
    validator = SemanticValidator(
        material_profiles={material["profile_id"]: material},
        design_specs={design["design_spec_id"]: design},
    )
    assert validator.validate_crochet_ir(ir).ok
    assert validate_schema("crochet_ir", ir).ok
    assert ir["design_spec_ref"]["design_spec_id"] == design["design_spec_id"]


def test_source_vertex_reordering_preserves_normalized_anchor_and_draft_counts() -> None:
    design, material, source, start, end = _inputs()
    first = _generate(design, material, source, _config(source, start, end))
    mesh = parse_json(source)
    old_vertices = mesh["vertices"]
    order = list(reversed(range(len(old_vertices))))
    remap = {old: new for new, old in enumerate(order)}
    mesh["vertices"] = [old_vertices[index] for index in order]
    for face in mesh["faces"]:
        face["vertex_indices"] = [remap[index] for index in face["vertex_indices"]]
    reordered = rfc8785.dumps(mesh)
    reordered_start, reordered_end = remap[start], remap[end]
    reordered_design, _ = _mesh_inputs(reordered)
    changed = reordered_design.to_dict()
    if "CLOSE" not in changed["difficulty_constraints"]["allowed_construction_operations"]:
        changed["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    changed["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    changed["solver_options"]["allowed_solver_families"].append("GEODESIC")
    changed["solver_options"]["solver_family_preference"].append("GEODESIC")
    second = _generate(
        changed, material, reordered, _config(reordered, reordered_start, reordered_end)
    )
    assert second["status"] == "CANDIDATES_EMITTED", second
    assert second["count_proposal"]["counts"] == first["count_proposal"]["counts"]


@pytest.mark.parametrize(
    "bad_field", ["start_pole_source_vertex_index", "end_pole_source_vertex_index"]
)
def test_anchor_binding_range_and_coincidence_fail_closed(bad_field: str) -> None:
    design, material, source, start, end = _inputs()
    config = _config(source, start, end)
    config[bad_field] = 99_999
    result = _generate(design, material, source, config)
    assert result["status"] == "INVALID_SOLVER_INPUT"
    config["start_pole_source_vertex_index"] = start
    config["end_pole_source_vertex_index"] = start
    result = _generate(design, material, source, config)
    assert result["status"] == "INVALID_SOLVER_INPUT"
    assert result["candidate_crochet_ir"] is None


def test_source_hash_and_required_config_fields_are_strict() -> None:
    design, material, source, start, end = _inputs()
    config = _config(source, start, end)
    config["source_mesh_sha256"] = "0" * 64
    result = _generate(design, material, source, config)
    assert result["status"] == "INVALID_SOLVER_INPUT"
    config = _config(source, start, end)
    config["unreviewed_seed"] = 1
    assert _generate(design, material, source, config)["status"] == "INVALID_SOLVER_INPUT"


def test_design_solver_controls_are_admitted_before_geodesic_work() -> None:
    design, material, source, start, end = _inputs()
    config = _config(source, start, end)
    design["solver_options"]["allowed_solver_families"] = ["ANALYTIC"]
    result = _generate(design, material, source, config)
    assert result["status"] == "NOT_APPLICABLE"
    assert result["reason"] == "geodesic_solver_family_not_allowed"
    assert result["candidate_crochet_ir"] is None

    design, material, source, start, end = _inputs()
    config = _config(source, start, end)
    config["parameter_profile_id"] = "unbound_profile"
    result = _generate(design, material, source, config)
    assert result["status"] == "INVALID_SOLVER_INPUT"
    assert result["reason"] == "parameter_profile_mismatch"

    config = _config(source, start, end)
    config["random_seed"] = 1
    result = _generate(design, material, source, config)
    assert result["status"] == "INVALID_SOLVER_INPUT"
    assert result["reason"] == "random_seed_mismatch"


def test_compile_provenance_is_explicit_and_commit_bound() -> None:
    design, material, source, start, end = _inputs()
    config = _config(source, start, end)
    wrong_provenance = CompileProvenance(
        "b" * 40,
        hashlib.sha256(b"independent implementation snapshot").hexdigest(),
        (),
    )
    result = _generate(design, material, source, config, provenance=wrong_provenance)
    assert result["status"] == "INVALID_SOLVER_INPUT"
    assert result["reason_code"] == "PROVENANCE"
    assert result["reason"] == "software_commit_mismatch"


def test_v0_rejection_and_solver_work_exhaustion_never_emit_candidates() -> None:
    design, material, source, start, end = _inputs()
    open_mesh = parse_json(source)
    open_mesh["faces"].pop()
    open_source = rfc8785.dumps(open_mesh)
    open_design_model, _ = _mesh_inputs(open_source)
    invalid = _generate(
        open_design_model.to_dict(), material, open_source, _config(open_source, start, end)
    )
    assert invalid["status"] == "NOT_APPLICABLE"
    config = _config(source, start, end)
    config["max_graph_edge_visits"] = 1
    exhausted = _generate(design, material, source, config)
    assert exhausted["status"] == "SEARCH_BUDGET_EXHAUSTED", (
        exhausted.get("reason_code"),
        exhausted.get("reason"),
    )
    assert exhausted["candidate_crochet_ir"] is None
