"""Deterministic coordinate-free triangulation of an admitted open quad strip.

This module preserves each source quad's declared orientation and introduces
no geometry, caps, contact model, or physical-verification claim.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from .canonical import jcs_bytes, parse_json
from .forward_cells import ForwardSurfaceCells, SurfaceCell

PROFILE = "FORWARD_SURFACE_TRIANGULATION_V1"


class ForwardTriangulationError(ValueError):
    """Source integrity or open-strip topology did not satisfy this profile."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class SurfaceTriangle:
    """An oriented triangle using stable attachment-location labels."""

    source_lower_course_id: str
    source_upper_course_id: str
    source_cell_ordinal: int
    triangle_index: int
    attachment_location_ids: tuple[str, str, str]


@dataclass(frozen=True, slots=True)
class ForwardSurfaceTriangulation:
    """Immutable triangulation bound to the exact canonical source cells."""

    status: str
    source_cells_sha256: str
    triangles: tuple[SurfaceTriangle, ...]
    canonical_bytes: bytes
    sha256: str


def triangulate_forward_surface_cells(
    source: ForwardSurfaceCells,
) -> ForwardSurfaceTriangulation:
    """Split each quad `(a,b,c,d)` into `(a,b,c)` and `(a,c,d)`.

    Input bytes, domain hash, and payload are checked against the immutable
    fields before topology is considered. It checks connectedness, opposite
    orientation on shared edges, two declared boundary loops, and Euler
    characteristic zero. These checks do not certify geometric embedding.
    """

    if not isinstance(source, ForwardSurfaceCells):
        raise TypeError("source must be ForwardSurfaceCells")
    _validate_source(source)

    triangles: list[SurfaceTriangle] = []
    for cell in source.cells:
        a, b, c, d = cell.attachment_location_ids
        if len({a, b, c, d}) != 4:
            raise ForwardTriangulationError("triangulation.cell_vertex_repeated")
        triangles.append(
            SurfaceTriangle(cell.lower_course_id, cell.upper_course_id, cell.ordinal, 0, (a, b, c))
        )
        triangles.append(
            SurfaceTriangle(cell.lower_course_id, cell.upper_course_id, cell.ordinal, 1, (a, c, d))
        )

    _validate_open_cylinder(source, triangles)
    payload: dict[str, Any] = {
        "profile": PROFILE,
        "status": "EXPERIMENTAL_TOPOLOGY",
        "source_cells_sha256": source.sha256,
        "triangles": [
            {
                "source_lower_course_id": triangle.source_lower_course_id,
                "source_upper_course_id": triangle.source_upper_course_id,
                "source_cell_ordinal": triangle.source_cell_ordinal,
                "triangle_index": triangle.triangle_index,
                "attachment_location_ids": list(triangle.attachment_location_ids),
            }
            for triangle in triangles
        ],
    }
    encoded = jcs_bytes(payload)
    digest = sha256(b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + encoded).hexdigest()
    return ForwardSurfaceTriangulation(
        status="EXPERIMENTAL_TOPOLOGY",
        source_cells_sha256=source.sha256,
        triangles=tuple(triangles),
        canonical_bytes=encoded,
        sha256=digest,
    )


