from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from math import inf
from typing import Any

import pytest

from crochet_ai.canonical import jcs_bytes
from crochet_ai.forward_cells import ForwardSurfaceCells, SurfaceCell
from crochet_ai.forward_initialization import ForwardInitialization
from crochet_ai.forward_triangle_geometry import (
    ForwardTriangleGeometryError,
    diagnose_initial_triangle_geometry,
)
from crochet_ai.forward_triangulation import triangulate_forward_surface_cells

PROJECTION = "a" * 64
MATERIAL = "b" * 64
INPUTS = "c" * 64


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


def _coordinates(
    *, height: float = 1.0
) -> tuple[tuple[str, tuple[float, float, float]], ...]:
    square = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))
    rows = [
        (f"lower_{index}", (point[0], point[1], 0.0))
        for index, point in enumerate(square)
    ]
    rows.extend(
        (f"upper_{index}", (point[0], point[1], height))
        for index, point in enumerate(square)
    )
    return tuple(sorted(rows))


def _initialization(
    coordinates: tuple[tuple[str, tuple[float, float, float]], ...] | None = None,
    *,
    projection: str = PROJECTION,
) -> ForwardInitialization:
    coordinate_rows = _coordinates() if coordinates is None else coordinates
    payload: dict[str, Any] = {
        "profile": "FORWARD_STRETCH_INITIALIZATION_V1",
        "status": "EXPERIMENTAL_INITIALIZATION",
        "projection_sha256": projection,
        "material_sha256": MATERIAL,
        "forward_inputs_sha256": INPUTS,
        "anchor_location_groups": [],
        "coordinates_mm": [
            {"attachment_location_id": identifier, "xyz_mm": list(point)}
            for identifier, point in coordinate_rows
        ],
    }
    encoded = jcs_bytes(payload)
    digest = sha256(b"Crochet.AI\0FORWARD_STRETCH_INITIALIZATION_V1\0" + encoded).hexdigest()
    return ForwardInitialization(
        "EXPERIMENTAL_INITIALIZATION",
        projection,
        MATERIAL,
        INPUTS,
        (),
        coordinate_rows,
        encoded,
        digest,
    )


def _run(
    coordinates: tuple[tuple[str, tuple[float, float, float]], ...] | None = None,
    *,
    initialization: ForwardInitialization | None = None,
) -> Any:
    source = _source()
    return diagnose_initial_triangle_geometry(
        source,
        triangulate_forward_surface_cells(source),
        _initialization(coordinates) if initialization is None else initialization,
    )


def test_handbuilt_two_course_source_reports_known_area_and_ordered_faces() -> None:
    result = _run()

    assert result.status == "INITIAL_COORDINATE_DIAGNOSTIC_ONLY"
    assert len(result.triangles) == 8
    assert [row.triangle_index for row in result.triangles[:2]] == [0, 1]
    assert all(row.area_mm2 == pytest.approx(0.5) for row in result.triangles)
    assert all(row.shape_quality == pytest.approx(0.5) for row in result.triangles)
    assert result.source_triangulation_sha256 == triangulate_forward_surface_cells(_source()).sha256


def test_result_hash_is_deterministic() -> None:
    assert _run().canonical_bytes == _run().canonical_bytes
    assert _run().sha256 == _run().sha256


def test_exactly_collinear_represented_triangle_is_rejected() -> None:
    coordinates = dict(_coordinates())
    coordinates["upper_1"] = (2.0, 0.0, 0.0)
    coordinates["upper_0"] = (0.0, 0.0, 0.0)
    coordinates["lower_1"] = (1.0, 0.0, 0.0)
    with pytest.raises(ForwardTriangleGeometryError, match="zero_area"):
        _run(tuple(sorted(coordinates.items())))


def test_area_overflow_and_subnormal_area_are_indeterminate() -> None:
    coordinates = dict(_coordinates())
    coordinates["upper_1"] = (1e200, 1e200, 0.0)
    coordinates["upper_0"] = (0.0, 1e200, 0.0)
    with pytest.raises(ForwardTriangleGeometryError, match="arithmetic_overflow"):
        _run(tuple(sorted(coordinates.items())))

    tiny = {
        identifier: tuple(value * 1e-160 for value in point)
        for identifier, point in _coordinates()
    }
    with pytest.raises(ForwardTriangleGeometryError, match="area_indeterminate"):
        _run(tuple(sorted(tiny.items())))


def test_large_scale_skinny_triangle_keeps_representable_area() -> None:
    square = ((0.0, 0.0), (1e200, 0.0), (1e200, 1e200), (0.0, 1e200))
    coordinates = tuple(
        sorted(
            [
                (f"lower_{index}", (point[0], point[1], 0.0))
                for index, point in enumerate(square)
            ]
            + [
                (f"upper_{index}", (point[0], point[1], 1e-100))
                for index, point in enumerate(square)
            ]
        )
    )

    result = _run(coordinates)

    assert result.triangles[0].area_mm2 == pytest.approx(5e99)


def test_non_finite_coordinate_is_rejected_before_integrity_check() -> None:
    coordinates = list(_coordinates())
    coordinates[0] = (coordinates[0][0], (inf, 0.0, 0.0))
    initialization = replace(_initialization(), coordinates_mm=tuple(sorted(coordinates)))
    with pytest.raises(ForwardTriangleGeometryError, match="coordinate_non_finite"):
        _run(initialization=initialization)


def test_missing_coordinate_and_provenance_mismatch_fail_closed() -> None:
    incomplete = tuple(row for row in _coordinates() if row[0] != "lower_0")
    with pytest.raises(ForwardTriangleGeometryError, match="coordinate_missing"):
        _run(incomplete)
    with pytest.raises(ForwardTriangleGeometryError, match="projection_mismatch"):
        _run(initialization=_initialization(projection="d" * 64))


def test_tampered_source_and_reordered_triangulation_are_rejected() -> None:
    source = _source()
    triangulation = triangulate_forward_surface_cells(source)
    tampered_source = replace(source, projection_sha256="d" * 64)
    with pytest.raises(ForwardTriangleGeometryError, match="source_integrity"):
        diagnose_initial_triangle_geometry(tampered_source, triangulation, _initialization())
    reordered = replace(triangulation, triangles=tuple(reversed(triangulation.triangles)))
    with pytest.raises(ForwardTriangleGeometryError, match="triangulation_mismatch"):
        diagnose_initial_triangle_geometry(source, reordered, _initialization())
