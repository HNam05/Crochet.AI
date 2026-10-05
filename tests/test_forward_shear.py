from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest

from crochet_ai.canonical import jcs_bytes
from crochet_ai.forward_bending import (
    admit_bending_parameters,
    evaluate_bending_terms,
    prepare_bending_terms,
)
from crochet_ai.forward_cells import ForwardSurfaceCells, SurfaceCell
from crochet_ai.forward_initialization import PROFILE as INIT_PROFILE
from crochet_ai.forward_initialization import ForwardInitialization
from crochet_ai.forward_inputs import ForwardInputs, admit_forward_inputs
from crochet_ai.forward_shear import (
    ForwardShearError,
    admit_shear_parameters,
    evaluate_shear_terms,
    optimize_stretch_shear_bending_prototype,
    optimize_stretch_shear_prototype,
    prepare_shear_terms,
)
from crochet_ai.forward_stretch import ForwardStretchTerms, StretchTerm


def _inputs(max_energy: int = 30, max_iterations: int = 10) -> ForwardInputs:
    loading = {
        "schema_version": "1.0.0",
        "loading_profile_id": "load",
        "state": "UNLOADED_UNPRESSURIZED",
    }
    model = {
        "schema_version": "1.0.0",
        "model_profile_id": "hyp",
        "status": "HYPOTHESIS",
        "source_provenance_id": "fixture",
        "stiffness_course_n_per_mm": 1.0,
        "stiffness_wale_n_per_mm": 1.0,
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
        "config_id": "run",
        "model_version": "F0_STRETCH_PROTOTYPE",
        "work_budgets": {
            "max_initializations": 1,
            "max_initialization_vertices": 20,
            "max_optimizer_iterations": max_iterations,
            "max_energy_evaluations": max_energy,
            "max_line_search_trials": 8,
            "max_linear_iterations": 20,
            "max_contact_pairs_evaluated": 20,
        },
        "tolerances": {
            name: {
                "value": 0.01,
                "unit": unit,
                "rationale": "fixture threshold",
                "owner": "test",
                "validation_path_id": f"test-{name}",
            }
            for name, unit in units.items()
        },
    }
    return admit_forward_inputs(loading, model, config)


def _cells() -> ForwardSurfaceCells:
    lower = ("a", "b", "x", "y")
    upper = ("d", "c", "v", "w")
    cells = tuple(
        SurfaceCell(
            "lower",
            "upper",
            ordinal,
            (lower[ordinal], lower[(ordinal + 1) % 4], upper[(ordinal + 1) % 4], upper[ordinal]),
        )
        for ordinal in range(4)
    )
    return _seal_cells(cells, lower, upper)


def _seal_cells(cells, lower, upper) -> ForwardSurfaceCells:
    payload = {
        "profile": "FORWARD_SURFACE_CELLS_V1",
        "status": "EXPERIMENTAL_TOPOLOGY",
        "projection_sha256": "1" * 64,
        "material_sha256": "2" * 64,
        "lower_boundary_location_ids": list(lower),
        "upper_boundary_location_ids": list(upper),
        "cells": [
            {
                "lower_course_id": cell.lower_course_id,
                "upper_course_id": cell.upper_course_id,
                "ordinal": cell.ordinal,
                "attachment_location_ids": list(cell.attachment_location_ids),
            }
            for cell in cells
        ],
    }
    encoded = jcs_bytes(payload)
    digest = sha256(b"Crochet.AI\0FORWARD_SURFACE_CELLS_V1\0" + encoded).hexdigest()
    return ForwardSurfaceCells(
        "EXPERIMENTAL_TOPOLOGY",
        "1" * 64,
        "2" * 64,
        lower,
        upper,
        cells,
        encoded,
        digest,
    )


def _artifacts(max_energy: int = 30, max_iterations: int = 10):
    inputs = _inputs(max_energy, max_iterations)
    cells = _cells()
    shear = prepare_shear_terms(
        cells, admit_shear_parameters("calibration-fixture", 2.0, 0.5), inputs
    )
    points = (
        ("a", (0.0, 0.0, 0.0)),
        ("b", (1.0, 0.0, 0.0)),
        ("c", (1.0, 1.0, 0.0)),
        ("d", (0.0, 1.0, 0.0)),
        ("x", (-1.0, 0.0, 0.0)),
        ("y", (-1.0, -1.0, 0.0)),
        ("v", (-1.0, 1.0, 0.0)),
        ("w", (-2.0, -1.0, 0.0)),
    )
    points = tuple(sorted(points))
    payload = {
        "profile": INIT_PROFILE,
        "status": "EXPERIMENTAL_INITIALIZATION",
        "projection_sha256": "1" * 64,
        "material_sha256": "2" * 64,
        "forward_inputs_sha256": inputs.sha256,
        "anchor_location_groups": [],
        "coordinates_mm": [
            {"attachment_location_id": key, "xyz_mm": list(point)} for key, point in points
        ],
    }
    encoded = jcs_bytes(payload)
    digest = sha256(b"Crochet.AI\0" + INIT_PROFILE.encode() + b"\0" + encoded).hexdigest()
    init = ForwardInitialization(
        "EXPERIMENTAL_INITIALIZATION",
        "1" * 64,
        "2" * 64,
        inputs.sha256,
        (),
        points,
        encoded,
        digest,
    )
    stretch = ForwardStretchTerms(
        "EXPERIMENTAL_STRETCH_TERMS",
        "1" * 64,
        "2" * 64,
        inputs.sha256,
        (StretchTerm("COURSE", "a", "b", 1.0, 1.0, "r"),),
    )
    return inputs, cells, shear, init, stretch


