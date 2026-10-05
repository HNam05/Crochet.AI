"""Human instructions and an explicitly schematic course layout from CrochetIR."""

from __future__ import annotations

from math import cos, pi, sin
from typing import Any

_STITCH_DE = {"SINGLE_CROCHET": "fM"}


def present_ir(
    value: dict[str, Any],
    color_hex: str,
    session: dict[str, Any],
    stitch_pitch_mm: float,
    course_pitch_mm: float,
    source_sha256: str,
) -> dict[str, Any]:
    events = sorted(value["construction_sequence"], key=lambda event: event["sequence_index"])
    stitches = {stitch["stitch_id"]: stitch for stitch in value["stitches"]}
    operations = {op["operation_id"]: op for op in value["construction_operations"]}
    locations = {
        location["attachment_location_id"]: location for location in value["attachment_locations"]
    }
    frontiers = {frontier["frontier_id"]: frontier for frontier in value["frontiers"]}
    courses_by_event = {
        event_id: course for course in value["courses"] for event_id in course["member_event_ids"]
    }
    points: list[dict[str, Any]] = []
    steps: list[dict[str, Any]] = []
    course_rows: list[dict[str, Any]] = []
    totals: dict[str, int] = {}
    for course in sorted(value["courses"], key=lambda item: item["ordinal"]):
        members = [event for event in events if event["event_id"] in course["member_event_ids"]]
        stitch_count = sum(
            len(stitches[event["subject_ref"]["stitch_id"]]["top_attachment_location_ids"])
            for event in members
            if event["subject_ref"]["entity_type"] == "STITCH"
        )
        totals[course["course_id"]] = stitch_count
        course_rows.append(
            {
                "course_id": course["course_id"],
                "number": course["ordinal"] + 1,
                "total_stitches": stitch_count,
                "summary_de": f"{course['ordinal'] + 1}. Runde: {stitch_count} Maschen",
                "step_ids": [event["event_id"] for event in members],
            }
        )
    event_course: dict[str, int] = {}
    stitches_after: dict[str, int] = {}
    course_consumed: dict[str, int] = {}
    visible_locations: dict[str, tuple[str, str]] = {}
    for course in sorted(value["courses"], key=lambda item: item["ordinal"]):
        running = 0
        for event_id in course["member_event_ids"]:
            event_course[event_id] = course["ordinal"] + 1
            event = next(item for item in events if item["event_id"] == event_id)
            if event["subject_ref"]["entity_type"] == "STITCH":
                running += len(
                    stitches[event["subject_ref"]["stitch_id"]]["top_attachment_location_ids"]
                )
            stitches_after[event_id] = running
    for event in events:
        ref = event["subject_ref"]
        course = courses_by_event.get(event["event_id"])
        if ref["entity_type"] == "STITCH":
            stitch = stitches[ref["stitch_id"]]
            kind = stitch["shaping"]
            de = _STITCH_DE.get(stitch["stitch_type"])
            if de is None:
                raise ValueError("presentation.unsupported_stitch")
            if kind == "INCREASE":
                instruction = f"{de} zweimal in dieselbe Einstichstelle"
            elif kind == "DECREASE":
                instruction = f"2 Maschen gemeinsam abmaschen ({de})"
            else:
                instruction = f"{de} in die nächste Masche"
            bases = stitch["base_attachment_location_ids"]
            tops = stitch["top_attachment_location_ids"]
            base_locations = [locations[base] for base in bases]
            if len(set(bases)) != len(base_locations):
                raise ValueError("presentation.duplicate_base")
            if base_locations and base_locations[0]["location_type"] == "MAGIC_RING_ANCHOR":
                instruction = f"{de} in denselben Fadenring"
            if course is not None and bases:
                available = frontiers[course["input_frontier_ids"][0]]["attachment_location_ids"]
                positions = [available.index(base) + 1 for base in bases]
                cursor = course_consumed.get(course["course_id"], 0)
                expected = [
                    ((cursor + offset) % len(available)) + 1 for offset in range(len(bases))
                ]
                if positions != expected:
                    targets = " und ".join(str(position) for position in positions)
                    instruction += f" an Einstichstelle {targets} der Vorrunde"
                course_consumed[course["course_id"]] = cursor + len(bases)
            for top in tops:
                visible_locations[top] = (stitch["stitch_id"], event["event_id"])
            event_kind = "STITCH"
            produced = len(tops)
        else:
            op = operations[ref["operation_id"]]
            typ = op["operation_type"]
            operation_instruction = {
                "MAGIC_RING": "Fadenring beginnen", "CLOSE": "Arbeit schließen",
            }.get(typ)
            if operation_instruction is None:
                raise ValueError("presentation.unsupported_operation")
            instruction = operation_instruction
            bases, tops, event_kind, produced = [], [], typ, 0
        number = event_course.get(event["event_id"])
        step_course_id = course["course_id"] if course else None
        steps.append(
            {
                "step_id": event["event_id"],
                "event_index": event["sequence_index"],
                "course_id": step_course_id,
                "course_number": number,
                "kind": event_kind,
                "stitch_id": ref.get("stitch_id"),
                "instruction_de": instruction,
                "base_location_ids": bases,
                "top_location_ids": tops,
                "produced_stitches": produced,
                "course_stitches_after": stitches_after.get(event["event_id"], 0),
            }
        )
    course_sizes = {course["course_id"]: course["ordinal"] + 1 for course in value["courses"]}
    course_positions: dict[str, tuple[int, int]] = {}
    event_map = {event["event_id"]: event for event in events}
    for item in value["courses"]:
        ordered_top_ids = [
            location_id
            for event_id in item["member_event_ids"]
            if event_map[event_id]["subject_ref"]["entity_type"] == "STITCH"
            for location_id in stitches[event_map[event_id]["subject_ref"]["stitch_id"]][
                "top_attachment_location_ids"
            ]
        ]
        for ordinal, location_id in enumerate(ordered_top_ids):
            course_positions[location_id] = (ordinal, len(ordered_top_ids))
    for location_id, (stitch_id, step_id) in visible_locations.items():
        producer = next(step for step in steps if step["step_id"] == step_id)
        course_id = producer["course_id"]
        ordinal, count = course_positions[location_id]
        count = max(count, 1)
        angle = 2 * pi * (ordinal + 0.5) / count
        radius = count * stitch_pitch_mm / (2 * pi)
        points.append(
            {
                "location_id": location_id,
                "stitch_id": stitch_id,
                "step_id": step_id,
                "course_id": course_id,
                "xyz_mm": [
                    radius * cos(angle),
                    course_sizes[course_id] * course_pitch_mm,
                    radius * sin(angle),
                ],
                "color_hex": color_hex,
            }
        )
    digest = source_sha256
    return {
        "prototype_version": "1.0.0",
        "project_id": digest,
        "request": {},
        "design_spec": {},
        "material_profile": {},
        "crochet_ir": value,
        "run_config": {},
        "pattern_text": "",
        "source_crochet_ir_sha256": digest,
        "semantic_validation": "PASS",
        "round_trip_state": "PASS",
        "verification_state": "NOT_VERIFIED",
        "physical_status": "UNTESTED",
        "generation": {"status": "CANDIDATES_EMITTED", "reason": "domain.complete", "work": {}},
        "courses": course_rows,
        "steps": steps,
        "preview": {
            "profile": "SCHEMATIC_COURSE_LAYOUT_V1",
            "unit": "mm",
            "role": "ILLUSTRATIVE_NOT_PHYSICAL",
            "points": points,
        },
        "session": session,
    }