def _validate_source(source: ForwardSurfaceCells) -> None:
    if source.status != "EXPERIMENTAL_TOPOLOGY":
        raise ForwardTriangulationError("triangulation.source_status_invalid")
    if not _digest(source.projection_sha256) or not _digest(source.material_sha256):
        raise ForwardTriangulationError("triangulation.source_hash_invalid")
    if not isinstance(source.canonical_bytes, bytes) or not _digest(source.sha256):
        raise ForwardTriangulationError("triangulation.source_integrity_invalid")
    if (
        not isinstance(source.lower_boundary_location_ids, tuple)
        or not isinstance(source.upper_boundary_location_ids, tuple)
        or not isinstance(source.cells, tuple)
        or any(not isinstance(cell, SurfaceCell) for cell in source.cells)
    ):
        raise ForwardTriangulationError("triangulation.source_fields_invalid")
    for cell in source.cells:
        if (
            not isinstance(cell.lower_course_id, str)
            or not cell.lower_course_id
            or not isinstance(cell.upper_course_id, str)
            or not cell.upper_course_id
            or isinstance(cell.ordinal, bool)
            or not isinstance(cell.ordinal, int)
            or cell.ordinal < 0
            or not isinstance(cell.attachment_location_ids, tuple)
            or len(cell.attachment_location_ids) != 4
            or not all(isinstance(item, str) and item for item in cell.attachment_location_ids)
        ):
            raise ForwardTriangulationError("triangulation.cell_invalid")
    expected_digest = sha256(
        b"Crochet.AI\0" + b"FORWARD_SURFACE_CELLS_V1" + b"\0" + source.canonical_bytes
    ).hexdigest()
    if expected_digest != source.sha256:
        raise ForwardTriangulationError("triangulation.source_hash_mismatch")
    try:
        payload = parse_json(source.canonical_bytes)
    except (TypeError, ValueError) as error:
        raise ForwardTriangulationError("triangulation.source_payload_invalid") from error
    if not isinstance(payload, dict) or jcs_bytes(payload) != source.canonical_bytes:
        raise ForwardTriangulationError("triangulation.source_payload_noncanonical")
    expected_payload: dict[str, Any] = {
        "profile": "FORWARD_SURFACE_CELLS_V1",
        "status": source.status,
        "projection_sha256": source.projection_sha256,
        "material_sha256": source.material_sha256,
        "lower_boundary_location_ids": list(source.lower_boundary_location_ids),
        "upper_boundary_location_ids": list(source.upper_boundary_location_ids),
        "cells": [
            {
                "lower_course_id": cell.lower_course_id,
                "upper_course_id": cell.upper_course_id,
                "ordinal": cell.ordinal,
                "attachment_location_ids": list(cell.attachment_location_ids),
            }
            for cell in source.cells
        ],
    }
    if payload != expected_payload:
        raise ForwardTriangulationError("triangulation.source_payload_mismatch")
    if not source.cells:
        raise ForwardTriangulationError("triangulation.cells_empty")
    if not _valid_loop(source.lower_boundary_location_ids) or not _valid_loop(
        source.upper_boundary_location_ids
    ):
        raise ForwardTriangulationError("triangulation.boundary_loop_invalid")
    _validate_cell_order(source)


def _validate_open_cylinder(source: ForwardSurfaceCells, triangles: list[SurfaceTriangle]) -> None:
    edge_directions: Counter[tuple[str, str]] = Counter()
    undirected_edges: set[frozenset[str]] = set()
    vertex_neighbors: dict[str, set[str]] = defaultdict(set)
    for triangle in triangles:
        a, b, c = triangle.attachment_location_ids
        if len({a, b, c}) != 3:
            raise ForwardTriangulationError("triangulation.triangle_degenerate")
        for left, right in ((a, b), (b, c), (c, a)):
            edge_directions[(left, right)] += 1
            undirected_edges.add(frozenset((left, right)))
            vertex_neighbors[left].add(right)
            vertex_neighbors[right].add(left)

    directed_counts: Counter[frozenset[str]] = Counter()
    for edge in undirected_edges:
        left, right = tuple(edge)
        directed_counts[edge] = edge_directions[(left, right)] + edge_directions[(right, left)]
        forward = edge_directions[(left, right)]
        reverse = edge_directions[(right, left)]
        if forward + reverse > 2:
            raise ForwardTriangulationError("triangulation.nonmanifold_edge")
        if forward == 2 or reverse == 2:
            raise ForwardTriangulationError("triangulation.edge_orientation_mismatch")

    boundary_edges = {edge for edge in undirected_edges if directed_counts[edge] == 1}
    if any(directed_counts[edge] != 2 for edge in undirected_edges - boundary_edges):
        raise ForwardTriangulationError("triangulation.edge_incidence_invalid")
    boundary_directed = [
        (left, right)
        for (left, right), count in edge_directions.items()
        if count == 1 and frozenset((left, right)) in boundary_edges
    ]
    expected_boundary = _expected_boundary_edges(source)
    if set(boundary_directed) != expected_boundary or len(boundary_directed) != len(
        expected_boundary
    ):
        raise ForwardTriangulationError("triangulation.boundary_mismatch")
    if _boundary_loop_count(boundary_directed) != 2:
        raise ForwardTriangulationError("triangulation.boundary_loop_count")

    vertices = set(vertex_neighbors)
    reached: set[str] = set()
    pending = [next(iter(vertices))] if vertices else []
    while pending:
        current = pending.pop()
        if current in reached:
            continue
        reached.add(current)
        pending.extend(vertex_neighbors[current] - reached)
    if reached != vertices:
        raise ForwardTriangulationError("triangulation.disconnected_surface")
    if len(vertices) - len(undirected_edges) + len(triangles) != 0:
        raise ForwardTriangulationError("triangulation.euler_characteristic_invalid")


def _expected_boundary_edges(source: ForwardSurfaceCells) -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    for loop, reverse in (
        (source.lower_boundary_location_ids, False),
        (source.upper_boundary_location_ids, True),
    ):
        for index, left in enumerate(loop):
            right = loop[(index + 1) % len(loop)]
            edges.add((right, left) if reverse else (left, right))
    return edges


