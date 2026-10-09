"""Deterministic print export for a saved local prototype project."""

from __future__ import annotations

from html import escape
from io import BytesIO
from itertools import groupby
from typing import Any

import rfc8785
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from .canonical import CanonicalProfile, canonical_hash
from .prototype_input import assemble_request
from .prototype_presentation import present_ir
from .validation import SemanticValidator


class PrototypePdfError(ValueError):
    """Saved project cannot be safely represented in a printable document."""


_SHAPE_EN = {
    "sphere": "Sphere",
    "ellipsoid": "Ellipsoid",
    "cylinder": "Cylinder",
    "cone": "Cone",
    "capsule": "Capsule",
    "pear": "Pear",
}

# Four millimeters of cell padding alone must not become a visible row fragment.
_ROUND_ROW_MIN_SPLIT_HEIGHT = 23


def _run_notation(instructions: list[str]) -> str:
    groups: list[str] = []
    for instruction, members in groupby(instructions):
        count = sum(1 for _ in members)
        if instruction == "1 sc":
            groups.append(f"{count} sc")
        elif instruction in {"inc sc", "dec sc"} and count > 1:
            groups.append(f"{count} {instruction}")
        else:
            groups.extend([instruction] * count)
    return ", ".join(groups)


def _round_notation(instructions: list[str]) -> str:
    """Compact literal repeats and runs; preserve their order and any remainder."""
    if not instructions:
        raise PrototypePdfError("pdf.unsupported_ir")
    for size in range(1, len(instructions) // 2 + 1):
        repetitions = len(instructions) // size
        end = size * repetitions
        if instructions[:end] != instructions[:size] * repetitions:
            continue
        motif = _run_notation(instructions[:size])
        if size == 1 and instructions[0] in {"1 sc", "inc sc", "dec sc"}:
            repeated = _run_notation(instructions[:end])
        else:
            repeated = f"({motif}) x {repetitions}"
        tail = _run_notation(instructions[end:])
        return repeated + (", " + tail if tail else "")
    return _run_notation(instructions)


def _course_notation(course: dict[str, Any], ir: dict[str, Any]) -> tuple[str, int]:
    """Export a complete cyclic SC round from canonical bases and tops only."""
    events = {event["event_id"]: event for event in ir["construction_sequence"]}
    stitches = {stitch["stitch_id"]: stitch for stitch in ir["stitches"]}
    frontiers = {frontier["frontier_id"]: frontier for frontier in ir["frontiers"]}
    locations = {
        location["attachment_location_id"]: location for location in ir["attachment_locations"]
    }
    if (
        course["course_form"] != "CYCLIC"
        or course["turn_mode"] != "CONTINUOUS_SPIRAL"
        or len(course["input_frontier_ids"]) != 1
        or len(course["output_frontier_ids"]) != 1
    ):
        raise PrototypePdfError("pdf.unsupported_ir")
    available = frontiers[course["input_frontier_ids"][0]]["attachment_location_ids"]
    if not available:
        raise PrototypePdfError("pdf.unsupported_ir")
    initial = course["ordinal"] == 0
    consumed = total = 0
    instructions: list[str] = []
    for event_id in course["member_event_ids"]:
        ref = events[event_id]["subject_ref"]
        if ref["entity_type"] != "STITCH":
            raise PrototypePdfError("pdf.unsupported_ir")
        stitch = stitches[ref["stitch_id"]]
        bases = stitch["base_attachment_location_ids"]
        tops = stitch["top_attachment_location_ids"]
        semantic = (stitch["stitch_type"], stitch["shaping"], len(bases), len(tops))
        notation = {
            ("SINGLE_CROCHET", "PLAIN", 1, 1): "1 sc",
            ("SINGLE_CROCHET", "INCREASE", 1, 2): "inc sc",
            ("SINGLE_CROCHET", "DECREASE", 2, 1): "dec sc",
        }.get(semantic)
        if notation is None:
            raise PrototypePdfError("pdf.unsupported_ir")
        ring_bases = all(locations[base]["location_type"] == "MAGIC_RING_ANCHOR" for base in bases)
        if initial != ring_bases or (initial and stitch["shaping"] != "PLAIN"):
            raise PrototypePdfError("pdf.unsupported_ir")
        positions = [available.index(base) + 1 for base in bases]
        expected = [((consumed + offset) % len(available)) + 1 for offset in range(len(bases))]
        if positions != expected:
            if initial:
                raise PrototypePdfError("pdf.unsupported_ir")
            notation += " at prior-round stitch " + " & ".join(map(str, positions))
        instructions.append(notation)
        consumed += len(bases)
        total += len(tops)
    output = frontiers[course["output_frontier_ids"][0]]["attachment_location_ids"]
    if consumed != len(available) or total != len(output):
        raise PrototypePdfError("pdf.unsupported_ir")
    return ("MR, " if initial else "") + _round_notation(instructions), total


def _text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise PrototypePdfError(f"pdf.{field}")
    try:
        value.encode("cp1252", errors="strict")
    except UnicodeEncodeError as error:
        raise PrototypePdfError("pdf.unsupported_unicode") from error
    return escape(value)


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "PdfTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=21,
            leading=25,
            textColor=colors.HexColor("#342E28"),
            alignment=TA_CENTER,
            spaceAfter=8 * mm,
        ),
        "heading": ParagraphStyle(
            "PdfHeading",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#342E28"),
            spaceBefore=4 * mm,
            spaceAfter=2 * mm,
        ),
        "body": ParagraphStyle(
            "PdfBody",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#342E28"),
            spaceAfter=2 * mm,
        ),
        "small": ParagraphStyle(
            "PdfSmall",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#514A43"),
        ),
        "round": ParagraphStyle(
            "PdfRound",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=12,
            textColor=colors.HexColor("#342E28"),
        ),
    }


