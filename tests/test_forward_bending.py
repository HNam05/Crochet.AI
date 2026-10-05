from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest

from crochet_ai.canonical import jcs_bytes
from crochet_ai.forward_bending import (
    ForwardBendingError,
    admit_bending_parameters,
    evaluate_bending_terms,
    prepare_bending_terms,
)
from crochet_ai.forward_cells import ForwardSurfaceCells, SurfaceCell
from crochet_ai.forward_initialization import PROFILE as INIT_PROFILE
from crochet_ai.forward_initialization import ForwardInitialization
from crochet_ai.forward_inputs import ForwardInputs, admit_forward_inputs


def _inputs() -> ForwardInputs:
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
            "max_optimizer_iterations": 10,
            "max_energy_evaluations": 30,
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


def _seal_cells(
    cells: tuple[SurfaceCell, ...], lower: tuple[str, ...], upper: tuple[str, ...]
) -> ForwardSurfaceCells:
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
        "EXPERIMENTAL_TOPOLOGY", "1" * 64, "2" * 64, lower, upper, cells, encoded, digest
    )


def _initialization(inputs: ForwardInputs) -> ForwardInitialization:
    points = (
        ("a", (0.0, 0.0, 0.0)),
        ("b", (1.0, 0.0, 0.0)),
        ("c", (1.0, 0.0, 1.0)),
        ("d", (0.0, 0.0, 1.0)),
        ("v", (1.0, 1.0, 1.0)),
        ("w", (0.0, 1.0, 1.0)),
        ("x", (1.0, 1.0, 0.0)),
        ("y", (0.0, 1.0, 0.0)),
    )
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
    return ForwardInitialization(
        "EXPERIMENTAL_INITIALIZATION",
        "1" * 64,
        "2" * 64,
        inputs.sha256,
        (),
        points,
        encoded,
        digest,
    )


def _artifacts():
    inputs = _inputs()
    cells = _cells()
    initialization = _initialization(inputs)
    parameters = admit_bending_parameters("calibration-fixture-v1", 0.0, 2.0)
    terms = prepare_bending_terms(cells, initialization, parameters, inputs)
    return inputs, cells, initialization, parameters, terms


def test_rest_energy_is_zero_fold_energy_positive_and_reproducible() -> None:
    inputs, cells, initialization, _, terms = _artifacts()
    rest = dict(initialization.coordinates_mm)
    assert evaluate_bending_terms(terms, rest).energy_n_mm == 0.0
    changed_parameters = admit_bending_parameters("calibration-fixture-v1", 0.2, 2.0)
    changed_rest = prepare_bending_terms(cells, initialization, changed_parameters, inputs)
    assert evaluate_bending_terms(changed_rest, rest).energy_n_mm > 0.0
    folded = dict(rest)
    folded["d"] = (0.0, 0.25, 1.0)
    result = evaluate_bending_terms(terms, folded)
    assert result.energy_n_mm > 0.0
    assert terms.canonical_bytes == _artifacts()[4].canonical_bytes


def test_analytic_force_matches_finite_difference_and_rigid_motion() -> None:
    _, _, initialization, _, terms = _artifacts()
    points = dict(initialization.coordinates_mm)
    points["d"] = (0.0, 0.25, 1.0)
    result = evaluate_bending_terms(terms, points)
    epsilon = 1e-6
    perturbed = dict(points)
    perturbed["d"] = (0.0, 0.25 + epsilon, 1.0)
    derivative = (
        evaluate_bending_terms(terms, perturbed).energy_n_mm - result.energy_n_mm
    ) / epsilon
    assert -derivative == pytest.approx(dict(result.forces_n)["d"][1], rel=2e-5, abs=1e-7)

    moved = {
        key: (point[1] + 4.0, -point[0] + 2.0, point[2] - 3.0) for key, point in points.items()
    }
    moved_result = evaluate_bending_terms(terms, moved)
    assert moved_result.energy_n_mm == pytest.approx(result.energy_n_mm)
    expected = {key: (force[1], -force[0], force[2]) for key, force in result.forces_n}
    assert dict(moved_result.forces_n) == pytest.approx(expected)


def test_bending_gradient_matches_central_difference_at_every_coordinate() -> None:
    _, _, initialization, _, terms = _artifacts()
    points = dict(initialization.coordinates_mm)
    points["d"] = (0.0, 0.25, 1.0)
    points["v"] = (1.1, 1.0, 1.2)
    forces = dict(evaluate_bending_terms(terms, points).forces_n)
    step_mm = 1e-6
    for key in sorted(points):
        for axis in range(3):
            plus, minus = dict(points), dict(points)
            positive, negative = list(points[key]), list(points[key])
            positive[axis] += step_mm
            negative[axis] -= step_mm
            plus[key], minus[key] = tuple(positive), tuple(negative)
            derivative = (
                evaluate_bending_terms(terms, plus).energy_n_mm
                - evaluate_bending_terms(terms, minus).energy_n_mm
            ) / (2.0 * step_mm)
            assert -derivative == pytest.approx(forces[key][axis], rel=5e-5, abs=1e-6)


def test_parameter_initialization_and_topology_tampering_fail_closed() -> None:
    inputs, cells, initialization, parameters, terms = _artifacts()
    forged_parameters = replace(parameters, provenance_id="forged")
    with pytest.raises(ForwardBendingError, match="parameters_integrity"):
        prepare_bending_terms(cells, initialization, forged_parameters, inputs)
    forged_terms = replace(terms, parameters_sha256="f" * 64)
    with pytest.raises(ForwardBendingError, match="terms_integrity"):
        evaluate_bending_terms(forged_terms, dict(initialization.coordinates_mm))
    altered_cell = replace(cells.cells[0], attachment_location_ids=("a", "c", "b", "d"))
    altered_cells = _seal_cells(
        (altered_cell, *cells.cells[1:]),
        cells.lower_boundary_location_ids,
        cells.upper_boundary_location_ids,
    )
    with pytest.raises(ForwardBendingError, match="triangulation"):
        prepare_bending_terms(altered_cells, initialization, parameters, inputs)


def test_degenerate_faces_and_pi_branch_are_rejected() -> None:
    _, _, initialization, _, terms = _artifacts()
    rest = dict(initialization.coordinates_mm)
    degenerate = dict(rest)
    degenerate["d"] = degenerate["a"]
    with pytest.raises(ForwardBendingError, match="face_degenerate"):
        evaluate_bending_terms(terms, degenerate)
    skinny = dict(rest)
    skinny["b"] = (0.5, 1e-12, 0.5)
    with pytest.raises(ForwardBendingError, match="face_skinny"):
        evaluate_bending_terms(terms, skinny)
    branch = dict(rest)
    branch["d"] = (0.0, 0.0, -1.0)
    with pytest.raises(ForwardBendingError, match="angle_branch_ambiguous"):
        evaluate_bending_terms(terms, branch)
