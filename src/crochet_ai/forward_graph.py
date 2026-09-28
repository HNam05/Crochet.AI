"""Deterministic target-free lowering for admitted physical semantics.

This module derives graph topology and selects keyed pitch responses. It does
not assign coordinates, import a solver, accept target data, or claim simulation.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import Any

from .canonical import CanonicalProfile, canonical_hash
from .physical_projection import PhysicalSemanticProjection
from .validation import SemanticValidator


class ForwardGraphError(ValueError):
    """A graph input or exact material response is invalid or unresolved."""


@dataclass(frozen=True, slots=True)
class GraphNode:
    attachment_location_id: str
    location_type: str


@dataclass(frozen=True, slots=True)
class GraphEdge:
    edge_type: str
    source_location_id: str
    target_location_id: str
    course_id: str
    stitch_id: str | None = None


@dataclass(frozen=True, slots=True)
class StitchShapingGroup:
    """A stitch operation with explicit, ordered base/top incidence."""

    stitch_id: str
    shaping: str
    base_attachment_location_ids: tuple[str, ...]
    top_attachment_location_ids: tuple[str, ...]
    base_arity: int
    top_arity: int


@dataclass(frozen=True, slots=True)
class StitchMaterialResponse:
    stitch_id: str
    response_id: str
    effective_stitch_pitch_mm: float
    effective_course_pitch_mm: float
    stitch_pitch_standard_uncertainty_mm: float
    course_pitch_standard_uncertainty_mm: float


@dataclass(frozen=True, slots=True)
class YarnPathLink:
    """Declared adjacency between work events, without invented loop geometry."""

    yarn_path_id: str
    segment_index: int
    source_stitch_id: str
    target_stitch_id: str


@dataclass(frozen=True, slots=True)
class ConstructionOperationGroup:
    """An admitted operation tied to its exact executable event and transition."""

    operation_id: str
    operation_type: str
    sequence_index: int
    event_id: str
    frontier_transition_ids: tuple[str, ...]
    input_frontier_ids: tuple[str, ...]
    output_frontier_ids: tuple[str, ...]
    attachment_location_ids: tuple[str, ...]
    input_yarn_ids: tuple[str, ...]
    output_yarn_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FrontierBoundaryGroup:
    """Declared boundary locations associated with creation or closure."""

    operation_id: str
    operation_type: str
    frontier_transition_id: str
    input_frontier_ids: tuple[str, ...]
    output_frontier_ids: tuple[str, ...]
    attachment_location_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ForwardGraph:
    """Stable graph labels, explicit topology, and exact material selections."""

    projection_sha256: str
    material_sha256: str
    nodes: tuple[GraphNode, ...]
    shaping_groups: tuple[StitchShapingGroup, ...]
    edges: tuple[GraphEdge, ...]
    yarn_path_links: tuple[YarnPathLink, ...]
    construction_operations: tuple[ConstructionOperationGroup, ...]
    frontier_boundaries: tuple[FrontierBoundaryGroup, ...]
    material_responses: tuple[StitchMaterialResponse, ...]


def lower_forward_graph(
    projection: PhysicalSemanticProjection,
    material: dict[str, Any],
    requested_tension_profile_id: str,
    requested_fabric_state: str,
    *,
    validator: SemanticValidator,
) -> ForwardGraph:
    """Lower an admitted projection to graph topology and selected gauge data.

    The `validator` argument is the semantic admission boundary for the material
    document. Neither this function nor its result accepts target/embedding data.
    """

    if not isinstance(projection, PhysicalSemanticProjection):
        raise TypeError("projection must be PhysicalSemanticProjection")
    if not isinstance(material, dict):
        raise TypeError("material must be a MaterialProfile object")
    if not isinstance(requested_tension_profile_id, str) or not requested_tension_profile_id:
        raise TypeError("requested_tension_profile_id must be a non-empty string")
    if not isinstance(requested_fabric_state, str) or not requested_fabric_state:
        raise TypeError("requested_fabric_state must be a non-empty string")
    if not isinstance(validator, SemanticValidator):
        raise TypeError("validator must be SemanticValidator")

    report = validator.validate_material_profile(material)
    if not report.ok:
        raise ForwardGraphError("forward_graph.invalid_material_profile")

    value = projection.to_dict()
    material_hash = canonical_hash(material, CanonicalProfile.MATERIAL_PROFILE)
    bindings = [yarn["material_profile_ref"] for yarn in value["yarns"]]
    expected_binding = {
        "profile_id": material["profile_id"],
        "revision": material["revision"],
        "sha256": material_hash,
    }
    if not bindings or any(binding != expected_binding for binding in bindings):
        raise ForwardGraphError("forward_graph.material_binding_mismatch")

    locations = {
        location["attachment_location_id"]: location["location_type"]
        for location in value["attachment_locations"]
    }
    nodes = tuple(
        GraphNode(location_id, locations[location_id]) for location_id in sorted(locations)
    )
    stitches = {stitch["stitch_id"]: stitch for stitch in value["stitches"]}
    courses = {course["course_id"]: course for course in value["courses"]}
    event_subjects = {
        event["event_id"]: event["subject_ref"]
        for event in value["construction_sequence"]
    }
    events_by_operation = {
        event["subject_ref"]["operation_id"]: event
        for event in value["construction_sequence"]
        if event["subject_ref"]["entity_type"] == "CONSTRUCTION_OPERATION"
    }
    transitions = {
        transition["frontier_transition_id"]: transition
        for transition in value["frontier_transitions"]
    }
    frontiers = {frontier["frontier_id"]: frontier for frontier in value["frontiers"]}
    responses = material["calibration_responses"]

    selected: dict[str, StitchMaterialResponse] = {}
    for stitch in sorted(stitches.values(), key=lambda item: item["stitch_id"]):
        course = courses[stitch["course_id"]]
        key = (
            stitch["stitch_type"],
            course["course_form"],
            requested_tension_profile_id,
            requested_fabric_state,
        )
        matches = [
            response
            for response in responses
            if (
                response["measurement_conditions"]["canonical_stitch_type"],
                response["measurement_conditions"]["course_mode"],
                response["measurement_conditions"]["tension_profile_id"],
                response["measurement_conditions"]["fabric_state"],
            )
            == key
        ]
        if len(matches) != 1:
            raise ForwardGraphError("forward_graph.material_response_unresolved")
        response = matches[0]
        gauge = response["effective_gauge"]
        uncertainty = response["uncertainty"]
        selected[stitch["stitch_id"]] = StitchMaterialResponse(
            stitch_id=stitch["stitch_id"],
            response_id=response["response_id"],
            effective_stitch_pitch_mm=gauge["effective_stitch_pitch_mm"],
            effective_course_pitch_mm=gauge["effective_course_pitch_mm"],
            stitch_pitch_standard_uncertainty_mm=uncertainty[
                "stitch_pitch_standard_uncertainty_mm"
            ],
            course_pitch_standard_uncertainty_mm=uncertainty[
                "course_pitch_standard_uncertainty_mm"
            ],
        )

    construction_operations: list[ConstructionOperationGroup] = []
    frontier_boundaries: list[FrontierBoundaryGroup] = []
    for operation in value["construction_operations"]:
        operation_id = operation["operation_id"]
        operation_type = operation["operation_type"]
        event = events_by_operation.get(operation_id)
        if event is None or event["subject_ref"] != {
            "entity_type": "CONSTRUCTION_OPERATION",
            "operation_id": operation_id,
        }:
            raise ForwardGraphError("forward_graph.operation_event_mismatch")
        transition_ids = tuple(event["frontier_transition_ids"])
        if len(transition_ids) != 1:
            raise ForwardGraphError("forward_graph.operation_transition_mismatch")
        transition = transitions.get(transition_ids[0])
        expected_transition = {"MAGIC_RING": "CREATE", "CLOSE": "CLOSE"}.get(operation_type)
        if (
            expected_transition is None
            or transition is None
            or transition["caused_by_subject_ref"] != event["subject_ref"]
            or transition["transition_type"] != expected_transition
            or transition["after_event_index"] != event["sequence_index"]
            or tuple(transition["input_frontier_ids"])
            != tuple(operation["input_frontier_ids"])
            or tuple(transition["output_frontier_ids"])
            != tuple(operation["output_frontier_ids"])
        ):
            raise ForwardGraphError("forward_graph.operation_transition_mismatch")
        construction_operations.append(
            ConstructionOperationGroup(
                operation_id=operation_id,
                operation_type=operation_type,
                sequence_index=event["sequence_index"],
                event_id=event["event_id"],
                frontier_transition_ids=transition_ids,
                input_frontier_ids=tuple(operation["input_frontier_ids"]),
                output_frontier_ids=tuple(operation["output_frontier_ids"]),
                attachment_location_ids=tuple(operation["attachment_location_ids"]),
                input_yarn_ids=tuple(operation["input_yarn_ids"]),
                output_yarn_ids=tuple(operation["output_yarn_ids"]),
            )
        )
        if operation_type == "MAGIC_RING":
            boundary_locations = tuple(operation["attachment_location_ids"])
            output_ids = tuple(operation["output_frontier_ids"])
            if (
                operation["input_frontier_ids"]
                or len(output_ids) != 1
                or output_ids[0] not in frontiers
                or tuple(frontiers[output_ids[0]]["attachment_location_ids"])
                != boundary_locations
                or tuple(transition["created_attachment_location_ids"])
                != boundary_locations
            ):
                raise ForwardGraphError("forward_graph.operation_boundary_mismatch")
        else:
            input_ids = tuple(operation["input_frontier_ids"])
            output_ids = tuple(operation["output_frontier_ids"])
            if (
                len(input_ids) != 1
                or input_ids[0] not in frontiers
                or len(output_ids) != 1
                or output_ids[0] not in frontiers
            ):
                raise ForwardGraphError("forward_graph.operation_boundary_mismatch")
            boundary_locations = tuple(frontiers[input_ids[0]]["attachment_location_ids"])
            if (
                tuple(transition["retired_attachment_location_ids"])
                != boundary_locations
                or frontiers[output_ids[0]]["lifecycle_state"] != "CLOSED"
                or frontiers[output_ids[0]]["attachment_location_ids"]
            ):
                raise ForwardGraphError("forward_graph.operation_boundary_mismatch")
        frontier_boundaries.append(
            FrontierBoundaryGroup(
                operation_id=operation_id,
                operation_type=operation_type,
                frontier_transition_id=transition_ids[0],
                input_frontier_ids=tuple(operation["input_frontier_ids"]),
                output_frontier_ids=tuple(operation["output_frontier_ids"]),
                attachment_location_ids=boundary_locations,
            )
        )
    construction_operations.sort(key=lambda item: item.sequence_index)
    operation_order = {item.operation_id: item.sequence_index for item in construction_operations}
    frontier_boundaries.sort(key=lambda item: operation_order[item.operation_id])

    shaping_groups: list[StitchShapingGroup] = []
    edges: list[GraphEdge] = []
    for stitch_id in sorted(stitches):
        stitch = stitches[stitch_id]
        bases = tuple(stitch["base_attachment_location_ids"])
        tops = tuple(stitch["top_attachment_location_ids"])
        shaping_groups.append(
            StitchShapingGroup(
                stitch_id=stitch_id,
                shaping=stitch["shaping"],
                base_attachment_location_ids=bases,
                top_attachment_location_ids=tops,
                base_arity=stitch["base_arity"],
                top_arity=stitch["top_arity"],
            )
        )
        # Incidences record topology only; they are not one-to-one pairings or
        # rest-length constraints. A shaped stitch can have unequal arities.
        for base in bases:
            for top in tops:
                edges.append(GraphEdge("WALE", base, top, stitch["course_id"], stitch_id))

    for course_id in value["course_order"]:
        course = courses[course_id]
        ordered_tops: list[str] = []
        for event_id in course["member_event_ids"]:
            subject = event_subjects[event_id]
            if subject["entity_type"] == "STITCH":
                ordered_tops.extend(stitches[subject["stitch_id"]]["top_attachment_location_ids"])
        links = list(pairwise(ordered_tops))
        if course["course_form"] == "CYCLIC" and len(ordered_tops) > 1:
            links.append((ordered_tops[-1], ordered_tops[0]))
        for left_location_id, right_location_id in links:
            edges.append(
                GraphEdge(
                    "COURSE",
                    left_location_id,
                    right_location_id,
                    course_id,
                )
            )

    # Yarn-path adjacency follows declared segment event order but does not
    # claim a physical attachment-location continuity between shaped stitches.
    yarn_path_links: list[YarnPathLink] = []
    for yarn_path in sorted(value["yarn_paths"], key=lambda item: item["yarn_path_id"]):
        for segment_index, segment in enumerate(yarn_path["segments"]):
            path_stitches = [
                event_subjects[event_id]["stitch_id"]
                for event_id in segment["event_ids"]
                if event_subjects[event_id]["entity_type"] == "STITCH"
            ]
            for left_id, right_id in pairwise(path_stitches):
                yarn_path_links.append(
                    YarnPathLink(
                        yarn_path_id=yarn_path["yarn_path_id"],
                        segment_index=segment_index,
                        source_stitch_id=left_id,
                        target_stitch_id=right_id,
                    )
                )

    edges.sort(
        key=lambda edge: (
            edge.edge_type,
            edge.course_id,
            edge.stitch_id or "",
            edge.source_location_id,
            edge.target_location_id,
        )
    )
    return ForwardGraph(
        projection_sha256=projection.sha256,
        material_sha256=material_hash,
        nodes=nodes,
        shaping_groups=tuple(shaping_groups),
        edges=tuple(edges),
        yarn_path_links=tuple(yarn_path_links),
        construction_operations=tuple(construction_operations),
        frontier_boundaries=tuple(frontier_boundaries),
        material_responses=tuple(selected[key] for key in sorted(selected)),
    )
