"""Target-free combinatorial closed-cellulation convention, version 1.

The output is topology-only. Its zipper diagonals and fan caps are conventions,
not evidence of a realizable crochet surface or a physical simulation.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, cast

from .canonical import jcs_bytes, parse_json
from .json_types import JSONValue
from .physical_projection import PROFILE as PROJECTION_PROFILE
from .physical_projection import PhysicalSemanticProjection

PROFILE = "FORWARD_CLOSED_SURFACE_CELLS_V1"
RULE_ID = "cyclic-span-zipper-fan-caps/1"
MAX_VERTICES = 30_000
MAX_FACES = 60_000


class ClosedCellsError(ValueError):
    """Unsupported or malformed projected topology; no partial output exists."""


@dataclass(frozen=True, slots=True)
class ClosedSurfaceCells:
    profile: str
    status: str
    projection_sha256: str
    rule_id: str
    canonical_bytes: bytes
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        value = parse_json(self.canonical_bytes)
        if not isinstance(value, dict):
            raise ClosedCellsError("closed_cells.internal_payload_shape")
        return value


def build_closed_surface_cells(
    projection: PhysicalSemanticProjection,
    *,
    max_vertices: int = MAX_VERTICES,
    max_faces: int = MAX_FACES,
) -> ClosedSurfaceCells:
    """Build a bounded oriented triangle complex from an admitted projection.

    Budgets are exact positive integers. Checks and a count-only topology pass
    run before vertex/face output arrays are allocated.
    """
    if not isinstance(projection, PhysicalSemanticProjection):
        raise TypeError("projection must be PhysicalSemanticProjection")
    if type(max_vertices) is not int or not 1 <= max_vertices <= MAX_VERTICES:
        raise ClosedCellsError("closed_cells.invalid_vertex_budget")
    if type(max_faces) is not int or not 1 <= max_faces <= MAX_FACES:
        raise ClosedCellsError("closed_cells.invalid_face_budget")
    if (
        projection.sha256
        != sha256(
            b"Crochet.AI\0"
            + PROJECTION_PROFILE.encode("ascii")
            + b"\0"
            + projection.canonical_bytes
        ).hexdigest()
    ):
        raise ClosedCellsError("closed_cells.projection_hash_mismatch")

    value = projection.to_dict()
    try:
        _admit_profile(value)
        anchors, courses, terminal, schedules = _extract_cycles(value)
        # Cycles share adjacent course boundaries; count unique labels instead.
        all_ids = set(anchors)
        for cycle in courses:
            all_ids.update(cycle)
        all_ids.update(terminal)
        vertex_count = len(all_ids)
        face_count = sum(
            _annulus_face_count(lower, upper)
            for lower, upper in zip([anchors, *courses[:-1]], courses, strict=True)
        )
        face_count += max(0, len(anchors) - 2) + max(0, len(terminal) - 2)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        if isinstance(exc, ClosedCellsError):
            raise
        raise ClosedCellsError("closed_cells.invalid_projected_topology") from exc
    if vertex_count > max_vertices:
        raise ClosedCellsError("closed_cells.vertex_budget_exceeded")
    if face_count > max_faces:
        raise ClosedCellsError("closed_cells.face_budget_exceeded")

    faces: list[tuple[str, str, str]] = []
    lower = anchors
    for upper, schedule in zip(courses, schedules, strict=True):
        faces.extend(_zipper_faces(lower, upper, schedule))
        lower = upper
    faces.extend(_fan(anchors, reverse=True))
    faces.extend(_fan(terminal, reverse=False))
    if len(faces) != face_count:
        raise ClosedCellsError("closed_cells.internal_face_count")
    payload = {
        "profile": PROFILE,
        "status": "TOPOLOGY_ONLY",
        "projection_sha256": projection.sha256,
        "rule_id": RULE_ID,
        "vertices": sorted(all_ids),
        "faces": [list(face) for face in faces],
    }
    encoded = jcs_bytes(cast(JSONValue, payload))
    digest = sha256(
        b"Crochet.AI\0"
        + PROFILE.encode("ascii")
        + b"\0"
        + projection.sha256.encode("ascii")
        + b"\0"
        + RULE_ID.encode("ascii")
        + b"\0"
        + encoded
    ).hexdigest()
    return ClosedSurfaceCells(PROFILE, "TOPOLOGY_ONLY", projection.sha256, RULE_ID, encoded, digest)


def _admit_profile(value: dict[str, Any]) -> None:
    if (
        value.get("profile") != "FORWARD_PHYSICAL_SEMANTICS_V1"
        or len(value["components"]) != 1
        or len(value["branches"]) != 1
        or len(value["yarns"]) != 1
        or value["openings"]
        or sorted(op["operation_type"] for op in value["construction_operations"])
        != ["CLOSE", "MAGIC_RING"]
        or any(stitch["stitch_type"] != "SINGLE_CROCHET" for stitch in value["stitches"])
    ):
        raise ClosedCellsError("closed_cells.unsupported_construction")


def _extract_cycles(
    value: dict[str, Any],
) -> tuple[list[str], list[list[str]], list[str], list[list[tuple[int, int]]]]:
    frontiers = {row["frontier_id"]: row for row in value["frontiers"]}
    stitches = {row["stitch_id"]: row for row in value["stitches"]}
    operations = {row["operation_id"]: row for row in value["construction_operations"]}
    events = sorted(value["construction_sequence"], key=lambda row: row["sequence_index"])
    event_by_id = {event["event_id"]: event for event in events}
    ring_op = next(op for op in operations.values() if op["operation_type"] == "MAGIC_RING")
    close_op = next(op for op in operations.values() if op["operation_type"] == "CLOSE")
    anchors = list(ring_op["attachment_location_ids"])
    if len(anchors) < 3 or len(set(anchors)) != len(anchors):
        raise ClosedCellsError("closed_cells.invalid_ring_cycle")
    ring_frontier = frontiers[ring_op["output_frontier_ids"][0]]
    if (
        ring_frontier["attachment_location_ids"] != anchors
        or ring_frontier["anchor_attachment_location_id"] != anchors[0]
    ):
        raise ClosedCellsError("closed_cells.ring_anchor_mismatch")

    course_by_id = {row["course_id"]: row for row in value["courses"]}
    if not course_by_id or value["course_order"] != [
        row["course_id"] for row in sorted(course_by_id.values(), key=lambda row: row["ordinal"])
    ]:
        raise ClosedCellsError("closed_cells.course_order_mismatch")
    previous = anchors
    cycles: list[list[str]] = []
    schedules: list[list[tuple[int, int]]] = []
    direction: str | None = None
    for course_id in value["course_order"]:
        course = course_by_id[course_id]
        if course["course_form"] != "CYCLIC" or course["work_direction"] not in {
            "CLOCKWISE",
            "COUNTERCLOCKWISE",
        }:
            raise ClosedCellsError("closed_cells.unsupported_course")
        if direction is None:
            direction = course["work_direction"]
        elif course["work_direction"] != direction:
            raise ClosedCellsError("closed_cells.inconsistent_work_direction")
        if len(course["input_frontier_ids"]) != 1:
            raise ClosedCellsError("closed_cells.ambiguous_course_input")
        input_frontier = frontiers[course["input_frontier_ids"][0]]
        if input_frontier["attachment_location_ids"] != previous:
            raise ClosedCellsError("closed_cells.frontier_cycle_mismatch")
        try:
            member_events = [event_by_id[event_id] for event_id in course["member_event_ids"]]
        except KeyError as exc:
            raise ClosedCellsError("closed_cells.course_membership_mismatch") from exc
        members = [event["subject_ref"]["stitch_id"] for event in member_events]
        if len(members) == 0 or any(
            event["subject_ref"]["entity_type"] != "STITCH" for event in member_events
        ):
            raise ClosedCellsError("closed_cells.course_membership_mismatch")
        bases: list[str] = []
        tops: list[str] = []
        schedule: list[tuple[int, int]] = []
        for sid in members:
            stitch = stitches[sid]
            sb, st = (
                list(stitch["base_attachment_location_ids"]),
                list(stitch["top_attachment_location_ids"]),
            )
            if (
                len(sb) != stitch["base_arity"]
                or len(st) != stitch["top_arity"]
                or not sb
                or not st
            ):
                raise ClosedCellsError("closed_cells.invalid_stitch_arity")
            bases.extend(sb)
            tops.extend(st)
            schedule.append((len(sb), len(st)))
            expected_shape = {
                (1, 1): "PLAIN",
                (1, 2): "INCREASE",
                (2, 1): "DECREASE",
            }.get((len(sb), len(st)))
            if expected_shape is None or stitch["shaping"] != expected_shape:
                raise ClosedCellsError("closed_cells.unsupported_span")
        if bases != previous or len(set(tops)) != len(tops) or len(tops) < 3:
            raise ClosedCellsError("closed_cells.cyclic_span_partition")
        output_ids = course["output_frontier_ids"]
        if len(output_ids) != 1:
            raise ClosedCellsError("closed_cells.ambiguous_course_output")
        output_frontier = frontiers[output_ids[0]]
        if output_frontier["attachment_location_ids"] != tops:
            raise ClosedCellsError("closed_cells.top_cycle_mismatch")
        cycles.append(tops)
        schedules.append(schedule)
        previous = tops
    close_frontier = frontiers[close_op["input_frontier_ids"][0]]
    if close_frontier["attachment_location_ids"] != previous or len(previous) < 3:
        raise ClosedCellsError("closed_cells.terminal_cycle_mismatch")
    if len(close_op["output_frontier_ids"]) != 1:
        raise ClosedCellsError("closed_cells.close_output_mismatch")
    closed_frontier = frontiers[close_op["output_frontier_ids"][0]]
    if closed_frontier["lifecycle_state"] != "CLOSED" or closed_frontier["attachment_location_ids"]:
        raise ClosedCellsError("closed_cells.close_output_mismatch")
    if not cycles:
        raise ClosedCellsError("closed_cells.empty_surface")
    all_cycle_ids = [*anchors, *(location_id for cycle in cycles for location_id in cycle)]
    if len(all_cycle_ids) != len(set(all_cycle_ids)):
        raise ClosedCellsError("closed_cells.repeated_vertex_id")
    return anchors, cycles, previous, schedules


def _annulus_face_count(lower: list[str], upper: list[str]) -> int:
    n, m = len(lower), len(upper)
    if n < 3 or m < 3:
        raise ClosedCellsError("closed_cells.frontier_too_small")
    return n + m


def _zipper_faces(
    lower: list[str], upper: list[str], schedule: list[tuple[int, int]]
) -> list[tuple[str, str, str]]:
    n, m = len(lower), len(upper)
    i = j = 0
    faces: list[tuple[str, str, str]] = []
    # Within each stitch span, emit all base advances before its top advances.
    for lower_steps, upper_steps in schedule:
        for _ in range(lower_steps):
            bi, tj = lower[i % n], upper[j % m]
            bn = lower[(i + 1) % n]
            faces.append((bi, bn, tj))
            i += 1
        for _ in range(upper_steps):
            bi, tj = lower[i % n], upper[j % m]
            tn = upper[(j + 1) % m]
            faces.append((bi, tn, tj))
            j += 1
    if i != n or j != m:
        raise ClosedCellsError("closed_cells.cycle_coverage_mismatch")
    return faces


def _fan(cycle: list[str], *, reverse: bool) -> list[tuple[str, str, str]]:
    if len(cycle) < 3:
        raise ClosedCellsError("closed_cells.cap_too_small")
    return [
        (cycle[0], cycle[i + 1], cycle[i]) if reverse else (cycle[0], cycle[i], cycle[i + 1])
        for i in range(1, len(cycle) - 1)
    ]
