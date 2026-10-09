"""Focused checks for the offline saved-project PDF export."""

from __future__ import annotations

import http.client
import re
import subprocess
from io import BytesIO
from threading import Thread
from typing import Any

import pytest
from pypdf import PdfReader
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Table

from crochet_ai.analytic_compile import CompileProvenance, compile_closed_schedule
from crochet_ai.canonical import CanonicalProfile, canonical_hash
from crochet_ai.prototype_backend import LocalPrototype
from crochet_ai.prototype_pdf import (
    _ROUND_ROW_MIN_SPLIT_HEIGHT,
    PrototypePdfError,
    _course_notation,
    _round_notation,
    _text,
    render_project_pdf,
)
from crochet_ai.prototype_server import make_server
from crochet_ai.prototype_storage import PrototypeStore
from crochet_ai.validation import SemanticValidator


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    store = PrototypeStore(tmp_path_factory.mktemp("prototype-pdf"))
    try:
        return LocalPrototype(store, commit).generate(
            {
                "prototype_version": "1.0.0",
                "shape": "sphere",
                "diameter_mm": 40,
                "height_mm": 40,
                "stitches_per_100mm": 25,
                "courses_per_100mm": 28,
                "hook_diameter_mm": 3,
                "yarn_label": "Garn & <lange> " + "Wolle " * 14,
                "color_hex": "#B88757",
                "uncertainty_percent": 10,
            }
        )
    finally:
        store.close()


def test_pdf_contains_instructions_provenance_gauge_and_report_page(
    project: dict[str, Any],
) -> None:
    pdf = render_project_pdf(project, project["project_id"])
    assert pdf.startswith(b"%PDF-")
    reader = PdfReader(BytesIO(pdf))
    page_texts = [" ".join((page.extract_text() or "").split()) for page in reader.pages]
    text = " ".join(page_texts)
    assert "Garn & <lange> Wolle" in text
    assert text.count("Wolle") >= 14
    assert "0.04" in text or "4.00" in text
    assert "NOT_VERIFIED" in text and "UNTESTED" in text
    assert "Feedback After Crocheting" in text
    assert "Measured width" in text and "Problem round" in text
    assert "dec sc" in text
    assert "inc sc" in text
    assert "loc_" not in text and "ev_" not in text
    assert "final rounds before closing the opening" in text
    assert "unstuffed" in text and "stuffed" in text
    assert "worked well" in text and "changes needed" in text and "unfinished" in text
    assert all(term not in text for term in ("Runde ", "Schritt ", "Step ", "Maschen neu"))
    matches = re.findall(r"\[ \] R(\d+): (.*?) \((\d+) stitches\)", text)
    assert len(matches) == len(project["courses"])
    for (number, instruction, count), course in zip(matches, project["courses"], strict=True):
        assert int(number) == course["number"]
        assert int(count) == course["total_stitches"]
        assert instruction
    assert "[ ] R1: MR, 6 sc (6 stitches)" in text


def test_pdf_fails_closed_when_saved_source_identity_is_changed(
    project: dict[str, Any],
) -> None:
    modified = dict(project)
    modified["crochet_ir"] = dict(project["crochet_ir"])
    modified["crochet_ir"]["courses"] = list(project["crochet_ir"]["courses"])
    modified["crochet_ir"]["courses"][0] = dict(modified["crochet_ir"]["courses"][0])
    modified["crochet_ir"]["courses"][0]["ordinal"] += 1
    with pytest.raises(PrototypePdfError, match=r"pdf\.project_invalid"):
        render_project_pdf(modified, project["project_id"])


def test_pdf_rejects_text_outside_builtin_helvetica_encoding(project: dict[str, Any]) -> None:
    with pytest.raises(PrototypePdfError, match=r"pdf\.unsupported_unicode"):
        _text("Yarn 🧶", "yarn")


def test_compact_us_notation_keeps_final_round_totals() -> None:
    assert _round_notation(["1 sc"] * 6) == "6 sc"
    assert _round_notation(["inc sc"] * 6) == "6 inc sc"
    assert _round_notation(["1 sc", "inc sc"] * 6) == "(1 sc, inc sc) x 6"
    assert _round_notation(["1 sc"] * 6) + " (6 stitches)" == "6 sc (6 stitches)"
    assert _round_notation(["inc sc"] * 6) + " (12 stitches)" == "6 inc sc (12 stitches)"
    assert _round_notation(["1 sc", "inc sc"] * 6) + " (18 stitches)" == (
        "(1 sc, inc sc) x 6 (18 stitches)"
    )


def test_round_row_split_defers_padding_fragment_but_splits_long_instructions() -> None:
    style = ParagraphStyle("RoundSplitTest", fontName="Helvetica", fontSize=9.5, leading=12)

    def make_row(text: str) -> Table:
        return Table(
            [[Paragraph(text, style)]],
            colWidths=[170 * mm],
            splitInRow=_ROUND_ROW_MIN_SPLIT_HEIGHT,
            style=[
                ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
            ],
        )

    ordinary = make_row("[ ] R17: 6 sc (6 stitches)")
    assert ordinary.split(170 * mm, 4 * mm) == []

    long_instruction = " ".join(f"instruction{i}" for i in range(500))
    fragments = make_row(long_instruction).split(170 * mm, 50 * mm)
    assert len(fragments) == 2
    document = BytesIO()
    SimpleDocTemplate(document).build(fragments)
    pages = PdfReader(document).pages
    page_texts = [page.extract_text() or "" for page in pages]
    assert all(text.strip() for text in page_texts)
    assert re.findall(r"instruction\d+", " ".join(page_texts)) == [
        f"instruction{i}" for i in range(500)
    ]


