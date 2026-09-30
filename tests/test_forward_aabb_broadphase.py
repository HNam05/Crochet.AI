from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from math import inf, nextafter
from typing import Any

import pytest

from crochet_ai.canonical import jcs_bytes
from crochet_ai.forward_aabb_broadphase import (
    ForwardAABBBroadphaseError,
    TriangleAABB,
    _overlaps_inclusive,
    diagnose_initial_aabb_candidates,
)
from crochet_ai.forward_cells import ForwardSurfaceCells, SurfaceCell
from crochet_ai.forward_initialization import ForwardInitialization
from crochet_ai.forward_inputs import ForwardInputs, admit_forward_inputs
from crochet_ai.forward_triangulation import triangulate_forward_surface_cells

PROJECTION = "a" * 64
MATERIAL = "b" * 64


def _inputs(budget: int = 28) -> ForwardInputs:
    loading = {
        "schema_version": "1.0.0",
        "loading_profile_id": "aabb-loading",
        "state": "UNLOADED_UNPRESSURIZED",
    }
    model = {
        "schema_version": "1.0.0",
        "model_profile_id": "aabb-model",
        "status": "HYPOTHESIS",
        "source_provenance_id": "aabb-study",
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
        "config_id": "aabb-config",
        "model_version": "F0_STRETCH_PROTOTYPE",
        "work_budgets": {
            "max_initializations": 1,
            "max_initialization_vertices": 100,
            "max_line_search_trials": 10,
            "max_optimizer_iterations": 10,
            "max_energy_evaluations": 20,
            "max_linear_iterations": 30,
            "max_contact_pairs_evaluated": budget,
        },
        "tolerances": {
            name: {
                "value": 0.01,
                "unit": unit,
                "rationale": f"AABB fixture tolerance metadata for {name}.",
                "owner": "forward-model",
                "validation_path_id": f"aabb-{name}",
            }
            for name, unit in units.items()
        },
    }
    return admit_forward_inputs(loading, model, config)


def _source() -> ForwardSurfaceCells:
    lower = tuple(f"lower_{index}" for index in range(4))
    upper = tuple(f"upper_{index}" for index in range(4))
    cells = tuple(
        SurfaceCell(
            "course_lower",
            "course_upper",
            index,
            (lower[index], lower[(index + 1) % 4], upper[(index + 1) % 4], upper[index]),
        )
        for index in range(4)
    )
    payload: dict[str, Any] = {
        "profile": "FORWARD_SURFACE_CELLS_V1",
        "status": "EXPERIMENTAL_TOPOLOGY",
        "projection_sha256": PROJECTION,
        "material_sha256": MATERIAL,
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
        "EXPERIMENTAL_TOPOLOGY", PROJECTION, MATERIAL, lower, upper, cells, encoded, digest
    )


def _coordinates(offset: float = 0.0) -> tuple[tuple[str, tuple[float, float, float]], ...]:
    square = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    rows = [
        (f"lower_{index}", (point[0] + offset, point[1] + offset, offset))
        for index, point in enumerate(square)
    ]
    rows.extend(
        (f"upper_{index}", (point[0] + offset, point[1] + offset, 1.0 + offset))
        for index, point in enumerate(square)
    )
    return tuple(sorted(rows))


def _initialization(
    inputs: ForwardInputs,
    coordinates: tuple[tuple[str, tuple[float, float, float]], ...] | None = None,
    *,
    forward_inputs_sha256: str | None = None,
) -> ForwardInitialization:
    rows = _coordinates() if coordinates is None else coordinates
    input_hash = inputs.sha256 if forward_inputs_sha256 is None else forward_inputs_sha256
    payload: dict[str, Any] = {
        "profile": "FORWARD_STRETCH_INITIALIZATION_V1",
        "status": "EXPERIMENTAL_INITIALIZATION",
        "projection_sha256": PROJECTION,
        "material_sha256": MATERIAL,
        "forward_inputs_sha256": input_hash,
        "anchor_location_groups": [[]],
        "coordinates_mm": [
            {"attachment_location_id": identifier, "xyz_mm": list(point)}
            for identifier, point in rows
        ],
    }
    encoded = jcs_bytes(payload)
    digest = sha256(
        b"Crochet.AI\0FORWARD_STRETCH_INITIALIZATION_V1\0" + encoded
    ).hexdigest()
    return ForwardInitialization(
        "EXPERIMENTAL_INITIALIZATION",
        PROJECTION,
        MATERIAL,
        input_hash,
        ((),),
        rows,
        encoded,
        digest,
    )


