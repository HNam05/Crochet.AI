from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

import pytest
from conftest import make_increase_ir, resolved_artifacts, resolved_validator
from ring_fixtures import make_multi_ring_ir

from crochet_ai.forward_graph import (
    ForwardGraph,
    GraphEdge,
    GraphNode,
    StitchMaterialResponse,
    StitchShapingGroup,
    lower_forward_graph,
)
from crochet_ai.forward_inputs import ForwardInputs, admit_forward_inputs
from crochet_ai.forward_stretch import (
    ForwardStretchError,
    _stretch_energy_n_mm,
    prepare_stretch_terms,
)
from crochet_ai.physical_projection import PhysicalSemanticProjection


def _inputs() -> ForwardInputs:
    loading = {
        "schema_version": "1.0.0",
        "loading_profile_id": "loading-unloaded-v1",
        "state": "UNLOADED_UNPRESSURIZED",
    }
    model = {
        "schema_version": "1.0.0",
        "model_profile_id": "f0-stretch-hypothesis-v1",
        "status": "HYPOTHESIS",
        "source_provenance_id": "stretch-prototype-study-01",
        "stiffness_course_n_per_mm": 0.8,
        "stiffness_wale_n_per_mm": 0.4,
    }
    units = {
        "force_residual_n": "N",
        "position_step_mm": "mm",
        "relative_energy_change": "dimensionless",
        "contact_penetration_mm": "mm",
        "volume_orientation_epsilon_mm3": "mm^3",
        "mode_equivalence_rms_mm": "mm",
    }
    config = {
        "schema_version": "1.0.0",
        "config_id": "stretch-prototype-run-v1",
        "model_version": "F0_STRETCH_PROTOTYPE",
        "work_budgets": {
            "max_initializations": 1,
            "max_initialization_vertices": 100,
            "max_optimizer_iterations": 10,
            "max_energy_evaluations": 20,
            "max_line_search_trials": 10,
            "max_linear_iterations": 30,
            "max_contact_pairs_evaluated": 40,
        },
        "tolerances": {
            name: {
                "value": 0.01,
                "unit": unit,
                "rationale": f"Experimental fixture threshold for {name}.",
                "owner": "forward-model",
                "validation_path_id": f"fixture-{name}",
            }
            for name, unit in units.items()
        },
    }
    return admit_forward_inputs(loading, model, config)


def _lower(value: dict[str, Any] | None = None) -> ForwardGraph:
    source = make_multi_ring_ir() if value is None else value
    _, material = resolved_artifacts()
    projection = PhysicalSemanticProjection(source, material, validator=resolved_validator())
    graph = lower_forward_graph(
        projection,
        material,
        "tension_fixture_default",
        "RELAXED_UNSTUFFED",
        validator=resolved_validator(),
    )
    return graph


def _top_to_top_graph() -> ForwardGraph:
    return ForwardGraph(
        projection_sha256="a" * 64,
        material_sha256="b" * 64,
        nodes=(
            GraphNode("anchor", "MAGIC_RING_ANCHOR"),
            GraphNode("top_a", "TOP_LOOP"),
            GraphNode("top_b", "TOP_LOOP"),
        ),
        shaping_groups=(
            StitchShapingGroup("stitch_a", "PLAIN", ("anchor",), ("top_a",), 1, 1),
            StitchShapingGroup("stitch_b", "PLAIN", ("top_a",), ("top_b",), 1, 1),
        ),
        edges=(
            GraphEdge("COURSE", "top_a", "top_b", "course_1"),
            GraphEdge("WALE", "top_a", "top_b", "course_1", "stitch_b"),
            GraphEdge("WALE", "anchor", "top_a", "course_0", "stitch_a"),
        ),
        yarn_path_links=(),
        construction_operations=(),
        frontier_boundaries=(),
        material_responses=(
            StitchMaterialResponse("stitch_a", "response_a", 4.0, 3.5, 0.1, 0.1),
            StitchMaterialResponse("stitch_b", "response_b", 5.0, 6.0, 0.1, 0.1),
        ),
    )


