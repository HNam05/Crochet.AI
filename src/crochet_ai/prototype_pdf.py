"""Deterministic print export for a saved local prototype project."""

from __future__ import annotations

import re
from html import escape
from io import BytesIO
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
    KeepTogether,
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
from .prototype_shapes import shape_label
from .validation import SemanticValidator


class PrototypePdfError(ValueError):
    """Saved project cannot be safely represented in a printable document."""


def _group_course_steps(course_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compress contiguous repeated instructions without explicit base positions."""
    groups: list[dict[str, Any]] = []
    for step in course_steps:
        instruction = step["instruction_de"]
        has_position = re.search(r"\ban Einstichstelle \d", instruction) is not None
        can_join = (
            bool(groups)
            and not has_position
            and not groups[-1]["has_position"]
            and groups[-1]["instruction"] == instruction
            and groups[-1]["produced_each"] == step["produced_stitches"]
        )
        if can_join:
            groups[-1]["event_ids"].append(step["step_id"])
            groups[-1]["last_number"] = step["event_index"] + 1
            groups[-1]["produced_total"] += step["produced_stitches"]
        else:
            groups.append(
                {
                    "event_ids": [step["step_id"]],
                    "first_number": step["event_index"] + 1,
                    "last_number": step["event_index"] + 1,
                    "instruction": instruction,
                    "produced_each": step["produced_stitches"],
                    "produced_total": step["produced_stitches"],
                    "has_position": has_position,
                }
            )
    return groups


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
        "step": ParagraphStyle(
            "PdfStep",
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
    steps = {step["step_id"]: step for step in presentation["steps"]}
    events = {event["event_id"]: event for event in ir["construction_sequence"]}
    stitches = {stitch["stitch_id"]: stitch for stitch in ir["stitches"]}
    style = _styles()
    story: list[Any] = [Paragraph("Häkelanleitung", style["title"])]
    requested_shape = request.get("shape")
    if not isinstance(requested_shape, str):
        raise PrototypePdfError("pdf.project_invalid")
    try:
        shape = shape_label(requested_shape)
    except ValueError as error:
        raise PrototypePdfError("pdf.project_invalid") from error
    story.extend(
        [
            Paragraph(
                f"{shape}: max. Breite / Ø {request['diameter_mm']:g} mm x "
                f"Höhe {request['height_mm']:g} mm",
                style["heading"],
            ),
            Paragraph(
                f"Garn: {_text(request['yarn_label'], 'yarn')} &nbsp; "
                f"Farbe: {_text(request['color_hex'], 'color')} &nbsp; "
                f"Häkelnadel: {request['hook_diameter_mm']:g} mm",
                style["body"],
            ),
            Paragraph(
                f"Maschenprobe (Eingabe): {request['stitches_per_100mm']} fM x "
                f"{request['courses_per_100mm']} Runden je 100 mm. "
                f"Intervall-/Unsicherheitsannahme: +/-{request['uncertainty_percent']:g} %. "
                f"Effektive Teilung: {gauge['effective_stitch_pitch_mm']:.2f} mm je Masche "
                f"und {gauge['effective_course_pitch_mm']:.2f} mm je Runde.",
                style["body"],
            ),
            Paragraph(
                "Status: NOT_VERIFIED · UNTESTED. Die Maße und die Maschenprobe sind Eingaben; "
                "Form, Passform und physische Größe sind nicht bestätigt.",
                style["body"],
            ),
            Paragraph(
                "Abkürzungen: fM = feste Masche. Zunahme: 2 fM in dieselbe Einstichstelle "
                "(eine Basis, zwei Maschen oben). Abnahme: zwei Basen gemeinsam abmaschen "
                "(zwei Basen, eine Masche oben). Die Anweisungen folgen "
                "der Reihenfolge der Vorrunde.",
                style["body"],
            ),
            Paragraph(
                f"[ ] Schritt 1: Fadenring beginnen und die "
                f"{presentation['courses'][0]['total_stitches']} "
                "fM der ersten Runde wie unten angegeben in denselben Ring arbeiten. "
                "Jede Runde fortlaufend häkeln und nach Abschluss abhaken. "
                "Falls Füllung gewünscht ist: in den letzten Runden vor den "
                "Schließabnahmen füllen; ungefüllt ist ebenfalls möglich.",
                style["body"],
            ),
        ]
    )
    for course in courses:
        course_summary = presentation["courses"][course["ordinal"]]
        total_stitches = course_summary["total_stitches"]
        course_header = Table(
            [
                [
                    Paragraph(
                        f"[ ] Runde {course['ordinal'] + 1} · {total_stitches} Maschen",
                        style["heading"],
                    )
                ]
            ],
            colWidths=[170 * mm],
            style=TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#9B8B78")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
                    ("TOPPADDING", (0, 0), (-1, -1), 1 * mm),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1 * mm),
                ]
            ),
        )
        course_header.keepWithNext = 1
        course_block: list[Any] = [course_header]
        course_steps: list[dict[str, Any]] = []
        for event_id in course["member_event_ids"]:
            step = steps[event_id]
            event = events[event_id]
            instruction = step["instruction_de"]
            if event["subject_ref"]["entity_type"] == "STITCH":
                stitch = stitches[event["subject_ref"]["stitch_id"]]
                if stitch["shaping"] == "INCREASE":
                    instruction = instruction.replace(
                        "fM zweimal in dieselbe Einstichstelle",
                        "2 fM in dieselbe Einstichstelle",
                    )
            course_steps.append({**step, "instruction_de": instruction})
        for group in _group_course_steps(course_steps):
            number = str(group["first_number"])
            if len(group["event_ids"]) > 1:
                number = (
                    f"{group['first_number']}-{group['last_number']} ({len(group['event_ids'])}x)"
                )
            text = (
                f"[ ] Schritt {number}: {_text(group['instruction'], 'instruction')} "
                f"({group['produced_total']} Maschen neu)"
            )
            course_block.append(Paragraph(text, style["step"]))
        course_block.append(Spacer(1, 3 * mm))
        story.append(KeepTogether(course_block))
    close_steps = [step for step in presentation["steps"] if step["kind"] == "CLOSE"]
    if len(close_steps) != 1:
        raise PrototypePdfError("pdf.unsupported_ir")
    story.append(
        Paragraph(
            f"[ ] {close_steps[0]['event_index'] + 1}. Arbeit schließen",
            style["body"],
        )
    )
    story.extend(
        [
            PageBreak(),
            Paragraph("Rückmeldung nach dem Häkeln", style["title"]),
            Paragraph("Projekt-Kurz-ID: " + expected_id[:12], style["body"]),
            Paragraph("Vollständiger CrochetIR-SHA-256: " + expected_id, style["small"]),
            Paragraph(
                "Dieses Blatt dokumentiert Ihre Rückmeldung. "
                "Sie ändert keinen Prüfstatus automatisch.",
                style["body"],
            ),
        ]
    )
    story.append(
        Paragraph(
            "Ergebnis: [ ] ungefüllt  [ ] gefüllt &nbsp;&nbsp; "
            "Rückmeldung: [ ] hat geklappt  [ ] Änderungen nötig  [ ] nicht fertig",
            style["body"],
        )
    )
    fields = [
        "Gemessene Breite: ____________________ mm",
        "Gemessene Höhe: ____________________ mm",
        "Garn und Häkelnadel tatsächlich verwendet: ______________________________",
        "Maschenprobe tatsächlich gemessen: ______ fM / 100 mm; ______ Runden / 100 mm",
        "Änderungen an der Anleitung: _____________________________________________",
        "Problemrunde / Stelle: _________________________________________________",
        "Notizen: _______________________________________________________________",
        "________________________________________________________________________",
    ]
    story.extend(Paragraph(_text(line, "report_field"), style["body"]) for line in fields)
    story.append(Spacer(1, 8 * mm))
    story.append(
        Paragraph(
            "Foto oder PDF der fertigen Arbeit hier zuordnen: Projekt-Kurz-ID " + expected_id[:12],
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
        title="Crochet.AI Häkelanleitung",
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
        canvas.drawString(20 * mm, 12 * mm, f"{expected_id[:12]} · NOT_VERIFIED / UNTESTED")
        canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, f"Seite {document.page}")
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="pattern", frames=frame, onPage=footer)])
    doc.build(story)
    return output.getvalue()