def _validate_cell_order(source: ForwardSurfaceCells) -> None:
    groups: list[tuple[str, str, list[SurfaceCell]]] = []
    group_keys: set[tuple[str, str]] = set()
    for cell in source.cells:
        key = (cell.lower_course_id, cell.upper_course_id)
        if not groups or groups[-1][:2] != key:
            if key in group_keys:
                raise ForwardTriangulationError("triangulation.cell_group_repeated")
            group_keys.add(key)
            groups.append((key[0], key[1], []))
        groups[-1][2].append(cell)
    if not groups:
        raise ForwardTriangulationError("triangulation.cells_empty")
    previous_upper: str | None = None
    previous_upper_loop: tuple[str, ...] | None = None
    course_loops: dict[str, tuple[str, ...]] = {}
    occupied_locations: set[str] = set()
    for lower_course, upper_course, cells in groups:
        if lower_course == upper_course or (
            previous_upper is not None and lower_course != previous_upper
        ):
            raise ForwardTriangulationError("triangulation.cell_course_order_invalid")
        if [cell.ordinal for cell in cells] != list(range(len(cells))) or len(cells) < 3:
            raise ForwardTriangulationError("triangulation.cell_ordinal_order_invalid")
        lower_loop = tuple(cell.attachment_location_ids[0] for cell in cells)
        if (
            tuple(cell.attachment_location_ids[1] for cell in cells)
            != lower_loop[1:] + lower_loop[:1]
        ):
            raise ForwardTriangulationError("triangulation.cell_lower_adjacency_invalid")
        upper_loop = tuple(cell.attachment_location_ids[3] for cell in cells)
        if (
            tuple(cell.attachment_location_ids[2] for cell in cells)
            != upper_loop[1:] + upper_loop[:1]
        ):
            raise ForwardTriangulationError("triangulation.cell_upper_adjacency_invalid")
        if not _valid_loop(lower_loop) or not _valid_loop(upper_loop):
            raise ForwardTriangulationError("triangulation.cell_loop_invalid")
        if previous_upper_loop is not None and lower_loop != previous_upper_loop:
            raise ForwardTriangulationError("triangulation.adjacent_cell_courses_mismatch")
        if lower_course in course_loops:
            if course_loops[lower_course] != lower_loop:
                raise ForwardTriangulationError("triangulation.course_loop_inconsistent")
        else:
            if occupied_locations.intersection(lower_loop):
                raise ForwardTriangulationError("triangulation.course_loop_vertex_alias")
            course_loops[lower_course] = lower_loop
            occupied_locations.update(lower_loop)
        if upper_course in course_loops:
            raise ForwardTriangulationError("triangulation.course_id_repeated")
        if occupied_locations.intersection(upper_loop):
            raise ForwardTriangulationError("triangulation.course_loop_vertex_alias")
        course_loops[upper_course] = upper_loop
        occupied_locations.update(upper_loop)
        previous_upper = upper_course
        previous_upper_loop = upper_loop
    if groups[0][0] == groups[-1][1]:
        raise ForwardTriangulationError("triangulation.cell_course_cycle_invalid")
    if tuple(source.lower_boundary_location_ids) != tuple(
        cell.attachment_location_ids[0] for cell in groups[0][2]
    ) or tuple(source.upper_boundary_location_ids) != tuple(
        cell.attachment_location_ids[3] for cell in groups[-1][2]
    ):
        raise ForwardTriangulationError("triangulation.boundary_source_mismatch")


def _boundary_loop_count(edges: list[tuple[str, str]]) -> int:
    outgoing: dict[str, str] = {}
    incoming: dict[str, str] = {}
    for left, right in edges:
        if left in outgoing or right in incoming:
            raise ForwardTriangulationError("triangulation.boundary_branch")
        outgoing[left] = right
        incoming[right] = left
    if set(outgoing) != set(incoming):
        raise ForwardTriangulationError("triangulation.boundary_open_chain")
    loops = 0
    visited: set[str] = set()
    for start in outgoing:
        if start in visited:
            continue
        loops += 1
        current = start
        while current not in visited:
            visited.add(current)
            current = outgoing[current]
        if current != start:
            raise ForwardTriangulationError("triangulation.boundary_loop_invalid")
    return loops


def _valid_loop(value: object) -> bool:
    return (
        isinstance(value, tuple)
        and len(value) >= 3
        and all(isinstance(item, str) and item for item in value)
        and len(set(value)) == len(value)
    )


def _digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )
