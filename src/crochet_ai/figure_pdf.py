"""Printable German PDF for a solved figure (parts, rounds, assembly, front sketch)."""

from __future__ import annotations

from html import escape
from io import BytesIO
from typing import Any

from reportlab.graphics.shapes import Circle, Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_INK = colors.HexColor("#2B2621")
_MUTED = colors.HexColor("#6E655B")
_ACCENT = colors.HexColor("#A4552F")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["BodyText"]
    return {
        "title": ParagraphStyle("t", parent=base, fontName="Helvetica-Bold", fontSize=20,
                                leading=24, textColor=_INK, spaceAfter=4),
        "h": ParagraphStyle("h", parent=base, fontName="Helvetica-Bold", fontSize=13,
                            leading=16, textColor=_ACCENT, spaceBefore=10, spaceAfter=4),
        "body": ParagraphStyle("b", parent=base, fontName="Helvetica", fontSize=9.5,
                               leading=12.5, textColor=_INK),
        "note": ParagraphStyle("n", parent=base, fontName="Helvetica-Oblique", fontSize=9,
                               leading=11.5, textColor=_MUTED),
        "small": ParagraphStyle("s", parent=base, fontName="Helvetica", fontSize=8,
                                leading=10, textColor=_MUTED),
    }


def _sketch(result: dict[str, Any], width: float, height: float) -> Drawing:
    """Front view of the schematic points, painter-sorted back to front."""
    points = result["preview"]["points"]
    palette = [colors.HexColor(c["hex"]) for c in result["colors"]]
    low, high = result["bounds_mm"]["min"], result["bounds_mm"]["max"]
    span_x = max(high[0] - low[0], 1.0)
    span_y = max(high[1] - low[1], 1.0)
    scale = min(width / span_x, height / span_y) * 0.92
    drawing = Drawing(width, height)
    cx = (low[0] + high[0]) / 2
    cy = (low[1] + high[1]) / 2
    for x, y, z, color_index, _part, _round, size in sorted(points, key=lambda p: p[2]):
        shade = 0.72 + 0.28 * (z - low[2]) / max(high[2] - low[2], 1.0)
        base = palette[int(color_index)]
        fill = colors.Color(base.red * shade, base.green * shade, base.blue * shade)
        drawing.add(
            Circle(width / 2 + (x - cx) * scale, height / 2 + (y - cy) * scale,
                   max(size * scale * 1.1, 0.8), fillColor=fill, strokeColor=None)
        )
    return drawing


def render_figure_pdf(
    result: dict[str, Any], checks: list[dict[str, Any]] | None = None
) -> bytes:
    style = _styles()
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
        bottomMargin=16 * mm, title=result["name"], author="Crochet.AI",
    )
    g = result["gauge"]
    color_names = {c["id"]: c["label"] for c in result["colors"]}
    story: list[Any] = [Paragraph(escape(result["name"]), style["title"])]
    story.append(
        Paragraph(
            "Status: NOT_VERIFIED / UNTESTED - mathematisch berechneter Vorschlag, noch nicht "
            "nachgehäkelt. Maße hängen von deiner Maschenprobe ab.",
            style["note"],
        )
    )
    story.append(Spacer(1, 4))
    facts = [
        f"<b>Maschenprobe:</b> {g['stitches_per_100mm']:g} fM x {g['rows_per_100mm']:g} Runden "
        f"= 10 cm &nbsp; <b>Nadel:</b> {g['hook_mm']:g} mm"
        + (f" &nbsp; <b>Garn:</b> {escape(g['yarn'])}" if g["yarn"] else ""),
        "<b>Farben:</b> " + ", ".join(escape(c["label"]) for c in result["colors"]),
        "<b>Abkürzungen:</b> MR = Magic Ring (Fadenring), fM = feste Masche, zun = 2 fM in "
        "eine Masche, abn = 2 Maschen zusammen abmaschen. In Spiralrunden häkeln, "
        "Rundenanfang markieren. Die Zahl in Klammern ist die Maschenzahl nach der Runde.",
        f"<b>Gesamt:</b> {result['total_stitches']} Maschen, Figur ca. "
        f"{result['bounds_mm']['max'][1] - result['bounds_mm']['min'][1]:.0f} mm hoch "
        "(Schemaschätzung).",
    ]
    text_column = [Paragraph(item, style["body"]) for item in facts]
    sketch = _sketch(result, 62 * mm, 72 * mm)
    header = Table([[text_column, sketch]], colWidths=[108 * mm, 66 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(header)

    if checks is not None:
        passed = sum(1 for check in checks if check["status"] == "PASS")
        story.append(Spacer(1, 4))
        story.append(
            Paragraph(
                f"<b>Strukturprüfung:</b> {passed} von {len(checks)} Teilen bestehen die "
                "unabhängige CrochetIR-Prüfung (jede Masche, Einstichstelle, Farbwechsel und "
                "Öffnung nachgerechnet). Form und Größe sind damit noch nicht bestätigt.",
                style["body"],
            )
        )
        for check in checks:
            if check["status"] != "PASS":
                story.append(Paragraph(
                    f"FEHLER in {escape(check['label'])}: {escape(str(check.get('reason')))}",
                    style["note"]))
    for part in result["parts"]:
        count = f" - {part['instances']}x" if part["instances"] > 1 else ""
        block: list[Any] = [
            Paragraph(f"{escape(part['label'])}{count} <font size=9 color='#6E655B'>"
                      f"({escape(color_names[part['color']])}, {part['round_count']} Runden)"
                      "</font>", style["h"])
        ]
        if part["note"]:
            block.append(Paragraph(escape(part["note"]), style["note"]))
        rows: list[list[Any]] = []
        for row in part["rows"]:
            for note in row["notes"]:
                rows.append(["", Paragraph(f"<i>{escape(note)}</i>", style["note"])])
            rows.append(["[ ]", Paragraph(escape(row["text_de"]), style["body"])])
        rows.append(["[ ]", Paragraph(escape(part["finish_de"]), style["body"])])
        table = Table(rows, colWidths=[9 * mm, 165 * mm])
        table.setStyle(TableStyle([
            ("FONT", (0, 0), (0, -1), "Helvetica", 9),
            ("TEXTCOLOR", (0, 0), (0, -1), _MUTED),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 1.2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ]))
        block.append(table)
        # Short parts stay on one page; long ones may split across pages.
        if len(rows) < 30:
            story.append(KeepTogether(block))
        else:
            story.extend(block)

    if result["features"] or result["assembly"]:
        story.append(Paragraph("Montage", style["h"]))
        story.append(
            Paragraph(
                "Positionen zählen ab dem Rundenanfang (Markierung = Rückseite des Teils) in "
                "Häkelrichtung, für Rechtshänder. Linkshänder tauschen links und rechts. "
                "Vor dem Annähen mit Nadeln feststecken und die Wirkung prüfen.",
                style["note"],
            )
        )
        steps = [step["text_de"] for step in result["features"]] + [
            step["text_de"] for step in result["assembly"]
        ]
        for number, text in enumerate(steps, 1):
            story.append(Paragraph(f"{number}. {escape(text)}", style["body"]))
            story.append(Spacer(1, 2))

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(_MUTED)
        canvas.drawString(18 * mm, 9 * mm,
                          f"Crochet.AI · {result['solver_version']} · NOT_VERIFIED / UNTESTED")
        canvas.drawRightString(A4[0] - 18 * mm, 9 * mm, f"Seite {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
