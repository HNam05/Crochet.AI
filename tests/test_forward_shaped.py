from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from typing import Any

import pytest
from conftest import resolved_artifacts

from crochet_ai.analytic_compile import CompileProvenance, compile_closed_schedule
from crochet_ai.canonical import jcs_bytes, parse_json
from crochet_ai.forward_shaped import (
    PROFILE,
    ForwardShapedError,
    admit_shaped_forward_recipe,
    inspect_shaped_forward_model,
)
from crochet_ai.physical_projection import PROFILE as PHYSICAL_PROFILE
from crochet_ai.physical_projection import PhysicalSemanticProjection
from crochet_ai.validation import SemanticValidator


def _recipe() -> dict[str, Any]:
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
            "loading_profile_id": "load-test",
            "state": "UNLOADED_UNPRESSURIZED",
        },
        "model_profile": {
            "schema_version": "1.0.0",
            "model_profile_id": "model-test",
            "status": "HYPOTHESIS",
            "source_provenance_id": "study-test",
            "stiffness_course_n_per_mm": 0.8,
            "stiffness_wale_n_per_mm": 0.4,
        },
        "config": {
            "schema_version": "1.0.0",
            "config_id": "config-test",
            "model_version": "F0_STRETCH_PROTOTYPE",
            "work_budgets": {
                "max_initializations": 1,
                "max_initialization_vertices": 2048,
                "max_line_search_trials": 1,
                "max_optimizer_iterations": 1,
                "max_energy_evaluations": 1,
                "max_linear_iterations": 1,
                "max_contact_pairs_evaluated": 1,
            },
            "tolerances": {
                name: {
                    "value": 0.01,
                    "unit": unit,
                    "rationale": "Synthetic test fixture only.",
                    "owner": "test",
                    "validation_path_id": f"test-{name}",
                }
                for name, unit in units.items()
            },
        },
        "rest_parameters": {
            "schema_version": "1.0.0",
            "status": "HYPOTHESIS",
            "provenance_id": "synthetic-study",
            "wale_rest_length_factors": {"PLAIN": 0.9, "INCREASE": 1.1, "DECREASE": 0.8},
            "wale_stiffness_factors": {"PLAIN": 1.2, "INCREASE": 1.5, "DECREASE": 0.7},
            "ring_rest_length_mm": 0.7,
            "ring_stiffness_n_per_mm": 1.3,
            "ring_initial_chord_mm": 0.6,
            "ring_initial_offset_mm": 0.2,
        },
    }


def _setup(
    counts: tuple[int, ...],
) -> tuple[PhysicalSemanticProjection, dict[str, Any], SemanticValidator]:
    design, material = resolved_artifacts()
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    ir = compile_closed_schedule(
        design,
        material,
        counts,
        (0,) * (len(counts) - 1),
        CompileProvenance("a" * 40, "b" * 64, (("fixture", "forward-shaped"),)),
        max_stitches=100,
    )
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={(material["profile_id"], material["revision"]): material},
    )
    return (
        PhysicalSemanticProjection(ir, material, validator=validator),
        material,
        SemanticValidator(material_profiles={material["profile_id"]: material}),
    )


@pytest.mark.parametrize("counts", [(3, 3), (3, 4, 3), (4, 3, 4)])
def test_shaped_initial_diagnostic_is_deterministic_and_binds_all_vertices(
    counts: tuple[int, ...],
) -> None:
    projection, material, validator = _setup(counts)
    recipe = admit_shaped_forward_recipe(_recipe())
    one = inspect_shaped_forward_model(projection, material, recipe, validator=validator)
    two = inspect_shaped_forward_model(projection, material, recipe, validator=validator)
    assert one == two
    assert one["profile"] == PROFILE
    assert one["status"] == "EXPERIMENTAL_INITIAL_ELASTIC_DIAGNOSTIC"
    assert one["comparison_eligible"] is False
    assert one["verification_state"] == "NOT_VERIFIED"
    assert one["physical_status"] == "UNTESTED"
    assert {row["attachment_location_id"] for row in one["coordinates_mm"]} == set(
        projection.to_dict()["attachment_locations"][i]["attachment_location_id"]
        for i in range(len(projection.to_dict()["attachment_locations"]))
    )
    assert one["energy_n_mm"] > 0
    assert one["maximum_force_n"] > 0
    terms = one["spring_terms"]
    for term in terms:
        assert (
            (term["edge_type"] == "COURSE")
            or term["response_id"] == "ring-hypothesis"
            or term["stiffness_n_per_mm"] != 0.4
        )