def test_ring_prepares_course_terms_and_skips_ring_anchor_wales() -> None:
    graph = _lower()
    prepared = prepare_stretch_terms(graph, _inputs())
    assert prepared.status == "EXPERIMENTAL_STRETCH_TERMS"
    assert prepared.material_sha256 == graph.material_sha256
    assert len(prepared.terms) == 6
    assert {term.edge_type for term in prepared.terms} == {"COURSE"}
    assert all(term.rest_length_mm == 4.0 for term in prepared.terms)
    assert all(term.stiffness_n_per_mm == 0.8 for term in prepared.terms)
    assert all(term.response_id.startswith("mr_") for term in prepared.terms)
    assert not any(term.source_location_id.startswith("loc_ring_") for term in prepared.terms)


def test_top_to_top_wale_uses_course_pitch_and_wale_stiffness() -> None:
    prepared = prepare_stretch_terms(_top_to_top_graph(), _inputs())
    course, wale = prepared.terms
    assert (course.edge_type, course.rest_length_mm, course.stiffness_n_per_mm) == (
        "COURSE",
        4.0,
        0.8,
    )
    assert (course.source_location_id, course.response_id) == ("top_a", "response_a")
    assert (wale.edge_type, wale.rest_length_mm, wale.stiffness_n_per_mm) == (
        "WALE",
        6.0,
        0.4,
    )
    assert (wale.source_location_id, wale.target_location_id, wale.response_id) == (
        "top_a",
        "top_b",
        "response_b",
    )


def test_increase_is_rejected_before_term_assignment() -> None:
    with pytest.raises(ForwardStretchError, match="unsupported_shaping"):
        prepare_stretch_terms(_lower(make_increase_ir()), _inputs())


def test_input_order_and_excluded_target_provenance_do_not_change_terms() -> None:
    original_ir = make_multi_ring_ir()
    original = prepare_stretch_terms(_lower(original_ir), _inputs())

    changed = deepcopy(original_ir)
    for table in changed.values():
        if isinstance(table, list) and table and isinstance(table[0], dict):
            table.reverse()
    changed["provenance"]["input_artifacts"] = [
        {
            "artifact_id": "asset_changed",
            "artifact_role": "TARGET_GEOMETRY",
            "sha256": "f" * 64,
        }
    ]
    reordered = prepare_stretch_terms(_lower(changed), _inputs())
    assert reordered.terms == original.terms
    assert reordered.projection_sha256 == original.projection_sha256


def test_missing_and_ambiguous_material_or_producer_mapping_fails_closed() -> None:
    graph = _top_to_top_graph()
    without_source_response = replace(
        graph,
        material_responses=(graph.material_responses[1],),
    )
    with pytest.raises(ForwardStretchError, match="material_response_missing"):
        prepare_stretch_terms(without_source_response, _inputs())

    duplicate_producer = replace(
        graph,
        shaping_groups=(
            *graph.shaping_groups,
            StitchShapingGroup("stitch_c", "PLAIN", ("anchor",), ("top_a",), 1, 1),
        ),
    )
    with pytest.raises(ForwardStretchError, match="ambiguous_top_producer"):
        prepare_stretch_terms(duplicate_producer, _inputs())

    invalid_ring_edge = replace(
        graph,
        edges=(
            graph.edges[0],
            graph.edges[1],
            replace(graph.edges[2], stitch_id="missing_stitch"),
        ),
    )
    with pytest.raises(ForwardStretchError, match="wale_producer_mismatch"):
        prepare_stretch_terms(invalid_ring_edge, _inputs())


def test_synthetic_exact_spring_energy() -> None:
    term = prepare_stretch_terms(_top_to_top_graph(), _inputs()).terms[0]
    energy = _stretch_energy_n_mm(
        (replace(term, rest_length_mm=2.0, stiffness_n_per_mm=3.0),),
        {"top_a": (0.0, 0.0), "top_b": (4.0, 0.0)},
    )
    assert energy == pytest.approx(6.0)


def test_synthetic_energy_requires_finite_complete_coordinates() -> None:
    term = prepare_stretch_terms(_top_to_top_graph(), _inputs()).terms[0]
    with pytest.raises(ForwardStretchError, match="coordinate_missing"):
        _stretch_energy_n_mm((term,), {"top_a": (0.0, 0.0)})
    with pytest.raises(ForwardStretchError, match="coordinate_non_finite"):
        _stretch_energy_n_mm((term,), {"top_a": (0.0, 0.0), "top_b": (float("nan"), 0.0)})
