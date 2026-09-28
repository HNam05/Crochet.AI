"""Target-free quad topology for a bounded cyclic single-crochet subset.

This module emits discrete surface cells only. It assigns no coordinates,
boundary caps, contact semantics, or physical interpretation.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from itertools import pairwise
from typing import Any

from .canonical import jcs_bytes
from .forward_graph import ForwardGraph, GraphEdge
from .physical_projection import PhysicalSemanticProjection

PROFILE = "FORWARD_SURFACE_CELLS_V1"


class ForwardSurfaceCellsError(ValueError):
    """The admitted projection and graph do not define the supported strip."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class SurfaceCell:
    lower_course_id: str
    upper_course_id: str
    ordinal: int
    attachment_location_ids: tuple[str, str, str, str]


@dataclass(frozen=True, slots=True)
class ForwardSurfaceCells:
    """Immutable ordered quads, bound to semantic and material inputs."""

    status: str
    projection_sha256: str
    material_sha256: str
    lower_boundary_location_ids: tuple[str, ...]
    upper_boundary_location_ids: tuple[str, ...]
    cells: tuple[SurfaceCell, ...]
    canonical_bytes: bytes
    sha256: str


def build_forward_surface_cells(
    projection: PhysicalSemanticProjection, graph: ForwardGraph
) -> ForwardSurfaceCells:
    """Build an open strip from adjacent plain 1:1 cyclic SC courses.

    Every course loop must contain at least three stitches. Wale incidence
    must define an orientation-preserving bijection from each course loop to
    the next. The emitted strip has no caps, even when a CrochetIR close
    operation retires the last semantic frontier.
    """

    if not isinstance(projection, PhysicalSemanticProjection):
        raise TypeError("projection must be PhysicalSemanticProjection")
    if not isinstance(graph, ForwardGraph):
        raise TypeError("graph must be ForwardGraph")
    if projection.sha256 != graph.projection_sha256:
        raise ForwardSurfaceCellsError("surface_cells.projection_hash_mismatch")
    if not _digest(graph.material_sha256):
        raise ForwardSurfaceCellsError("surface_cells.material_hash_invalid")

    value = projection.to_dict()
    courses = _index_rows(value.get("courses"), "course_id", "courses_invalid")
    stitches = _index_rows(value.get("stitches"), "stitch_id", "stitches_invalid")
    events = _index_rows(
        value.get("construction_sequence"), "event_id", "sequence_invalid"
    )
    locations = _index_rows(
        value.get("attachment_locations"),
        "attachment_location_id",
        "locations_invalid",
    )

    course_order = value.get("course_order")
    if (
        not isinstance(course_order, list)
        or not all(isinstance(course_id, str) for course_id in course_order)
        or len(course_order) != len(courses)
        or len(set(course_order)) != len(course_order)
        or set(course_order) != set(courses)
    ):
        raise ForwardSurfaceCellsError("surface_cells.course_order_mismatch")
    if len(course_order) < 2:
        raise ForwardSurfaceCellsError("surface_cells.adjacent_course_pair_missing")

    sequence = value.get("construction_sequence")
    assert isinstance(sequence, list)
    sequence_order: dict[str, int] = {}
    for row in sequence:
        event_id = row["event_id"]
        index = row.get("sequence_index")
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or index in sequence_order.values()
        ):
            raise ForwardSurfaceCellsError("surface_cells.sequence_order_invalid")
        sequence_order[event_id] = index
    if sorted(sequence_order.values()) != list(range(len(sequence_order))):
        raise ForwardSurfaceCellsError("surface_cells.sequence_order_invalid")

    course_loops: dict[str, tuple[str, ...]] = {}
    course_bases: dict[str, tuple[str, ...]] = {}
    course_directions: dict[str, str] = {}
    seen_stitches: list[str] = []
    previous_event_index = -1
    for course_id in course_order:
        course = courses[course_id]
        if course.get("course_form") != "CYCLIC":
            raise ForwardSurfaceCellsError("surface_cells.course_not_cyclic")
        if course.get("work_direction") not in {"CLOCKWISE", "COUNTERCLOCKWISE"}:
            raise ForwardSurfaceCellsError("surface_cells.work_direction_unsupported")
        course_directions[course_id] = course["work_direction"]
        member_event_ids = course.get("member_event_ids")
        if not isinstance(member_event_ids, list) or len(member_event_ids) < 3:
            raise ForwardSurfaceCellsError("surface_cells.course_too_small")
        top_ids: list[str] = []
        base_ids: list[str] = []
        member_indices: list[int] = []
        for event_id in member_event_ids:
            event = events.get(event_id)
            if event is None:
                raise ForwardSurfaceCellsError("surface_cells.course_event_missing")
            subject = event.get("subject_ref")
            if not isinstance(subject, dict) or subject.get("entity_type") != "STITCH":
                raise ForwardSurfaceCellsError("surface_cells.non_stitch_course_event")
            stitch_id = subject.get("stitch_id")
            if not isinstance(stitch_id, str):
                raise ForwardSurfaceCellsError("surface_cells.course_stitch_mismatch")
            stitch = stitches.get(stitch_id)
            if stitch is None or stitch.get("course_id") != course_id:
                raise ForwardSurfaceCellsError("surface_cells.course_stitch_mismatch")
            if stitch.get("stitch_type") != "SINGLE_CROCHET" or stitch.get("shaping") != "PLAIN":
                raise ForwardSurfaceCellsError("surface_cells.unsupported_stitch")
            bases = stitch.get("base_attachment_location_ids")
            if not isinstance(bases, list) or len(bases) != 1 or not isinstance(bases[0], str):
                raise ForwardSurfaceCellsError("surface_cells.non_bijective_wale_mapping")
            tops = stitch.get("top_attachment_location_ids")
            if not isinstance(tops, list) or len(tops) != 1 or not isinstance(tops[0], str):
                raise ForwardSurfaceCellsError("surface_cells.non_bijective_wale_mapping")
            base_ids.append(bases[0])
            top_ids.append(tops[0])
            seen_stitches.append(stitch_id)
            member_indices.append(sequence_order[event_id])
        if member_indices != sorted(member_indices) or member_indices[0] <= previous_event_index:
            raise ForwardSurfaceCellsError("surface_cells.course_sequence_mismatch")
        previous_event_index = member_indices[-1]
        if len(set(top_ids)) != len(top_ids):
            raise ForwardSurfaceCellsError("surface_cells.course_location_ambiguous")
        course_loops[course_id] = tuple(top_ids)
        course_bases[course_id] = tuple(base_ids)

    first_course_bases = course_bases[course_order[0]]
    if any(
        locations.get(base_id, {}).get("location_type") != "MAGIC_RING_ANCHOR"
        for base_id in first_course_bases
    ):
        raise ForwardSurfaceCellsError("surface_cells.first_course_base_type_mismatch")
    for course_id in course_order[1:]:
        if any(
            locations.get(base_id, {}).get("location_type") != "TOP_LOOP"
            for base_id in course_bases[course_id]
        ):
            raise ForwardSurfaceCellsError("surface_cells.course_base_type_mismatch")
    for lower_id, upper_id in pairwise(course_order):
        lower_loop = course_loops[lower_id]
        upper_bases = course_bases[upper_id]
        if len(set(upper_bases)) != len(upper_bases):
            raise ForwardSurfaceCellsError("surface_cells.duplicate_course_base")
        if set(upper_bases) != set(lower_loop):
            raise ForwardSurfaceCellsError("surface_cells.course_base_set_mismatch")
        if course_directions[lower_id] != course_directions[upper_id]:
            raise ForwardSurfaceCellsError("surface_cells.course_direction_mismatch")

    if len(seen_stitches) != len(stitches) or set(seen_stitches) != set(stitches):
        raise ForwardSurfaceCellsError("surface_cells.stitch_membership_mismatch")
    if len(locations) != len(graph.nodes) or set(locations) != {
        node.attachment_location_id for node in graph.nodes
    }:
        raise ForwardSurfaceCellsError("surface_cells.graph_node_set_mismatch")
    if len({node.attachment_location_id for node in graph.nodes}) != len(graph.nodes):
        raise ForwardSurfaceCellsError("surface_cells.graph_node_duplicate")
    for node in graph.nodes:
        if locations[node.attachment_location_id].get("location_type") != node.location_type:
            raise ForwardSurfaceCellsError("surface_cells.graph_node_type_mismatch")

    shaping = _index_groups(graph.shaping_groups)
    if set(shaping) != set(stitches):
        raise ForwardSurfaceCellsError("surface_cells.shaping_group_coverage")
    expected_edges: list[GraphEdge] = []
    wale_map: dict[str, str] = {}
    for stitch_id, stitch in stitches.items():
        group = shaping[stitch_id]
        bases = stitch.get("base_attachment_location_ids")
        tops = stitch.get("top_attachment_location_ids")
        if (
            group.shaping != "PLAIN"
            or group.base_arity != 1
            or group.top_arity != 1
            or len(group.base_attachment_location_ids) != 1
            or len(group.top_attachment_location_ids) != 1
            or not isinstance(bases, list)
            or not isinstance(tops, list)
            or len(bases) != 1
            or len(tops) != 1
            or group.base_attachment_location_ids != tuple(bases)
            or group.top_attachment_location_ids != tuple(tops)
        ):
            raise ForwardSurfaceCellsError("surface_cells.shaping_group_mismatch")
        base_id, top_id = bases[0], tops[0]
        if base_id in wale_map:
            raise ForwardSurfaceCellsError("surface_cells.non_bijective_wale_mapping")
        wale_map[base_id] = top_id
        expected_edges.append(GraphEdge("WALE", base_id, top_id, stitch["course_id"], stitch_id))

    for course_id in course_order:
        loop = course_loops[course_id]
        for left, right in zip(loop, (*loop[1:], loop[0]), strict=True):
            expected_edges.append(GraphEdge("COURSE", left, right, course_id))
    if Counter(graph.edges) != Counter(expected_edges):
        raise ForwardSurfaceCellsError("surface_cells.graph_edge_set_mismatch")

    output: list[SurfaceCell] = []
    for lower_id, upper_id in pairwise(course_order):
        lower_loop = course_loops[lower_id]
        upper_loop = course_loops[upper_id]
        if len(lower_loop) != len(upper_loop):
            raise ForwardSurfaceCellsError("surface_cells.course_count_mismatch")
        mapped_upper: list[str] = []
        for location_id in lower_loop:
            mapped = wale_map.get(location_id)
            if mapped is None:
                raise ForwardSurfaceCellsError("surface_cells.wale_mapping_missing")
            mapped_upper.append(mapped)
        if len(set(mapped_upper)) != len(mapped_upper) or set(mapped_upper) != set(upper_loop):
            raise ForwardSurfaceCellsError("surface_cells.non_bijective_wale_mapping")
        upper_positions = {location_id: index for index, location_id in enumerate(upper_loop)}
        if any(
            upper_positions[mapped_upper[(index + 1) % len(mapped_upper)]]
            != (upper_positions[mapped_upper[index]] + 1) % len(upper_loop)
            for index in range(len(lower_loop))
        ):
            raise ForwardSurfaceCellsError("surface_cells.course_adjacency_mismatch")
        # The bounded profile has no phase-selection rule. Require the exact
        # declared ordinal correspondence instead of rotating either loop.
        if mapped_upper != list(upper_loop):
            raise ForwardSurfaceCellsError("surface_cells.course_phase_mismatch")
        for ordinal, lower_left in enumerate(lower_loop):
            lower_right = lower_loop[(ordinal + 1) % len(lower_loop)]
            output.append(
                SurfaceCell(
                    lower_id,
                    upper_id,
                    ordinal,
                    (
                        lower_left,
                        lower_right,
                        mapped_upper[(ordinal + 1) % len(lower_loop)],
                        mapped_upper[ordinal],
                    ),
                )
            )

    payload: dict[str, Any] = {
        "profile": PROFILE,
        "status": "EXPERIMENTAL_TOPOLOGY",
        "projection_sha256": projection.sha256,
        "material_sha256": graph.material_sha256,
        "lower_boundary_location_ids": list(course_loops[course_order[0]]),
        "upper_boundary_location_ids": list(course_loops[course_order[-1]]),
        "cells": [
            {
                "lower_course_id": cell.lower_course_id,
                "upper_course_id": cell.upper_course_id,
                "ordinal": cell.ordinal,
                "attachment_location_ids": list(cell.attachment_location_ids),
            }
            for cell in output
        ],
    }
    encoded = jcs_bytes(payload)
    digest = sha256(b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + encoded).hexdigest()
    return ForwardSurfaceCells(
        "EXPERIMENTAL_TOPOLOGY",
        projection.sha256,
        graph.material_sha256,
        course_loops[course_order[0]],
        course_loops[course_order[-1]],
        tuple(output),
        encoded,
        digest,
    )


def _index_rows(value: object, key: str, reason: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise ForwardSurfaceCellsError(f"surface_cells.{reason}")
    rows: dict[str, dict[str, Any]] = {}
    for row in value:
        identifier = row.get(key)
        if not isinstance(identifier, str) or identifier in rows:
            raise ForwardSurfaceCellsError(f"surface_cells.{reason}")
        rows[identifier] = row
    return rows


def _index_groups(groups: tuple[Any, ...]) -> dict[str, Any]:
    indexed: dict[str, Any] = {}
    for group in groups:
        if group.stitch_id in indexed:
            raise ForwardSurfaceCellsError("surface_cells.shaping_group_ambiguous")
        indexed[group.stitch_id] = group
    return indexed


def _digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        char in "0123456789abcdef" for char in value
    )
