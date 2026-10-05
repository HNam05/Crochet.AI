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

from crochet_ai.prototype_backend import LocalPrototype
from crochet_ai.prototype_pdf import (
    PrototypePdfError,
    _group_course_steps,
    _text,
    render_project_pdf,
)
from crochet_ai.prototype_server import make_server
from crochet_ai.prototype_storage import PrototypeStore


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
    assert "Rückmeldung nach dem Häkeln" in text
    assert "Gemessene Breite" in text and "Problemrunde" in text
    assert "gemeinsam abmaschen" in text
    assert "2 fM in dieselbe Einstichstelle" in text
    assert "loc_" not in text and "ev_" not in text
    assert "letzten Runden vor den Schließabnahmen" in text
    assert "ungefüllt" in text and "gefüllt" in text
    assert "hat geklappt" in text and "Änderungen nötig" in text and "nicht fertig" in text
    for course in project["courses"]:
        source_steps = [
            step for step in project["steps"] if step["course_id"] == course["course_id"]
        ]
        header = f"[ ] Runde {course['number']} · {course['total_stitches']} Maschen"
        first_step = source_steps[0]["event_index"] + 1
        assert any(
            header in page_text and re.search(rf"\[ \] Schritt {first_step}(?:-|:)", page_text)
            for page_text in page_texts
        ), "A course header must share a page with its first instruction"
        groups = _group_course_steps(source_steps)
        expanded = [event_id for group in groups for event_id in group["event_ids"]]
        assert expanded == course["step_ids"]
        assert sum(group["produced_total"] for group in groups) == course["total_stitches"]


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
