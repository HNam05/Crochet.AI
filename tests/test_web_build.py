"""The in-browser bridge (web/bridge.py) answers like the local server."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest

from crochet_ai.figure_api import figure_spec_call, templates_payload
from crochet_ai.figure_templates import template_catalog

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def bridge() -> dict:
    return runpy.run_path(str(ROOT / "web" / "bridge.py"))


def _call(bridge: dict, path: str, body: object = None) -> dict:
    return json.loads(bridge["handle"](path, "" if body is None else json.dumps(body), "test"))


def test_templates_never_offer_claude(bridge: dict) -> None:
    reply = _call(bridge, "/api/figure/templates")
    assert reply["ok"] and reply["data"]["claude_available"] is False
    assert reply["data"]["templates"] == templates_payload(allow_claude=False)["templates"]


def test_solve_matches_shared_api(bridge: dict) -> None:
    spec = template_catalog()[0]["spec"]
    reply = _call(bridge, "/api/figure/solve", {"spec": spec})
    kind, data = figure_spec_call("/api/figure/solve", {"spec": spec}, software_commit="test")
    assert reply == {"ok": True, "data": json.loads(json.dumps(data))} and kind == "json"


def test_pdf_and_text_are_binary(bridge: dict) -> None:
    spec = template_catalog()[0]["spec"]
    pdf = _call(bridge, "/api/figure/pdf", {"spec": spec})
    assert pdf == {"ok": True, "binary": True, "content_type": "application/pdf"}
    assert bridge["handle"].__globals__["LAST_BYTES"].startswith(b"%PDF")
    text = _call(bridge, "/api/figure/text", {"spec": spec})
    assert text["content_type"].startswith("text/plain")


def test_claude_and_bad_input_fail_closed(bridge: dict) -> None:
    claude = _call(bridge, "/api/figure/compose", {"text": "Hase", "use_claude": True})
    assert not claude["ok"] and claude["error"]["reason"] == "compose.claude"
    bad = _call(bridge, "/api/figure/solve", {"spec": {"parts": []}})
    assert not bad["ok"] and bad["error"]["code"] == "E_INPUT"
    extra = _call(bridge, "/api/figure/solve", {"spec": {}, "x": 1})
    assert not extra["ok"] and extra["error"]["reason"] == "figure.fields"
    assert not _call(bridge, "/api/unknown")["ok"]


def test_pdf_without_verification_omits_check_summary() -> None:
    spec = template_catalog()[0]["spec"]
    kind, fast = figure_spec_call(
        "/api/figure/pdf", {"spec": spec}, software_commit="test", verify_pdf=False
    )
    assert kind == "pdf" and fast.startswith(b"%PDF")