def test_compact_notation_preserves_uneven_tail_and_event_order() -> None:
    assert _round_notation(["1 sc", "inc sc"] * 3 + ["1 sc"]) == ("(1 sc, inc sc) x 3, 1 sc")
    assert _round_notation(["inc sc at prior-round stitch 3", "1 sc"]) == (
        "inc sc at prior-round stitch 3, 1 sc"
    )


def _scheduled_project(
    project: dict[str, Any], counts: tuple[int, ...], phases: tuple[int, ...]
) -> dict[str, Any]:
    ir = compile_closed_schedule(
        project["design_spec"],
        project["material_profile"],
        counts,
        phases,
        CompileProvenance("a" * 40, "b" * 64, (("test_profile", "pdf"),)),
        max_stitches=2000,
    )
    validator = SemanticValidator(
        material_profiles={project["material_profile"]["profile_id"]: project["material_profile"]},
        design_specs={project["design_spec"]["design_spec_id"]: project["design_spec"]},
    )
    digest = canonical_hash(ir, CanonicalProfile.CROCHET_IR, validator=validator)
    return {
        **project,
        "crochet_ir": ir,
        "project_id": digest,
        "source_crochet_ir_sha256": digest,
    }


def test_pdf_exact_sample_rounds_and_decrease_totals(project: dict[str, Any]) -> None:
    scheduled = _scheduled_project(project, (6, 12, 18, 12, 6, 3), (0, 0, 0, 0, 0))
    pdf = render_project_pdf(scheduled, scheduled["project_id"])
    text = " ".join(
        " ".join((p.extract_text() or "").split()) for p in PdfReader(BytesIO(pdf)).pages
    )
    expected = [
        "R1: MR, 6 sc (6 stitches)",
        "R2: 6 inc sc (12 stitches)",
        "R3: (1 sc, inc sc) x 6 (18 stitches)",
        "R4: (1 sc, dec sc) x 6 (12 stitches)",
        "R5: 6 dec sc (6 stitches)",
        "R6: 3 dec sc (3 stitches)",
    ]
    for instruction in expected:
        assert instruction in text
    assert re.findall(r"\((\d+) stitches\)", text) == ["6", "12", "18", "12", "6", "3"]


def test_canonical_positions_survive_rotated_rounds(project: dict[str, Any]) -> None:
    scheduled = _scheduled_project(project, (6, 12, 6), (2, 11))
    ir = scheduled["crochet_ir"]
    courses = sorted(ir["courses"], key=lambda course: course["ordinal"])
    notation, count = _course_notation(courses[1], ir)
    assert count == 12
    assert notation == ", ".join(f"inc sc at prior-round stitch {i}" for i in (3, 4, 5, 6, 1, 2))
    notation, count = _course_notation(courses[2], ir)
    assert count == 6
    assert notation == ", ".join(
        f"dec sc at prior-round stitch {a} & {b}"
        for a, b in ((12, 1), (2, 3), (4, 5), (6, 7), (8, 9), (10, 11))
    )
    text = " ".join(
        (page.extract_text() or "")
        for page in PdfReader(BytesIO(render_project_pdf(scheduled, scheduled["project_id"]))).pages
    )
    assert "12 & 1" in text and "3" in text


@pytest.mark.parametrize(
    "instructions,expected",
    [
        (["1 sc", "1 sc", "inc sc"] * 6, "(2 sc, inc sc) x 6"),
        (["dec sc"] * 4, "4 dec sc"),
        (["1 sc"] * 3 + ["inc sc", "1 sc"], "3 sc, inc sc, 1 sc"),
        (["inc sc", "1 sc", "dec sc"], "inc sc, 1 sc, dec sc"),
    ],
)
def test_notation_compacts_runs_without_reordering(instructions: list[str], expected: str) -> None:
    assert _round_notation(instructions) == expected


def test_pdf_rejects_stale_request_metadata(project: dict[str, Any]) -> None:
    modified = dict(project)
    modified["request"] = dict(project["request"])
    modified["request"]["diameter_mm"] = 42
    with pytest.raises(PrototypePdfError, match=r"pdf\.project_invalid"):
        render_project_pdf(modified, project["project_id"])


def test_pdf_ignores_saved_prose_and_progress(project: dict[str, Any]) -> None:
    baseline = render_project_pdf(project, project["project_id"])
    modified = dict(project)
    modified["pattern_text"] = "user prose must never be rendered"
    modified["session"] = {"project_id": project["project_id"], "revision": 9, "cursor": 99}
    assert render_project_pdf(modified, project["project_id"]) == baseline


def test_saved_project_route_returns_attachment_and_preserves_host_checks(
    project: dict[str, Any], tmp_path: Any
) -> None:
    server = make_server(0, tmp_path, "test-commit")
    server.prototype_store.save_project(project, "2026-10-05T00:00:00Z")
    thread = Thread(target=server.serve_forever)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
    try:
        connection.request("GET", f"/api/projects/{project['project_id']}/pattern.pdf")
        response = connection.getresponse()
        payload = response.read()
        assert response.status == 200
        assert response.getheader("Content-Type") == "application/pdf"
        assert response.getheader("Content-Disposition", "").startswith("attachment;")
        assert payload.startswith(b"%PDF-")
        connection.request(
            "GET",
            f"/api/projects/{project['project_id']}/pattern.pdf",
            headers={"Host": "example.com"},
        )
        rejected = connection.getresponse()
        assert rejected.status == 403
        assert b"request.host" in rejected.read()
        connection.request("GET", "/api/projects/" + "0" * 64 + "/pattern.pdf")
        missing = connection.getresponse()
        assert missing.status == 404
        assert b"project.not_found" in missing.read()
    finally:
        connection.close()
        server.shutdown()
        thread.join(timeout=5)
        server.prototype_store.close()