def _first_cell_terms(terms):
    selected = replace(terms, terms=(terms.terms[0],))
    payload = {
        "profile": "FORWARD_SHEAR_TERMS_V1",
        "status": selected.status,
        "projection_sha256": selected.projection_sha256,
        "material_sha256": selected.material_sha256,
        "forward_inputs_sha256": selected.forward_inputs_sha256,
        "cells_sha256": selected.cells_sha256,
        "parameters_sha256": selected.parameters_sha256,
        "terms": [
            {
                "attachment_location_ids": list(term.attachment_location_ids),
                "rest_cosine": term.rest_cosine,
                "stiffness_n_mm": term.stiffness_n_mm,
            }
            for term in selected.terms
        ],
    }
    encoded = jcs_bytes(payload)
    digest = sha256(b"Crochet.AI\0FORWARD_SHEAR_TERMS_V1\0" + encoded).hexdigest()
    return replace(selected, canonical_bytes=encoded, sha256=digest)


def test_hand_derived_energy_and_nodal_forces() -> None:
    _, _, shear, init, _ = _artifacts()
    one_cell = _first_cell_terms(shear)
    coords = {key: dict(init.coordinates_mm)[key] for key in ("a", "b", "c", "d")}
    result = evaluate_shear_terms(one_cell, coords)
    assert result.energy_n_mm == pytest.approx(0.25)
    forces = dict(result.forces_n)
    assert forces["b"] == pytest.approx((0.0, 1.0, 0.0))
    assert forces["d"] == pytest.approx((1.0, 0.0, 0.0))
    assert forces["a"] == pytest.approx((-1.0, -1.0, 0.0))
    assert forces["c"] == (0.0, 0.0, 0.0)


def test_gradient_matches_finite_difference_and_rigid_motion_invariance() -> None:
    _, _, shear, init, _ = _artifacts()
    shear = _first_cell_terms(shear)
    coords = {key: dict(init.coordinates_mm)[key] for key in ("a", "b", "c", "d")}
    result = evaluate_shear_terms(shear, coords)
    epsilon = 1e-6
    changed = dict(coords)
    changed["b"] = (1.0, epsilon, 0.0)
    derivative = (evaluate_shear_terms(shear, changed).energy_n_mm - result.energy_n_mm) / epsilon
    assert -derivative == pytest.approx(dict(result.forces_n)["b"][1], rel=1e-5)
    moved = {key: (p[1] + 3.0, -p[0] + 2.0, p[2] - 7.0) for key, p in coords.items()}
    moved_result = evaluate_shear_terms(shear, moved)
    assert moved_result.energy_n_mm == pytest.approx(result.energy_n_mm)
    expected = {key: (force[1], -force[0], force[2]) for key, force in result.forces_n}
    assert dict(moved_result.forces_n) == pytest.approx(expected)


def test_parameter_and_terms_provenance_tampering_fails_closed() -> None:
    inputs, cells, shear, init, _ = _artifacts()
    shear = _first_cell_terms(shear)
    with pytest.raises(ForwardShearError, match="parameters_integrity"):
        prepare_shear_terms(
            cells, replace(admit_shear_parameters("p", 1.0, 0.0), provenance_id="forged"), inputs
        )
    forged = replace(shear, parameters_sha256="f" * 64)
    with pytest.raises(ForwardShearError, match="terms_integrity"):
        evaluate_shear_terms(forged, dict(init.coordinates_mm))
    forged_cells = replace(cells, cells=(replace(cells.cells[0], ordinal=2), *cells.cells[1:]))
    with pytest.raises(ForwardShearError, match="triangulation"):
        prepare_shear_terms(forged_cells, admit_shear_parameters("p", 1.0, 0.0), inputs)


def test_single_quad_without_supported_strip_topology_is_rejected() -> None:
    inputs = _inputs()
    cells = _cells()
    malformed = _seal_cells(
        (cells.cells[0],), cells.lower_boundary_location_ids, cells.upper_boundary_location_ids
    )
    with pytest.raises(ForwardShearError, match="triangulation"):
        prepare_shear_terms(malformed, admit_shear_parameters("p", 1.0, 0.0), inputs)


