"""Experimental deterministic target-free coordinates for a narrow crochet graph.

The initializer supports plain, multi-course cyclic single-crochet graphs only.
It proposes coordinates and does not simulate, optimize, or claim convergence.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from .canonical import jcs_bytes
from .forward_graph import ForwardGraph
from .forward_inputs import ForwardInputs
from .json_types import JSONValue
from .physical_projection import PhysicalSemanticProjection

PROFILE = "FORWARD_STRETCH_INITIALIZATION_V1"


class ForwardInitializationError(ValueError):
    """Unsupported or ambiguous target-free initialization input."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ForwardInitialization:
    """Immutable experimental coordinates and their complete input bindings."""

    status: str
    projection_sha256: str
    material_sha256: str
    forward_inputs_sha256: str
    anchor_location_groups: tuple[tuple[str, ...], ...]
    coordinates_mm: tuple[tuple[str, tuple[float, float, float]], ...]
    canonical_bytes: bytes
    sha256: str


def initialize_forward_graph(
    projection: PhysicalSemanticProjection,
    graph: ForwardGraph,
    inputs: ForwardInputs,
) -> ForwardInitialization:
    """Create fixed regular-polygon coordinates from admitted physical semantics.

    Each cyclic course becomes a regular polygon whose chord is its exact,
    uniform effective stitch pitch. The first course is at ``z=0``. Later
    courses advance axially by their own exact, uniform effective course
    pitch. That z increment does not assert an equal 3D Euclidean wale length.
    All magic-ring anchor locations from one declared operation share origin.
    """

    if not isinstance(projection, PhysicalSemanticProjection):
        raise ForwardInitializationError("initialization.projection_type")
    if not isinstance(graph, ForwardGraph):
        raise ForwardInitializationError("initialization.graph_type")
    if not isinstance(inputs, ForwardInputs):
        raise ForwardInitializationError("initialization.inputs_type")
    if projection.sha256 != graph.projection_sha256:
        raise ForwardInitializationError("initialization.projection_hash_mismatch")
    if (
        isinstance(inputs.max_initialization_vertices, bool)
        or not isinstance(inputs.max_initialization_vertices, int)
        or inputs.max_initialization_vertices <= 0
    ):
        raise ForwardInitializationError("initialization.vertex_budget_invalid")
    if len(graph.nodes) > inputs.max_initialization_vertices:
        raise ForwardInitializationError("initialization.vertex_budget_exhausted")

    projected = projection.to_dict()
    courses, sequence_by_event, stitches, locations, operations = _index_projection(projected)
    graph_nodes = {node.attachment_location_id: node.location_type for node in graph.nodes}
    if len(graph_nodes) != len(graph.nodes):
        raise ForwardInitializationError("initialization.duplicate_graph_node")
    projected_locations: dict[str, dict[str, Any]] = {}
    for row in locations:
        identifier = row.get("attachment_location_id")
        if not isinstance(identifier, str) or identifier in projected_locations:
            raise ForwardInitializationError("initialization.location_ambiguous")
        projected_locations[identifier] = row
    if set(projected_locations) != set(graph_nodes):
        raise ForwardInitializationError("initialization.location_set_mismatch")

    anchor_groups = _ring_anchor_groups(graph_nodes, projected_locations, operations)
    if len(anchor_groups) != 1:
        raise ForwardInitializationError("initialization.one_ring_operation_required")
    anchor_locations = anchor_groups[0]
    if not anchor_locations:
        raise ForwardInitializationError("initialization.ring_anchors_missing")

    if any(group.shaping != "PLAIN" for group in graph.shaping_groups):
        raise ForwardInitializationError("initialization.unsupported_shaping")
    shaping_groups = {}
    for group in graph.shaping_groups:
        if group.stitch_id in shaping_groups:
            raise ForwardInitializationError("initialization.ambiguous_shaping_group")
        if (
            group.base_arity != 1
            or group.top_arity != 1
            or len(group.base_attachment_location_ids) != 1
            or len(group.top_attachment_location_ids) != 1
        ):
            raise ForwardInitializationError("initialization.unsupported_shaping")
        shaping_groups[group.stitch_id] = group
    if set(shaping_groups) != set(stitches):
        raise ForwardInitializationError("initialization.shaping_group_coverage")

    responses = {}
    for response in graph.material_responses:
        if response.stitch_id in responses:
            raise ForwardInitializationError("initialization.ambiguous_material_response")
        responses[response.stitch_id] = response
    if set(responses) != set(stitches):
        raise ForwardInitializationError("initialization.material_response_coverage")

    course_order = projected.get("course_order")
    if not isinstance(course_order, list) or not course_order:
        raise ForwardInitializationError("initialization.course_order_missing")
    coordinates: dict[str, tuple[float, float, float]] = {
        location_id: (0.0, 0.0, 0.0) for location_id in anchor_locations
    }
    seen_stitch_members: list[str] = []
    z_mm = 0.0
    previous_top_ids: list[str] | None = None
    previous_direction: str | None = None
    for course_index, course_id in enumerate(course_order):
        course = courses.get(course_id)
        if course is None:
            raise ForwardInitializationError("initialization.course_missing")
        if course.get("course_form") != "CYCLIC":
            raise ForwardInitializationError("initialization.course_not_cyclic")
        direction = course.get("work_direction")
        if direction not in {"CLOCKWISE", "COUNTERCLOCKWISE"}:
            raise ForwardInitializationError("initialization.work_direction_unsupported")
        if previous_direction is not None and direction != previous_direction:
            raise ForwardInitializationError("initialization.work_direction_inconsistent")
        event_ids = course.get("member_event_ids")
        if not isinstance(event_ids, list) or len(event_ids) < 3:
            raise ForwardInitializationError("initialization.course_too_small")

        top_ids: list[str] = []
        base_ids: list[str] = []
        stitch_ids: list[str] = []
        pitch_values: list[float] = []
        for event_id in event_ids:
            event = sequence_by_event.get(event_id)
            if event is None or not isinstance(event.get("subject_ref"), dict):
                raise ForwardInitializationError("initialization.course_event_missing")
            subject = event["subject_ref"]
            if subject.get("entity_type") != "STITCH":
                raise ForwardInitializationError("initialization.non_stitch_course_event")
            stitch_id = subject.get("stitch_id")
            stitch = stitches.get(stitch_id)
            if (
                stitch is None
                or stitch.get("course_id") != course_id
                or stitch.get("stitch_type") != "SINGLE_CROCHET"
            ):
                raise ForwardInitializationError("initialization.course_stitch_mismatch")
            course_group = shaping_groups.get(stitch_id)
            if course_group is None:
                raise ForwardInitializationError("initialization.shaping_group_missing")
            base_id = course_group.base_attachment_location_ids[0]
            expected_base_type = "MAGIC_RING_ANCHOR" if course_index == 0 else "TOP_LOOP"
            if graph_nodes.get(base_id) != expected_base_type:
                raise ForwardInitializationError("initialization.base_location_missing")
            base_ids.append(base_id)
            top_id = course_group.top_attachment_location_ids[0]
            if top_id not in graph_nodes or graph_nodes[top_id] != "TOP_LOOP":
                raise ForwardInitializationError("initialization.top_location_missing")
            location = projected_locations.get(top_id)
            if location is None or location.get("producer_ref") != {
                "entity_type": "STITCH",
                "stitch_id": stitch_id,
            }:
                raise ForwardInitializationError("initialization.top_producer_mismatch")
            course_response = responses.get(stitch_id)
            if course_response is None:
                raise ForwardInitializationError("initialization.material_response_missing")
            pitch_values.append(
                _positive_finite(course_response.effective_stitch_pitch_mm, "stitch_pitch")
            )
            top_ids.append(top_id)
            stitch_ids.append(stitch_id)
            seen_stitch_members.append(stitch_id)

        if previous_top_ids is not None and base_ids != previous_top_ids:
            raise ForwardInitializationError("initialization.wale_order_mismatch")

        if len(set(top_ids)) != len(top_ids):
            raise ForwardInitializationError("initialization.duplicate_course_location")
        if any(top_id in coordinates for top_id in top_ids):
            raise ForwardInitializationError("initialization.location_reused")
        stitch_pitch = _uniform(pitch_values, "stitch_pitch_nonuniform")
        if course_index:
            course_pitches = [
                _positive_finite(responses[sid].effective_course_pitch_mm, "course_pitch")
                for sid in stitch_ids
            ]
            course_pitch = _uniform(course_pitches, "course_pitch_nonuniform")
            next_z_mm = z_mm + course_pitch
            if not math.isfinite(next_z_mm) or next_z_mm <= z_mm:
                raise ForwardInitializationError("initialization.axial_progress_unrepresentable")
            z_mm = next_z_mm
        previous_top_ids = top_ids
        previous_direction = direction

        count = len(top_ids)
        radius = stitch_pitch / (2.0 * math.sin(math.pi / count))
        if not math.isfinite(radius):
            raise ForwardInitializationError("initialization.radius_non_finite")
        sign = -1.0 if direction == "CLOCKWISE" else 1.0
        course_points: list[tuple[float, float, float]] = []
        for ordinal, location_id in enumerate(top_ids):
            angle = sign * (2.0 * math.pi * ordinal / count)
            point = (radius * math.cos(angle), radius * math.sin(angle), z_mm)
            if any(not math.isfinite(value) for value in point):
                raise ForwardInitializationError("initialization.coordinate_non_finite")
            coordinates[location_id] = point
            course_points.append(point)
        for left, right in zip(course_points, course_points[1:] + course_points[:1], strict=True):
            actual_chord = math.dist(left, right)
            # Internal arithmetic check: 64 ULPs in mm cover binary64 rounding
            # in radius, trigonometry, and norm; this is not a physical tolerance.
            chord_tolerance_mm = 64.0 * (math.ulp(stitch_pitch) + math.ulp(actual_chord))
            if (
                not math.isfinite(actual_chord)
                or abs(actual_chord - stitch_pitch) > chord_tolerance_mm
            ):
                raise ForwardInitializationError("initialization.chord_residual")

    if set(courses) != set(course_order) or len(set(course_order)) != len(course_order):
        raise ForwardInitializationError("initialization.course_order_mismatch")
    if set(coordinates) != set(graph_nodes):
        raise ForwardInitializationError("initialization.unassigned_graph_location")
    # Course membership must account for every executable stitch exactly once.
    if set(seen_stitch_members) != set(stitches) or len(seen_stitch_members) != len(stitches):
        raise ForwardInitializationError("initialization.incomplete_course_membership")

    ordered_coordinates = tuple(sorted(coordinates.items()))
    anchor_tuple = tuple(anchor_locations)
    payload: dict[str, JSONValue] = {
        "profile": PROFILE,
        "status": "EXPERIMENTAL_INITIALIZATION",
        "projection_sha256": projection.sha256,
        "material_sha256": graph.material_sha256,
        "forward_inputs_sha256": inputs.sha256,
        "anchor_location_groups": [list(anchor_tuple)],
        "coordinates_mm": [
            {"attachment_location_id": location_id, "xyz_mm": list(point)}
            for location_id, point in ordered_coordinates
        ],
    }
    encoded = jcs_bytes(payload)
    digest = sha256(b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + encoded).hexdigest()
    return ForwardInitialization(
        "EXPERIMENTAL_INITIALIZATION",
        projection.sha256,
        graph.material_sha256,
        inputs.sha256,
        (anchor_tuple,),
        ordered_coordinates,
        encoded,
        digest,
    )