def _run(
    *,
    budget: int = 28,
    offset: float = 0.0,
    coordinates: tuple[tuple[str, tuple[float, float, float]], ...] | None = None,
) -> Any:
    inputs = _inputs(budget)
    source = _source()
    triangulation = triangulate_forward_surface_cells(source)
    initialization = _initialization(
        inputs, _coordinates(offset) if coordinates is None else coordinates
    )
    return diagnose_initial_aabb_candidates(source, triangulation, initialization, inputs)


def test_enumerates_all_pairs_and_keeps_adjacent_faces() -> None:
    result = _run()

    assert result.status == "CANDIDATES_ONLY"
    assert result.unordered_aabb_comparisons == 8 * 7 // 2
    assert [box.face_index for box in result.face_aabbs] == list(range(8))
    adjacent = next(
        pair
        for pair in result.candidate_pairs
        if (pair.first_face_index, pair.second_face_index) == (0, 1)
    )
    assert adjacent.shared_location_count == 2
    assert adjacent.shared_location_ids == ("lower_0", "upper_1")


def test_inclusive_touching_and_one_ulp_separation() -> None:
    box = TriangleAABB(0, (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    touching = TriangleAABB(1, (1.0, 0.25, 0.25), (2.0, 0.75, 0.75))
    separated = TriangleAABB(2, (nextafter(1.0, inf), 0.25, 0.25), (2.0, 0.75, 0.75))

    assert _overlaps_inclusive(box, touching)
    assert not _overlaps_inclusive(box, separated)


def test_negative_translation_is_preserved_and_hash_bound() -> None:
    base = _run()
    translated = _run(offset=-10.0)

    assert translated.face_aabbs[0].minimum_mm == (-10.0, -10.0, -10.0)
    assert translated.sha256 != base.sha256
    assert translated.canonical_bytes != base.canonical_bytes


@pytest.mark.parametrize("scale", [1e-200, 1e200])
def test_finite_coordinate_scale_does_not_require_binary64_area_metric(scale: float) -> None:
    coordinates = tuple(
        (identifier, tuple(value * scale for value in point))
        for identifier, point in _coordinates()
    )

    result = _run(coordinates=coordinates)

    assert result.unordered_aabb_comparisons == 28


def test_exact_budget_succeeds_and_one_under_fails_before_result() -> None:
    assert _run(budget=28).unordered_aabb_comparisons == 28
    with pytest.raises(ForwardAABBBroadphaseError, match="comparison_budget_exhausted"):
        _run(budget=27)


def test_input_budget_field_must_match_canonical_hashed_content() -> None:
    inputs = _inputs()
    tampered = replace(inputs, max_contact_pairs_evaluated=27)
    source = _source()
    initialization = _initialization(inputs)

    with pytest.raises(ForwardAABBBroadphaseError, match="forward_inputs_integrity"):
        diagnose_initial_aabb_candidates(
            source,
            triangulate_forward_surface_cells(source),
            initialization,
            tampered,
        )


def test_tampered_source_initialization_and_forward_input_binding_fail_closed() -> None:
    inputs = _inputs()
    source = _source()
    triangulation = triangulate_forward_surface_cells(source)
    initialization = _initialization(inputs)

    with pytest.raises(ForwardAABBBroadphaseError, match="initial_geometry_invalid"):
        diagnose_initial_aabb_candidates(
            replace(source, material_sha256="c" * 64), triangulation, initialization, inputs
        )
    with pytest.raises(ForwardAABBBroadphaseError, match="initial_geometry_invalid"):
        diagnose_initial_aabb_candidates(
            source,
            triangulation,
            replace(initialization, coordinates_mm=tuple(reversed(initialization.coordinates_mm))),
            inputs,
        )
    with pytest.raises(ForwardAABBBroadphaseError, match="forward_inputs_binding_mismatch"):
        diagnose_initial_aabb_candidates(
            source,
            triangulation,
            _initialization(inputs, forward_inputs_sha256="d" * 64),
            inputs,
        )


def test_identical_inputs_produce_identical_hashes() -> None:
    first = _run()
    second = _run()

    assert first.canonical_bytes == second.canonical_bytes
    assert first.sha256 == second.sha256
    assert _run(budget=29).sha256 != first.sha256