def _validate_project(project: object, expected_id: str) -> dict[str, Any]:
    if not isinstance(project, dict) or project.get("project_id") != expected_id:
        raise PrototypePdfError("pdf.project_invalid")
    try:
        ir, design, material = (
            project["crochet_ir"],
            project["design_spec"],
            project["material_profile"],
        )
        if not all(isinstance(value, dict) for value in (ir, design, material)):
            raise TypeError
        validator = SemanticValidator(
            material_profiles={material["profile_id"]: material},
            design_specs={design["design_spec_id"]: design},
        )
        report = validator.validate_crochet_ir(ir)
        digest = canonical_hash(ir, CanonicalProfile.CROCHET_IR, validator=validator)
        if (
            not report.ok
            or digest != expected_id
            or project.get("source_crochet_ir_sha256") != digest
        ):
            raise PrototypePdfError("pdf.project_invalid")
        request = project["request"]
        if not isinstance(request, dict):
            raise TypeError
        provenance = material["provenance"]
        expected_design, expected_material, _ = assemble_request(
            request,
            software_commit=provenance["software_commit"],
            working_tree_dirty=provenance["working_tree_dirty"],
        )
        if rfc8785.dumps(expected_design) != rfc8785.dumps(design) or rfc8785.dumps(
            expected_material
        ) != rfc8785.dumps(material):
            raise PrototypePdfError("pdf.project_invalid")
        return project
    except PrototypePdfError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise PrototypePdfError("pdf.project_invalid") from error