def _index_projection(
    value: dict[str, Any],
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    courses = _rows_by_id(value.get("courses"), "course_id", "courses")
    sequence = _rows_by_id(value.get("construction_sequence"), "event_id", "construction_sequence")
    stitches = _rows_by_id(value.get("stitches"), "stitch_id", "stitches")
    locations = value.get("attachment_locations")
    operations = value.get("construction_operations")
    if not isinstance(locations, list) or not all(isinstance(item, dict) for item in locations):
        raise ForwardInitializationError("initialization.locations_invalid")
    if not isinstance(operations, list) or not all(isinstance(item, dict) for item in operations):
        raise ForwardInitializationError("initialization.operations_invalid")
    return courses, sequence, stitches, locations, operations


def _rows_by_id(value: object, key: str, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ForwardInitializationError(f"initialization.{label}_invalid")
    result: dict[str, dict[str, Any]] = {}
    for row in value:
        identifier = row.get(key)
        if not isinstance(identifier, str) or identifier in result:
            raise ForwardInitializationError(f"initialization.{label}_ambiguous")
        result[identifier] = row
    return result


def _ring_anchor_groups(
    graph_nodes: dict[str, str],
    projected_locations: dict[str, dict[str, Any]],
    operations: list[dict[str, Any]],
) -> list[tuple[str, ...]]:
    operation_types: dict[str, str] = {}
    for operation in operations:
        operation_id = operation.get("operation_id")
        operation_type = operation.get("operation_type")
        if not isinstance(operation_id, str) or not isinstance(operation_type, str):
            raise ForwardInitializationError("initialization.operation_invalid")
        if operation_id in operation_types:
            raise ForwardInitializationError("initialization.operation_ambiguous")
        operation_types[operation_id] = operation_type
    anchors = [
        identifier for identifier, kind in graph_nodes.items() if kind == "MAGIC_RING_ANCHOR"
    ]
    unknown = [
        identifier
        for identifier, kind in graph_nodes.items()
        if kind not in {"MAGIC_RING_ANCHOR", "TOP_LOOP"}
    ]
    if unknown:
        raise ForwardInitializationError("initialization.location_type_unsupported")
    ring_operation_ids = [
        operation_id
        for operation_id, operation_type in operation_types.items()
        if operation_type == "MAGIC_RING"
    ]
    if len(ring_operation_ids) != 1:
        raise ForwardInitializationError("initialization.one_ring_operation_required")
    by_operation: dict[str, list[str]] = defaultdict(list)
    for identifier in anchors:
        location = projected_locations.get(identifier)
        producer = None if location is None else location.get("producer_ref")
        if (
            not isinstance(producer, dict)
            or producer.get("entity_type") != "CONSTRUCTION_OPERATION"
        ):
            raise ForwardInitializationError("initialization.ring_anchor_producer_invalid")
        operation_id = producer.get("operation_id")
        if not isinstance(operation_id, str) or operation_types.get(operation_id) != "MAGIC_RING":
            raise ForwardInitializationError("initialization.ring_anchor_producer_invalid")
        by_operation[operation_id].append(identifier)
    if set(by_operation) != set(ring_operation_ids):
        raise ForwardInitializationError("initialization.ring_anchor_operation_mismatch")
    ring_operation_id = ring_operation_ids[0]
    operation = next(row for row in operations if row["operation_id"] == ring_operation_id)
    declared_locations = operation.get("attachment_location_ids")
    if not isinstance(declared_locations, list) or not declared_locations:
        raise ForwardInitializationError("initialization.ring_sites_invalid")
    if len(set(declared_locations)) != len(declared_locations):
        raise ForwardInitializationError("initialization.ring_sites_ambiguous")
    if set(declared_locations) != set(by_operation[ring_operation_id]) or set(
        declared_locations
    ) != set(anchors):
        raise ForwardInitializationError("initialization.ring_site_accounting")
    for ordinal, location_id in enumerate(declared_locations):
        location = projected_locations[location_id]
        if location.get("ordinal_within_producer") != ordinal or location.get("producer_ref") != {
            "entity_type": "CONSTRUCTION_OPERATION",
            "operation_id": ring_operation_id,
        }:
            raise ForwardInitializationError("initialization.ring_site_order_mismatch")
    return [tuple(declared_locations)]


def _uniform(values: list[float], reason: str) -> float:
    if not values:
        raise ForwardInitializationError("initialization.material_response_missing")
    first = values[0]
    if any(value != first for value in values[1:]):
        raise ForwardInitializationError(f"initialization.{reason}")
    return first


def _positive_finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ForwardInitializationError(f"initialization.{name}_invalid")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ForwardInitializationError(f"initialization.{name}_invalid")
    return result
