"""Printable measurement sheets; they are not compiled crochet instructions."""

from __future__ import annotations

from html import escape
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .calibration_campaign import PROTOCOL_ID, CalibrationCampaign


class CalibrationPdfError(ValueError):
    pass


def _text(value: object) -> str:
    text = str(value)
    try:
        text.encode("cp1252", errors="strict")
    except UnicodeEncodeError as error:
        raise CalibrationPdfError("packet.unsupported_unicode") from error
    return escape(text)


def render_calibration_packet(campaign: CalibrationCampaign | None = None) -> bytes:
    """Produce blank pilot sheets or sheets bound to a frozen campaign."""
    stream = BytesIO()
    document = SimpleDocTemplate(
        stream,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        invariant=1,
        title="Crochet.AI - Kalibrierschlauch-Messprotokoll",
        author="Crochet.AI",
    )
    styles = getSampleStyleSheet()
    for name in ("Normal", "BodyText"):
        styles[name].fontName = "Helvetica"
        styles[name].fontSize = 10
        styles[name].leading = 14
    story: list[Any] = []

    def paragraph(text: str, style: str = "BodyText") -> None:
        story.append(Paragraph(text, styles[style]))
        story.append(Spacer(1, 2 * mm))

    def table(rows: list[list[str]], widths: list[float], *, row_height: float = 9 * mm) -> None:
        cells = [[Paragraph(_text(cell), styles["BodyText"]) for cell in row] for row in rows]
        item = Table(cells, colWidths=widths, minRowHeights=[row_height] * len(rows), repeatRows=1)
        item.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#8B8177")),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EBE6DE")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(item)
        story.append(Spacer(1, 3 * mm))

    paragraph("Kalibrierschlauch: Messprotokoll", "Title")
    paragraph("Status: NOT_VERIFIED / UNTESTED. Pilotprotokoll, keine physische Freigabe.")
    paragraph(
        "Dieses Paket enthält Messblätter. Die verbindliche Häkelanleitung gehört separat dazu. "
        "Der Generator für einen offenen Kalibrierschlauch ist noch nicht implementiert. "
        "Ein geschlossener Zylinder aus dem Prototyp ersetzt diesen Messkörper nicht."
    )
    paragraph("Vor dem Häkeln festlegen", "Heading2")
    paragraph(
        "Mindestens drei unabhängig gehäkelte Schläuche aus demselben Garn, Garnlos und mit "
        "derselben Nadel und Person verwenden. Im Messbereich nur feste Maschen, konstante "
        "Maschenzahl, keine Zu- oder Abnahmen. Ungefüllt, ungewaschen und ungeblockt messen."
    )
    paragraph(
        "Start- und Endbereiche vorab ausschließen. Mindestens zwei innere Runden für den "
        "Umfang und zwei Orientierungen (0 und 90 Grad) festlegen. Jede Messung mindestens "
        "zweimal aufnehmen. Die Längsmessung erfolgt zwischen markierten Rundenmitten: "
        "k Abstände bedeuten k+1 Rundenmitten. Rohwerte in Millimetern unverändert eintragen."
    )
    paragraph(
        "Den Umfang mit einem flexiblen Maßband direkt um den entspannten Schlauch messen, "
        "ohne Zug. Keine verdoppelte flache Breite verwenden. Vorab festgelegte Referenz "
        "für den Profilentwurf: niedrigste Messrunde, Orientierung 0 Grad, Wiederholung 1; "
        "für die Längsspanne ebenfalls Wiederholung 1. Andere Messungen bleiben separat "
        "zur Beurteilung von Streuung und Messfehlern erhalten."
    )
    context = campaign.to_dict() if campaign is not None else None
    if context is not None:
        scope = context["scope"]
        paragraph(f"Kampagne: {_text(context['campaign_id'])}; Protokoll: {_text(PROTOCOL_ID)}")
        paragraph(f"Kampagnenhash: {_text(campaign.sha256 if campaign else '')}")
        paragraph(
            f"Garn: {_text(scope['yarn_description'])}; Los: {_text(scope['yarn_lot'])}; "
            f"Nadel: {scope['hook_diameter_mm']:g} mm; Person: {_text(scope['tension_profile_id'])}"
        )
        paragraph("Anleitungsbindungen", "Heading2")
        for key, label in (
            ("design_spec_sha256", "DesignSpec"),
            ("crochet_ir_sha256", "CrochetIR"),
            ("instructions_sha256", "Häkelanleitung"),
        ):
            digest = context["artifact_bindings"][key]
            description = digest if digest is not None else "FEHLT - vor Fertigung binden"
            paragraph(f"{label}: {_text(description)}")
    else:
        table(
            [
                ["Vorab festzulegen", "Eintrag"],
                ["Kampagne / Proben-IDs / Person", ""],
                ["Garn / Garnlos / Nadel in mm", ""],
                ["Maschen je Runde / Anzahl Runden", ""],
                ["Start-/Endausschluss / Messrunden", ""],
                ["Längsspanne: Startrunde / Anzahl Abstände", ""],
                ["Messgerät / Auflösung in mm / Prüfnachweis", ""],
                ["Genaue Anleitung / Version / Datum", ""],
            ],
            [83 * mm, 91 * mm],
        )
    paragraph(
        "Die drei Proben dienen nur zur Kalibrierung. Separate Kugel- und Hourglass-Proben "
        "für spätere Prüfung schon vorher als Holdout markieren; ihre Daten nicht zum "
        "Anpassen derselben Profilversion verwenden. Abweichungen und Fehler behalten."
    )
    assignments = (
        [item for item in context["specimens"] if item["role"] == "CALIBRATION"]
        if context is not None
        else [{"specimen_id": f"Probe {index}"} for index in range(1, 4)]
    )
    for assignment in assignments:
        story.append(PageBreak())
        sid = assignment["specimen_id"]
        paragraph(f"Messblatt: {_text(sid)}", "Title")
        paragraph("Rolle: CALIBRATION. Eine eigene, unabhängig gehäkelte Probe.")
        paragraph("Datum / Uhrzeit: __________________  Ruhezeit in Stunden: __________")
        paragraph(
            "Probenmasse in g: __________  Füllung: 0 g  Behandlung: ungewaschen / ungeblockt"
        )
        if context is not None:
            plan = context["plan"]
            paragraph(
                f"{plan['stitches_per_course']} Maschen je Runde; {plan['total_courses']} Runden. "
                f"Ausgeschlossen: {plan['exclude_start_courses']} Startrunden und "
                f"{plan['exclude_end_courses']} Endrunden."
            )
            bands = plan["circumference_courses"]
            repeats = plan["repeats"]
            rows = [["Runde", "Orientierung", "Wiederholung", "Umfang in mm"]]
            rows.extend(
                [
                    [str(band), f"{orientation} Grad", str(repeat), ""]
                    for band in bands
                    for orientation in (0, 90)
                    for repeat in range(1, repeats + 1)
                ]
            )
            table(rows, [27 * mm, 40 * mm, 37 * mm, 70 * mm], row_height=7 * mm)
            span_label = (
                f"Von Rundenmitte {plan['course_span_start']} bis "
                f"{plan['course_span_start'] + plan['course_span_intervals']}; "
                f"{plan['course_span_intervals']} Abstände."
            )
        else:
            repeats = 2
            rows = [["Runde", "Orientierung", "Wiederholung", "Umfang in mm"]]
            rows.extend(
                [
                    ["________", f"{orientation} Grad", str(repeat), ""]
                    for _ in range(2)
                    for orientation in (0, 90)
                    for repeat in range(1, repeats + 1)
                ]
            )
            table(rows, [27 * mm, 40 * mm, 37 * mm, 70 * mm])
            span_label = "Von Rundenmitte ______ bis ______; Anzahl Abstände ______."
        paragraph("Längsspanne zwischen Rundenmitten", "Heading2")
        paragraph(span_label)
        table(
            [["Wiederholung", "Länge in mm"]] + [[str(i), ""] for i in range(1, repeats + 1)],
            [60 * mm, 114 * mm],
        )
        paragraph("Abweichungen / Ovalisierung / Curling / Geräteprüfung", "Heading2")
        paragraph("________________________________________________________________________")
        paragraph("________________________________________________________________________")
        paragraph(
            "Fotos mit Maßstab: Ansichten / Dateinamen / Einwilligung und Nutzungsrecht: __________"
        )
        paragraph(
            "Fehlende Messungen ausdrücklich als nicht gemessen kennzeichnen. "
            "Keine Nullwerte erfinden."
        )
    document.build(story)
    return stream.getvalue()
