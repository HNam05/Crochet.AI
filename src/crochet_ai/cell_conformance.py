"""Independent source-to-face verification for closed surface cells V1."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, cast

from .canonical import CanonicalProfile, canonical_hash, jcs_bytes
from .json_types import JSONValue
from .validation import SemanticValidator

PROFILE = "CLOSED_CELL_CONFORMANCE_V1"
SURFACE_PROFILE = "FORWARD_CLOSED_SURFACE_CELLS_V1"
RULE_ID = "cyclic-span-zipper-fan-caps/1"
MAX_VERTICES = 30_000
MAX_FACES = 60_000
MAX_EVENTS = 30_000
_REPORT_DOMAIN = b"Crochet.AI\0CLOSED_CELL_CONFORMANCE_V1\0"


class CellConformanceInputError(ValueError):
    """Malformed input or a conformance resource limit, with no partial report."""


@dataclass(frozen=True, slots=True)
class CellConformanceReport:
    status: str
    diagnostics: tuple[str, ...]
    source_ir_sha256: str
    projection_sha256: str
    surface_cells_sha256: str
    checked_face_count: int
    checked_stitch_count: int
    checked_course_count: int
    max_vertices: int
    max_faces: int
    max_events: int
    canonical_bytes: bytes
    sha256: str

    def to_dict(self) -> dict[str, JSONValue]:
        return cast(
            dict[str, JSONValue],
            {
                "profile": PROFILE,
                "status": self.status,
                "diagnostics": list(self.diagnostics),
                "source_ir_sha256": self.source_ir_sha256,
                "projection_sha256": self.projection_sha256,
                "surface_cells_sha256": self.surface_cells_sha256,
                "checked_face_count": self.checked_face_count,
                "checked_stitch_count": self.checked_stitch_count,
                "checked_course_count": self.checked_course_count,
                "budgets": {
                    "max_vertices": self.max_vertices,
                    "max_faces": self.max_faces,
                    "max_events": self.max_events,
                },
            },
        )


def inspect_closed_cell_conformance(
    ir: dict[str, Any],
    surface_cells: object,
    *,
    validator: SemanticValidator,
    projection_sha256: str,
    surface_cells_sha256: str,
    max_vertices: int = MAX_VERTICES,
    max_faces: int = MAX_FACES,
    max_events: int = MAX_EVENTS,
) -> CellConformanceReport:
    """Verify each submitted face against its source stitch slot and lifecycle."""
    _check_budgets(max_vertices, max_faces, max_events)
    if not isinstance(ir, dict) or not isinstance(validator, SemanticValidator):
        raise CellConformanceInputError("cell_conformance.invalid_source_input")
    if not _digest(projection_sha256) or not _digest(surface_cells_sha256):
        raise CellConformanceInputError("cell_conformance.invalid_digest")
    _precheck_source(ir, max_events, max_vertices)
    source_digest = canonical_hash(ir, CanonicalProfile.CROCHET_IR, validator=validator)
    if not isinstance(surface_cells, dict):
        raise CellConformanceInputError("cell_conformance.invalid_surface_cells")
    cells = surface_cells
    _precheck_cells(cells, max_vertices, max_faces)
    diagnostics: list[str] = []
    if set(cells) != {"profile", "status", "projection_sha256", "rule_id", "vertices", "faces"}:
        raise CellConformanceInputError("cell_conformance.invalid_surface_envelope")
    if (
        cells.get("profile") != SURFACE_PROFILE
        or cells.get("status") != "TOPOLOGY_ONLY"
        or cells.get("rule_id") != RULE_ID
        or cells.get("projection_sha256") != projection_sha256
    ):
        diagnostics.append("surface.envelope_mismatch")
    content_digest = _surface_digest(cells, projection_sha256)
    if content_digest != surface_cells_sha256:
        diagnostics.append("surface.digest_mismatch")

    source = _source_cycles(ir)
    if source is None:
        status = "FAIL" if diagnostics else "NOT_APPLICABLE"
        source_diagnostics = tuple(diagnostics) or ("source.construction_outside_profile",)
        return _report(
            status,
            source_diagnostics,
            source_digest,
            projection_sha256,
            surface_cells_sha256,
            0,
            0,
            0,
            max_vertices,
            max_faces,
            max_events,
        )
    anchors, courses, stitch_count, event_count = source
    if event_count > max_events:
        raise CellConformanceInputError("cell_conformance.event_budget_exceeded")
    expected_vertices = sorted({*anchors, *(v for band in courses for v in band[1])})
    vertices = cells["vertices"]
    faces = cells["faces"]
    assert isinstance(vertices, list) and isinstance(faces, list)
    if vertices != expected_vertices:
        diagnostics.append("surface.vertex_set_mismatch")
    face_index = 0
    for lower, upper, members in courses:
        base_prefix = 0
        top_prefix = 0
        lower_size, upper_size = len(lower), len(upper)
        for bases, tops in members:
            # Every base slot precedes every top slot for this stitch.
            for offset in range(len(bases)):
                expected = (
                    lower[(base_prefix + offset) % lower_size],
                    lower[(base_prefix + offset + 1) % lower_size],
                    upper[top_prefix % upper_size],
                )
                _compare_face(faces, face_index, expected, diagnostics)
                face_index += 1
            base_prefix += len(bases)
            for offset in range(len(tops)):
                expected = (
                    lower[base_prefix % lower_size],
                    upper[(top_prefix + offset + 1) % upper_size],
                    upper[(top_prefix + offset) % upper_size],
                )
                _compare_face(faces, face_index, expected, diagnostics)
                face_index += 1
            top_prefix += len(tops)
        if base_prefix != lower_size or top_prefix != upper_size:
            diagnostics.append("source.band_coverage_mismatch")
    for offset in range(1, len(anchors) - 1):
        _compare_face(
            faces, face_index, (anchors[0], anchors[offset + 1], anchors[offset]), diagnostics
        )
        face_index += 1
    terminal = courses[-1][1]
    for offset in range(1, len(terminal) - 1):
        _compare_face(
            faces, face_index, (terminal[0], terminal[offset], terminal[offset + 1]), diagnostics
        )
        face_index += 1
    if face_index != len(faces):
        diagnostics.append("surface.face_count_mismatch")
    # Keep diagnostics stable when multiple exact slots fail.
    unique = tuple(dict.fromkeys(diagnostics))
    return _report(
        "FAIL" if unique else "PASS",
        unique,
        source_digest,
        projection_sha256,
        surface_cells_sha256,
        min(face_index, len(faces)),
        stitch_count,
        len(courses),
        max_vertices,
        max_faces,
        max_events,
    )


def _source_cycles(
    ir: dict[str, Any],
) -> (
    tuple[list[str], list[tuple[list[str], list[str], list[tuple[list[str], list[str]]]]], int, int]
    | None
):
    operations = {row["operation_id"]: row for row in ir["construction_operations"]}
    events = sorted(ir["construction_sequence"], key=lambda row: row["sequence_index"])
    op_events = [
        event["subject_ref"].get("operation_id")
        for event in events
        if event["subject_ref"].get("entity_type") == "CONSTRUCTION_OPERATION"
    ]
    ring_ops = [op for op in operations.values() if op["operation_type"] == "MAGIC_RING"]
    close_ops = [op for op in operations.values() if op["operation_type"] == "CLOSE"]
    if (
        len(ir["components"]) != 1
        or len(ir["branches"]) != 1
        or len(ir["yarns"]) != 1
        or ir["openings"]
        or len(ring_ops) != 1
        or len(close_ops) != 1
        or len(operations) != 2
    ):
        return None
    if (
        not events
        or op_events[0] != ring_ops[0]["operation_id"]
        or op_events[-1] != close_ops[0]["operation_id"]
    ):
        return None
    stitches = {row["stitch_id"]: row for row in ir["stitches"]}
    event_by_id = {row["event_id"]: row for row in events}
    event_position = {row["event_id"]: index for index, row in enumerate(events)}
    courses_by_id = {row["course_id"]: row for row in ir["courses"]}
    frontiers = {row["frontier_id"]: row for row in ir["frontiers"]}
    ring = ring_ops[0]
    ring_event = next(
        event
        for event in events
        if event["subject_ref"].get("operation_id") == ring["operation_id"]
    )
    if events[0] is not ring_event or len(ring["attachment_location_ids"]) < 3:
        return None
    anchors = list(ring["attachment_location_ids"])
    ring_output = ring["output_frontier_ids"]
    if (
        len(set(anchors)) != len(anchors)
        or len(ring_output) != 1
        or frontiers[ring_output[0]]["attachment_location_ids"] != anchors
        or frontiers[ring_output[0]]["anchor_attachment_location_id"] != anchors[0]
    ):
        return None
    if not ir["course_order"] or set(ir["course_order"]) != set(courses_by_id):
        return None
    course_rows = [courses_by_id[cid] for cid in ir["course_order"]]
    if [row["ordinal"] for row in course_rows] != sorted(row["ordinal"] for row in course_rows):
        return None
    lower = anchors
    bands: list[tuple[list[str], list[str], list[tuple[list[str], list[str]]]]] = []
    seen_cycle_ids = set(anchors)
    direction: str | None = None
    covered_events = [ring_event["event_id"]]
    stitch_total = 0
    for course in course_rows:
        if course["course_form"] != "CYCLIC" or course["work_direction"] not in {
            "CLOCKWISE",
            "COUNTERCLOCKWISE",
        }:
            return None
        if direction is not None and direction != course["work_direction"]:
            return None
        direction = course["work_direction"]
        ordered_events = [event_by_id[eid] for eid in course["member_event_ids"]]
        if any(e["subject_ref"].get("entity_type") != "STITCH" for e in ordered_events):
            return None
        positions = [event_position[e["event_id"]] for e in ordered_events]
        if positions != sorted(positions) or len(set(positions)) != len(positions):
            return None
        bases: list[str] = []
        tops: list[str] = []
        members: list[tuple[list[str], list[str]]] = []
        for event in ordered_events:
            sid = event["subject_ref"].get("stitch_id")
            stitch = stitches.get(sid)
            if stitch is None or stitch["stitch_type"] != "SINGLE_CROCHET":
                return None
            sb = list(stitch["base_attachment_location_ids"])
            st = list(stitch["top_attachment_location_ids"])
            shape = {(1, 1): "PLAIN", (1, 2): "INCREASE", (2, 1): "DECREASE"}.get(
                (len(sb), len(st))
            )
            if shape is None or stitch["shaping"] != shape:
                return None
            members.append((sb, st))
            bases.extend(sb)
            tops.extend(st)
            covered_events.append(event["event_id"])
        if (
            bases != lower
            or len(tops) < 3
            or len(set(tops)) != len(tops)
            or seen_cycle_ids.intersection(tops)
        ):
            return None
        if len(course["input_frontier_ids"]) != 1 or len(course["output_frontier_ids"]) != 1:
            return None
        input_frontier = frontiers[course["input_frontier_ids"][0]]
        if (
            input_frontier["attachment_location_ids"] != lower
            or input_frontier["anchor_attachment_location_id"] != lower[0]
        ):
            return None
        output_frontier = frontiers[course["output_frontier_ids"][0]]
        if (
            output_frontier["attachment_location_ids"] != tops
            or output_frontier["anchor_attachment_location_id"] != tops[0]
        ):
            return None
        bands.append((lower, tops, members))
        seen_cycle_ids.update(tops)
        lower = tops
        stitch_total += len(members)
    close = close_ops[0]
    close_event = next(
        event
        for event in events
        if event["subject_ref"].get("operation_id") == close["operation_id"]
    )
    if (
        len(close["input_frontier_ids"]) != 1
        or len(close["output_frontier_ids"]) != 1
        or frontiers[close["input_frontier_ids"][0]]["attachment_location_ids"] != lower
        or frontiers[close["input_frontier_ids"][0]]["anchor_attachment_location_id"] != lower[0]
        or frontiers[close["output_frontier_ids"][0]]["lifecycle_state"] != "CLOSED"
        or frontiers[close["output_frontier_ids"][0]]["attachment_location_ids"]
    ):
        return None
    covered_events.append(close_event["event_id"])
    if covered_events != [event["event_id"] for event in events]:
        return None
    return anchors, bands, stitch_total, len(events)


def _compare_face(
    faces: list[Any], index: int, expected: tuple[str, str, str], diagnostics: list[str]
) -> None:
    if index >= len(faces):
        diagnostics.append("surface.missing_face")
        return
    actual = faces[index]
    if not isinstance(actual, list) or len(actual) != 3 or tuple(actual) != expected:
        diagnostics.append(f"surface.face_mismatch:{index}")


def _precheck_source(ir: dict[str, Any], max_events: int, max_vertices: int) -> None:
    sequence = ir.get("construction_sequence")
    if not isinstance(sequence, list):
        raise CellConformanceInputError("cell_conformance.invalid_source_events")
    if len(sequence) > max_events:
        raise CellConformanceInputError("cell_conformance.event_budget_exceeded")
    source_table_limit = max(max_vertices, max_events)
    for _field, table in ir.items():
        if isinstance(table, list) and len(table) > source_table_limit:
            raise CellConformanceInputError("cell_conformance.source_table_budget_exceeded")
    for field in (
        "attachment_locations",
        "stitches",
        "construction_operations",
        "courses",
        "frontiers",
        "course_order",
    ):
        if not isinstance(ir.get(field), list):
            raise CellConformanceInputError("cell_conformance.invalid_source_table")
    _check_source_identifiers(ir, source_table_limit)


def _check_source_identifiers(value: object, max_items: int) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and (key.endswith("_id") or key.endswith("_ids")):
                if key.endswith("_ids") and not isinstance(child, list):
                    raise CellConformanceInputError(
                        "cell_conformance.invalid_source_identifier_list"
                    )
                if isinstance(child, list) and len(child) > max_items:
                    raise CellConformanceInputError(
                        "cell_conformance.source_identifier_budget_exceeded"
                    )
                identifiers = child if isinstance(child, list) else [child]
                for identifier in identifiers:
                    if identifier is not None and not _source_id(identifier):
                        raise CellConformanceInputError(
                            "cell_conformance.invalid_source_identifier"
                        )
            _check_source_identifiers(child, max_items)
    elif isinstance(value, list):
        for child in value:
            _check_source_identifiers(child, max_items)


def _precheck_cells(cells: dict[Any, Any], max_vertices: int, max_faces: int) -> None:
    vertices, faces = cells.get("vertices"), cells.get("faces")
    if not isinstance(vertices, list) or not isinstance(faces, list):
        raise CellConformanceInputError("cell_conformance.invalid_cell_arrays")
    if len(vertices) > max_vertices:
        raise CellConformanceInputError("cell_conformance.vertex_budget_exceeded")
    if len(faces) > max_faces:
        raise CellConformanceInputError("cell_conformance.face_budget_exceeded")
    for identifier in vertices:
        if not _source_id(identifier):
            raise CellConformanceInputError("cell_conformance.invalid_surface_identifier")
    for face in faces:
        if (
            not isinstance(face, list)
            or len(face) != 3
            or any(not _source_id(item) for item in face)
        ):
            raise CellConformanceInputError("cell_conformance.invalid_face")


def _source_id(value: object) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 128 and value.isascii()


def _check_budgets(*budgets: int) -> None:
    limits = (MAX_VERTICES, MAX_FACES, MAX_EVENTS)
    if any(
        type(value) is not int or not 1 <= value <= limit
        for value, limit in zip(budgets, limits, strict=True)
    ):
        raise CellConformanceInputError("cell_conformance.invalid_budget")


def _digest(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def _surface_digest(cells: dict[Any, Any], projection: str) -> str:
    try:
        encoded = jcs_bytes(cast(JSONValue, cells))
    except (TypeError, ValueError) as exc:
        raise CellConformanceInputError("cell_conformance.invalid_surface_json") from exc
    return sha256(
        b"Crochet.AI\0"
        + SURFACE_PROFILE.encode("ascii")
        + b"\0"
        + projection.encode("ascii")
        + b"\0"
        + RULE_ID.encode("ascii")
        + b"\0"
        + encoded
    ).hexdigest()


def _report(
    status: str,
    diagnostics: tuple[str, ...],
    source: str,
    projection: str,
    cells: str,
    faces: int,
    stitches: int,
    courses: int,
    max_vertices: int,
    max_faces: int,
    max_events: int,
) -> CellConformanceReport:
    payload: dict[str, JSONValue] = {
        "profile": PROFILE,
        "status": status,
        "diagnostics": list(diagnostics),
        "source_ir_sha256": source,
        "projection_sha256": projection,
        "surface_cells_sha256": cells,
        "checked_face_count": faces,
        "checked_stitch_count": stitches,
        "checked_course_count": courses,
        "budgets": {"max_vertices": max_vertices, "max_faces": max_faces, "max_events": max_events},
    }
    encoded = jcs_bytes(payload)
    digest = sha256(_REPORT_DOMAIN + encoded).hexdigest()
    return CellConformanceReport(
        status,
        diagnostics,
        source,
        projection,
        cells,
        faces,
        stitches,
        courses,
        max_vertices,
        max_faces,
        max_events,
        encoded,
        digest,
    )