def render_project_pdf(project: object, expected_id: str) -> bytes:
    """Render validated persisted IR and metadata; ignores stored prose and progress."""
    data = _validate_project(project, expected_id)
    request = data["request"]
    ir = data["crochet_ir"]
    material = data["material_profile"]
    design = data["design_spec"]
    gauge = material["calibration_responses"][0]["effective_gauge"]
    courses = sorted(ir["courses"], key=lambda course: course["ordinal"])
    try:
        presentation = present_ir(
            ir,
            design["colors"][0]["srgb_hex"],
            {"revision": 0, "cursor": 0},
            gauge["effective_stitch_pitch_mm"],
            gauge["effective_course_pitch_mm"],
            expected_id,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise PrototypePdfError("pdf.unsupported_ir") from error
    operations = {
        operation["operation_id"]: operation for operation in ir["construction_operations"]
    }
    ordered_events = sorted(ir["construction_sequence"], key=lambda event: event["sequence_index"])
    magic_ring_events = [
        event
        for event in ordered_events
        if event["subject_ref"]["entity_type"] == "CONSTRUCTION_OPERATION"
        and operations[event["subject_ref"]["operation_id"]]["operation_type"] == "MAGIC_RING"
    ]
    if len(magic_ring_events) != 1 or magic_ring_events[0] != ordered_events[0]:
        raise PrototypePdfError("pdf.unsupported_ir")
    style = _styles()
    story: list[Any] = [Paragraph("Crochet Pattern", style["title"])]
    requested_shape = request.get("shape")
    if not isinstance(requested_shape, str):
        raise PrototypePdfError("pdf.project_invalid")
    shape = _SHAPE_EN.get(requested_shape)
    if shape is None:
        raise PrototypePdfError("pdf.project_invalid")
    story.extend(
        [
            Paragraph(
                f"{shape}: maximum width / diameter {request['diameter_mm']:g} mm x "
                f"height {request['height_mm']:g} mm",
                style["heading"],
            ),
            Paragraph(
                f"Yarn: {_text(request['yarn_label'], 'yarn')} &nbsp; "
                f"Color: {_text(request['color_hex'], 'color')} &nbsp; "
                f"Hook: {request['hook_diameter_mm']:g} mm",
                style["body"],
            ),
            Paragraph(
                f"Gauge (entered): {request['stitches_per_100mm']} sc x "
                f"{request['courses_per_100mm']} rounds per 100 mm. "
                f"Interval / uncertainty assumption: +/-{request['uncertainty_percent']:g}%. "
                f"Effective pitch: {gauge['effective_stitch_pitch_mm']:.2f} mm per stitch "
                f"and {gauge['effective_course_pitch_mm']:.2f} mm per round.",
                style["body"],
            ),
            Paragraph(
                "Status: NOT_VERIFIED / UNTESTED. Dimensions and gauge are inputs; shape, fit, "
                "and physical size have not been confirmed.",
                style["body"],
            ),
            Paragraph(
                "US terms: MR = magic ring; sc = single crochet; "
                "inc sc = increase (2 sc in one stitch); "
                "dec sc = decrease (work the next 2 stitches together as one sc). "
                "Instructions follow "
                "the previous round's order. The final parentheses give the total stitches "
                "after completing that round.",
                style["body"],
            ),
            Paragraph(
                f"Start with an MR (magic ring), then work the "
                f"{presentation['courses'][0]['total_stitches']} "
                "sc in Round 1 into the ring as instructed below. Work continuously in a spiral "
                "and check off each round when complete. If stuffing is desired, add it during "
                "the final rounds before closing the opening; "
                "leaving it unstuffed is also possible.",
                style["body"],
            ),
        ]
    )
    for course in courses:
        round_text, total_stitches = _course_notation(course, ir)
        story.append(
            Table(
                [
                    [
                        Paragraph(
                            f"[ ] R{course['ordinal'] + 1}: "
                            f"{_text(round_text, 'instruction')} ({total_stitches} stitches)",
                            style["round"],
                        )
                    ]
                ],
                colWidths=[170 * mm],
                splitInRow=_ROUND_ROW_MIN_SPLIT_HEIGHT,
                style=TableStyle(
                    [
                        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#9B8B78")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
                        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
                    ]
                ),
            )
        )
        story.append(Spacer(1, 2 * mm))
    close_steps = [step for step in presentation["steps"] if step["kind"] == "CLOSE"]
    if len(close_steps) != 1:
        raise PrototypePdfError("pdf.unsupported_ir")
    story.append(
        Paragraph(
            "[ ] Close the remaining opening.",
            style["body"],
        )
    )
    story.extend(
        [
            PageBreak(),
            Paragraph("Feedback After Crocheting", style["title"]),
            Paragraph("Project short ID: " + expected_id[:12], style["body"]),
            Paragraph("Full CrochetIR SHA-256: " + expected_id, style["small"]),
            Paragraph(
                "Use this page to record your feedback. It does not automatically change "
                "verification status.",
                style["body"],
            ),
        ]
    )
    story.append(
        Paragraph(
            "Result: [ ] unstuffed  [ ] stuffed &nbsp;&nbsp; "
            "Feedback: [ ] worked well  [ ] changes needed  [ ] unfinished",
            style["body"],
        )
    )
    fields = [
        "Measured width: ____________________ mm",
        "Measured height: ____________________ mm",
        "Yarn and hook actually used: ____________________________________________",
        "Gauge measured: ______ sc / 100 mm; ______ rounds / 100 mm",
        "Pattern changes: _______________________________________________________",
        "Problem round / location: ______________________________________________",
        "Notes: __________________________________________________________________",
        "________________________________________________________________________",
    ]
    story.extend(Paragraph(_text(line, "report_field"), style["body"]) for line in fields)
    story.append(Spacer(1, 8 * mm))
    story.append(
        Paragraph(
            "Associate a photo or PDF of the finished work with project short ID "
            + expected_id[:12],
            style["body"],
        )
    )

    output = BytesIO()
    doc = BaseDocTemplate(
        output,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title="Crochet.AI Crochet Pattern",
        author="Crochet.AI local prototype",
        invariant=1,
    )
    frame = Frame(
        doc.leftMargin,
        doc.bottomMargin,
        doc.width,
        doc.height,
        id="main",
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )

    def footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#514A43"))
        canvas.drawString(20 * mm, 12 * mm, f"{expected_id[:12]} | NOT_VERIFIED / UNTESTED")
        canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="pattern", frames=frame, onPage=footer)])
    doc.build(story)
    return output.getvalue()