def test_invalid_parameters_degenerate_and_nonfinite_geometry_rejected() -> None:
    with pytest.raises(ForwardShearError, match="stiffness_invalid"):
        admit_shear_parameters("p", 0.0, 0.0)
    with pytest.raises(ForwardShearError, match="rest_cosine_invalid"):
        admit_shear_parameters("p", 1.0, 1.01)
    _, _, shear, init, _ = _artifacts()
    shear = _first_cell_terms(shear)
    coords = {key: dict(init.coordinates_mm)[key] for key in ("a", "b", "c", "d")}
    coords["b"] = coords["a"]
    with pytest.raises(ForwardShearError, match="degenerate_cell"):
        evaluate_shear_terms(shear, coords)
    coords["b"] = (float("inf"), 0.0, 0.0)
    with pytest.raises(ForwardShearError, match="coordinate_non_finite"):
        evaluate_shear_terms(shear, coords)


def test_combined_optimizer_is_deterministic_experimental_and_budgeted() -> None:
    inputs, _, shear, init, stretch = _artifacts()
    first = optimize_stretch_shear_prototype(stretch, shear, init, inputs)
    second = optimize_stretch_shear_prototype(stretch, shear, init, inputs)
    assert first.canonical_bytes == second.canonical_bytes
    assert first.projection_sha256 == shear.projection_sha256
    assert first.stretch_terms_sha256 != ""
    changed_stretch = replace(
        stretch,
        terms=(replace(stretch.terms[0], rest_length_mm=0.9),),
    )
    changed = optimize_stretch_shear_prototype(changed_stretch, shear, init, inputs)
    assert changed.sha256 != first.sha256
    assert changed.stretch_terms_sha256 != first.stretch_terms_sha256
    assert b'"initial_alpha_mm_per_n":1' in first.canonical_bytes
    assert first.status in {"EXPERIMENTAL_FORCE_BALANCED", "BUDGET_EXHAUSTED"}
    assert "CONVERGED" not in first.status
    limited, _, shear_limited, init_limited, stretch_limited = _artifacts(max_energy=1)
    exhausted = optimize_stretch_shear_prototype(
        stretch_limited, shear_limited, init_limited, limited
    )
    assert exhausted.status == "BUDGET_EXHAUSTED"
    assert exhausted.coordinates_mm is None
    assert exhausted.energy_evaluations == 1


def test_bending_hypothesis_rest_case_and_optimizer_drive() -> None:
    inputs, cells, shear, init, stretch = _artifacts(1000, 100)
    rest_parameters = admit_bending_parameters("bending-fixture", 0.0, 0.5)
    rest_terms = prepare_bending_terms(cells, init, rest_parameters, inputs)
    rest_energy = evaluate_bending_terms(rest_terms, dict(init.coordinates_mm)).energy_n_mm
    assert rest_energy == pytest.approx(0.0, abs=1e-12)

    bent_parameters = admit_bending_parameters("bending-fixture", 0.5, 0.5)
    bent_terms = prepare_bending_terms(cells, init, bent_parameters, inputs)
    initial_bending = evaluate_bending_terms(bent_terms, dict(init.coordinates_mm))
    assert initial_bending.energy_n_mm > 0.0
    assert initial_bending.maximum_force_n > 0.0
    result = optimize_stretch_shear_bending_prototype(stretch, shear, bent_terms, init, inputs)
    repeated = optimize_stretch_shear_bending_prototype(stretch, shear, bent_terms, init, inputs)
    assert result.canonical_bytes == repeated.canonical_bytes
    assert result.status.startswith("EXPERIMENTAL_")
    assert result.coordinates_mm is not None
    assert result.coordinates_mm != init.coordinates_mm
    assert result.energy_evaluations <= inputs.max_energy_evaluations
    assert result.bending_terms_sha256 == bent_terms.sha256
    assert result.projection_sha256 == init.projection_sha256
    assert result.material_sha256 == init.material_sha256
    assert result.forward_inputs_sha256 == init.forward_inputs_sha256


def test_bending_provenance_tamper_and_global_budget_fail_closed() -> None:
    inputs, cells, shear, init, stretch = _artifacts(1)
    parameters = admit_bending_parameters("bending-fixture", 0.5, 0.5)
    bending = prepare_bending_terms(cells, init, parameters, inputs)
    forged = replace(bending, initialization_sha256="f" * 64)
    with pytest.raises(ForwardShearError, match="bending_provenance_mismatch"):
        optimize_stretch_shear_bending_prototype(stretch, shear, forged, init, inputs)
    result = optimize_stretch_shear_bending_prototype(stretch, shear, bending, init, inputs)
    assert result.status == "BUDGET_EXHAUSTED"
    assert result.coordinates_mm is None
    assert result.energy_evaluations == inputs.max_energy_evaluations
    assert (
        result.canonical_bytes
        == optimize_stretch_shear_bending_prototype(
            stretch, shear, bending, init, inputs
        ).canonical_bytes
    )


def test_bending_artifact_tamper_returns_no_coordinates() -> None:
    inputs, cells, shear, init, stretch = _artifacts(30)
    parameters = admit_bending_parameters("bending-fixture", 0.5, 0.5)
    bending = prepare_bending_terms(cells, init, parameters, inputs)
    forged = replace(bending, parameters_sha256="f" * 64)
    result = optimize_stretch_shear_bending_prototype(stretch, shear, forged, init, inputs)
    assert result.status == "NUMERICAL_FAILURE"
    assert result.coordinates_mm is None
