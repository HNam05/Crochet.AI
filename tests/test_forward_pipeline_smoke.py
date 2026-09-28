from __future__ import annotations

from typing import Any

import pytest
from conftest import resolved_artifacts

from crochet_ai.analytic_compile import (
    CompileProvenance,
    compile_closed_schedule,
)
from crochet_ai.forward_cells import (
    ForwardSurfaceCellsError,
    build_forward_surface_cells,
)
from crochet_ai.forward_graph import lower_forward_graph
from crochet_ai.forward_initialization import initialize_forward_graph
from crochet_ai.forward_inputs import ForwardInputs, admit_forward_inputs
from crochet_ai.forward_triangle_geometry import diagnose_initial_triangle_geometry
from crochet_ai.forward_triangulation import triangulate_forward_surface_cells
from crochet_ai.physical_projection import PhysicalSemanticProjection
from crochet_ai.validation import SemanticValidator


def _forward_inputs() -> ForwardInputs:
    loading = {
        "schema_version": "1.0.0",
        "loading_profile_id": "loading-pipeline-smoke-unloaded",
        "state": "UNLOADED_UNPRESSURIZED",
    }
    model = {
        "schema_version": "1.0.0",
        "model_profile_id": "pipeline-smoke-f0-hypothesis",
        "status": "HYPOTHESIS",
        "source_provenance_id": "pipeline-smoke-study",
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
        "config_id": "pipeline-smoke-initialization-v1",
        "model_version": "F0_STRETCH_PROTOTYPE",
        "work_budgets": {
            "max_initializations": 1,
            "max_initialization_vertices": 100,
            "max_line_search_trials": 10,
            "max_optimizer_iterations": 10,
            "max_energy_evaluations": 20,
            "max_linear_iterations": 30,
            "max_contact_pairs_evaluated": 40,
        },
        "tolerances": {
            name: {
                "value": 0.01,
                "unit": unit,
                "rationale": f"Experimental smoke-fixture threshold for {name}.",
                "owner": "forward-model",
                "validation_path_id": f"pipeline-smoke-{name}",
            }
            for name, unit in units.items()
        },
    }
    return admit_forward_inputs(loading, model, config)


def _compile(phases: tuple[int, int]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    design, material = resolved_artifacts()
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    crochet_ir = compile_closed_schedule(
        design,
        material,
        (6, 6, 6),
        phases,
        CompileProvenance("a" * 40, "b" * 64, (("fixture", "pipeline-smoke"),)),
        max_stitches=100,
    )
    return design, material, crochet_ir


def _run_pipeline(phases: tuple[int, int]) -> tuple[Any, ...]:
    design, material, crochet_ir = _compile(phases)
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={material["profile_id"]: material},
    )
    assert validator.validate_crochet_ir(crochet_ir).ok

    projection = PhysicalSemanticProjection(crochet_ir, material, validator=validator)
    graph = lower_forward_graph(
        projection,
        material,
        "tension_fixture_default",
        "RELAXED_UNSTUFFED",
        validator=validator,
    )
    inputs = _forward_inputs()
    initialization = initialize_forward_graph(projection, graph, inputs)
    cells = build_forward_surface_cells(projection, graph)
    triangulation = triangulate_forward_surface_cells(cells)
    diagnostic = diagnose_initial_triangle_geometry(cells, triangulation, initialization)
    return crochet_ir, projection, graph, inputs, initialization, cells, triangulation, diagnostic


def test_closed_compilation_preserves_open_surface_and_is_deterministic() -> None:
    first = _run_pipeline((0, 0))
    second = _run_pipeline((0, 0))
    _, projection, graph, inputs, initialization, cells, triangulation, diagnostic = first
    (
        _,
        projection_again,
        graph_again,
        inputs_again,
        initialization_again,
        cells_again,
        triangulation_again,
        diagnostic_again,
    ) = second

    assert graph.projection_sha256 == projection.sha256
    assert any(operation.operation_type == "CLOSE" for operation in graph.construction_operations)
    assert cells.projection_sha256 == projection.sha256
    assert cells.material_sha256 == graph.material_sha256
    assert initialization.projection_sha256 == projection.sha256
    assert initialization.material_sha256 == graph.material_sha256
    assert initialization.forward_inputs_sha256 == inputs.sha256
    assert cells.status == "EXPERIMENTAL_TOPOLOGY"
    assert triangulation.status == "EXPERIMENTAL_TOPOLOGY"
    assert triangulation.source_cells_sha256 == cells.sha256
    assert diagnostic.status == "INITIAL_COORDINATE_DIAGNOSTIC_ONLY"
    assert diagnostic.source_triangulation_sha256 == triangulation.sha256
    assert diagnostic.projection_sha256 == projection.sha256
    assert diagnostic.material_sha256 == graph.material_sha256
    assert len(cells.cells) == 12
    assert len(triangulation.triangles) == 24
    assert len(cells.lower_boundary_location_ids) == 6
    assert len(cells.upper_boundary_location_ids) == 6
    assert len(set(cells.lower_boundary_location_ids)) == 6
    assert len(set(cells.upper_boundary_location_ids)) == 6
    assert set(cells.lower_boundary_location_ids).isdisjoint(cells.upper_boundary_location_ids)
    assert all(metric.area_mm2 > 0 for metric in diagnostic.triangles)
    assert len(diagnostic.triangles) == 24
    assert first == second
    assert projection_again.sha256 == projection.sha256
    assert graph_again == graph
    assert inputs_again.sha256 == inputs.sha256
    assert initialization_again == initialization
    assert cells_again == cells
    assert triangulation_again == triangulation
    assert diagnostic_again == diagnostic


def test_phase_shifted_compilation_fails_closed_at_surface_cell_admission() -> None:
    design, material, crochet_ir = _compile((1, 0))
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={material["profile_id"]: material},
    )
    assert validator.validate_crochet_ir(crochet_ir).ok
    projection = PhysicalSemanticProjection(crochet_ir, material, validator=validator)
    graph = lower_forward_graph(
        projection,
        material,
        "tension_fixture_default",
        "RELAXED_UNSTUFFED",
        validator=validator,
    )
    with pytest.raises(ForwardSurfaceCellsError, match="phase_mismatch"):
        build_forward_surface_cells(projection, graph)