@pytest.mark.parametrize(
    "path,value",
    [
        ("wale_rest_length_factors.PLAIN", True),
        ("ring_rest_length_mm", 0),
        ("ring_initial_offset_mm", float("inf")),
        ("ring_initial_chord_mm", 9_007_199_254_740_992),
    ],
)
def test_invalid_explicit_rest_parameters_are_rejected(path: str, value: object) -> None:
    doc = _recipe()
    obj = doc["rest_parameters"]
    if "." in path:
        parent, key = path.split(".")
        obj[parent][key] = value
    else:
        obj[path] = value
    with pytest.raises(ForwardShapedError):
        admit_shaped_forward_recipe(doc)


def test_forbidden_fields_and_forged_recipe_binding_fail_closed() -> None:
    prohibited = _recipe()
    prohibited["initial_coordinates"] = []
    with pytest.raises(ForwardShapedError, match="prohibited_target_field"):
        admit_shaped_forward_recipe(prohibited)
    recipe = admit_shaped_forward_recipe(_recipe())
    forged = replace(recipe, sha256="0" * 64)
    projection, material, validator = _setup((3, 4, 3))
    with pytest.raises(ForwardShapedError, match="binding_mismatch"):
        inspect_shaped_forward_model(projection, material, forged, validator=validator)


def test_recipe_canonicalization_binds_hypothesis_parameters() -> None:
    a = admit_shaped_forward_recipe(_recipe())
    changed = deepcopy(_recipe())
    changed["rest_parameters"]["wale_rest_length_factors"]["INCREASE"] = 1.2
    b = admit_shaped_forward_recipe(changed)
    assert a.sha256 != b.sha256
    assert parse_json(a.canonical_bytes)["rest_parameters"]["provenance_id"] == "synthetic-study"


def test_increase_and_decrease_bind_every_ordered_base_top_pair() -> None:
    projection, material, validator = _setup((3, 4, 3))
    result = inspect_shaped_forward_model(
        projection, material, admit_shaped_forward_recipe(_recipe()), validator=validator
    )
    terms = {
        (row["source_location_id"], row["target_location_id"])
        for row in result["spring_terms"]
        if row["edge_type"] == "WALE"
    }
    groups = [
        row
        for row in projection.to_dict()["stitches"]
        if row["shaping"] in {"INCREASE", "DECREASE"}
    ]
    assert groups
    for group in groups:
        expected = {
            (base, top)
            for base in group["base_attachment_location_ids"]
            for top in group["top_attachment_location_ids"]
        }
        assert expected <= terms


def test_exact_vertex_budget_passes_and_one_below_fails() -> None:
    projection, material, validator = _setup((3, 4, 3))
    exact_vertices = len(projection.to_dict()["attachment_locations"])
    recipe_doc = _recipe()
    recipe_doc["config"]["work_budgets"]["max_initialization_vertices"] = exact_vertices
    recipe = admit_shaped_forward_recipe(recipe_doc)
    result = inspect_shaped_forward_model(projection, material, recipe, validator=validator)
    assert len(result["coordinates_mm"]) == exact_vertices
    recipe_doc["config"]["work_budgets"]["max_initialization_vertices"] = exact_vertices - 1
    recipe = admit_shaped_forward_recipe(recipe_doc)
    with pytest.raises(ForwardShapedError, match="vertex_budget_exceeded") as error:
        inspect_shaped_forward_model(projection, material, recipe, validator=validator)
    assert error.value.code == "E_INPUT"


def test_overflowing_force_result_returns_error_without_bundle() -> None:
    projection, material, validator = _setup((3, 3))
    recipe_doc = _recipe()
    recipe_doc["rest_parameters"]["ring_stiffness_n_per_mm"] = 1.7e308
    recipe = admit_shaped_forward_recipe(recipe_doc)
    with pytest.raises(ForwardShapedError) as error:
        inspect_shaped_forward_model(projection, material, recipe, validator=validator)
    assert error.value.code == "E_FORWARD_DIVERGED"


def test_missing_ring_operation_is_rejected_before_graph_execution() -> None:
    projection, material, validator = _setup((3, 3))
    projected = projection.to_dict()
    projected["construction_operations"] = [
        row for row in projected["construction_operations"] if row["operation_type"] != "MAGIC_RING"
    ]
    encoded = jcs_bytes(projected)
    unsupported = object.__new__(PhysicalSemanticProjection)
    object.__setattr__(unsupported, "canonical_bytes", encoded)
    object.__setattr__(
        unsupported,
        "sha256",
        sha256(b"Crochet.AI\0" + PHYSICAL_PROFILE.encode() + b"\0" + encoded).hexdigest(),
    )
    with pytest.raises(ForwardShapedError) as error:
        inspect_shaped_forward_model(
            unsupported, material, admit_shaped_forward_recipe(_recipe()), validator=validator
        )
    assert error.value.code == "E_UNSUPPORTED_FEATURE"
    assert "unsupported_construction" in error.value.reason
