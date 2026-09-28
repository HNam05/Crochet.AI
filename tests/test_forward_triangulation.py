from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from typing import Any

import pytest

from crochet_ai.canonical import jcs_bytes
from crochet_ai.forward_cells import ForwardSurfaceCells, SurfaceCell
from crochet_ai.forward_triangulation import (
    ForwardTriangulationError,
    SurfaceTriangle,
    triangulate_forward_surface_cells,
)


def _source(course_count: int) -> ForwardSurfaceCells:
    """Build hand-authored quads, independent of the surface-cell builder."""
    assert course_count in {2, 3}
    loops = [tuple(f"loc_{course}_{index}" for index in range(4)) for course in range(course_count)]
    course_ids = [f"course_{course}" for course in range(course_count)]
    cells = tuple(
        SurfaceCell(
            course_ids[lower],
            course_ids[lower + 1],
            ordinal,
            (
                loops[lower][ordinal],
                loops[lower][(ordinal + 1) % 4],
                loops[lower + 1][(ordinal + 1) % 4],
                loops[lower + 1][ordinal],
            ),
        )
        for lower in range(course_count - 1)
        for ordinal in range(4)
    )
    return _seal(cells, loops[0], loops[-1])


def _seal(
    cells: tuple[SurfaceCell, ...], lower: tuple[str, ...], upper: tuple[str, ...]
) -> ForwardSurfaceCells:
    payload: dict[str, Any] = {
        "profile": "FORWARD_SURFACE_CELLS_V1",
        "status": "EXPERIMENTAL_TOPOLOGY",
        "projection_sha256": "a" * 64,
        "material_sha256": "b" * 64,
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
        payload["projection_sha256"],
        payload["material_sha256"],
        lower,
        upper,
        cells,
        encoded,
        digest,
    )


@pytest.mark.parametrize("course_count", [2, 3])
def test_handbuilt_open_strip_triangulates_with_preserved_orientation(course_count: int) -> None:
    source = _source(course_count)
    result = triangulate_forward_surface_cells(source)

    assert result.status == "EXPERIMENTAL_TOPOLOGY"
    assert result.source_cells_sha256 == source.sha256
    assert len(result.triangles) == 2 * len(source.cells)
    first = source.cells[0]
    assert result.triangles[:2] == (
        SurfaceTriangle(
            first.lower_course_id,
            first.upper_course_id,
            first.ordinal,
            0,
            first.attachment_location_ids[:3],
        ),
        SurfaceTriangle(
            first.lower_course_id,
            first.upper_course_id,
            first.ordinal,
            1,
            (
                first.attachment_location_ids[0],
                first.attachment_location_ids[2],
                first.attachment_location_ids[3],
            ),
        ),
    )
    assert triangulate_forward_surface_cells(source) == result
    assert b'"profile":"FORWARD_SURFACE_TRIANGULATION_V1"' in result.canonical_bytes


def test_dataclass_replace_field_tampering_is_rejected_by_source_binding() -> None:
    source = _source(2)
    with pytest.raises(ForwardTriangulationError, match="source_payload_mismatch"):
        triangulate_forward_surface_cells(
            replace(source, cells=(source.cells[1], *source.cells[1:]))
        )
    with pytest.raises(ForwardTriangulationError, match="source_hash_mismatch"):
        triangulate_forward_surface_cells(
            replace(source, canonical_bytes=source.canonical_bytes + b" ")
        )
    with pytest.raises(ForwardTriangulationError, match="source_status_invalid"):
        triangulate_forward_surface_cells(replace(source, status="CONVERGED"))


def test_resealed_reordered_and_duplicate_cells_are_rejected() -> None:
    source = _source(2)
    with pytest.raises(ForwardTriangulationError, match="cell_ordinal_order_invalid"):
        triangulate_forward_surface_cells(
            _seal(
                (source.cells[1], source.cells[0], *source.cells[2:]),
                source.lower_boundary_location_ids,
                source.upper_boundary_location_ids,
            )
        )
    with pytest.raises(ForwardTriangulationError, match="cell_ordinal_order_invalid"):
        triangulate_forward_surface_cells(
            _seal(
                (source.cells[0], source.cells[0], *source.cells[2:]),
                source.lower_boundary_location_ids,
                source.upper_boundary_location_ids,
            )
        )


def test_resealed_orientation_change_fails_closed() -> None:
    source = _source(2)
    first = source.cells[0]
    flipped = replace(
        first,
        attachment_location_ids=(
            first.attachment_location_ids[1],
            first.attachment_location_ids[0],
            first.attachment_location_ids[3],
            first.attachment_location_ids[2],
        ),
    )
    damaged = _seal(
        (flipped, *source.cells[1:]),
        source.lower_boundary_location_ids,
        source.upper_boundary_location_ids,
    )
    with pytest.raises(ForwardTriangulationError, match="cell_lower_adjacency_invalid"):
        triangulate_forward_surface_cells(damaged)


def test_nonadjacent_course_loops_cannot_alias_vertex_ids() -> None:
    source = _source(3)
    first_loop = source.lower_boundary_location_ids
    aliased_cells = tuple(
        replace(
                cell,
                attachment_location_ids=(
                    cell.attachment_location_ids[0],
                    cell.attachment_location_ids[1],
                    first_loop[(index + 1) % len(first_loop)],
                    first_loop[index],
                ),
        )
            if cell.upper_course_id == "course_2"
        else cell
        for index, cell in ((cell.ordinal, cell) for cell in source.cells)
    )
    damaged = _seal(aliased_cells, source.lower_boundary_location_ids, first_loop)

    with pytest.raises(ForwardTriangulationError, match="course_loop_vertex_alias"):
        triangulate_forward_surface_cells(damaged)
