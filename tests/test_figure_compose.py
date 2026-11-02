"""Knitting, flat projects, gauge calibration and text-to-figure composition."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from crochet_ai.figure import FigureError, calibrate_gauge, figure_text, solve_figure
from crochet_ai.figure_compose import SUBJECTS, compose, compose_offline, compose_with_claude
from crochet_ai.figure_ir import verify_figure
from crochet_ai.figure_parts import Gauge, consumed_and_produced, round_line, solve_part
from crochet_ai.figure_pdf import render_figure_pdf
from crochet_ai.figure_templates import TEMPLATES

COMMIT = "b" * 40


def test_knit_notation_uses_knitting_terms() -> None:
    schedule = solve_part("sphere", 40, 40, "closed", Gauge(22, 30))
    lines_de = [round_line(r, "de", "knit") for r in schedule.rounds]
    lines_en = [round_line(r, "en", "knit") for r in schedule.rounds]
    assert lines_de[0].startswith("R1: Magic Ring, 6 M aufnehmen")
    assert any("zun" in line for line in lines_de)
    assert any("2 re zus" in line for line in lines_de)
    assert any("kfb" in line for line in lines_en) and any("k2tog" in line for line in lines_en)
    assert not any("fM" in line for line in lines_de)


def test_knit_figure_finishes_and_skips_crochet_ir() -> None:
    spec = TEMPLATES["beanie_knit"]
    result = solve_figure(spec)
    assert result["technique"] == "knit"
    assert "abketten" in result["parts"][0]["finish_de"]
    assert "Abkürzungen: re = rechte Masche" in figure_text(result)
    records = verify_figure(spec, software_commit=COMMIT)
    assert [r["status"] for r in records] == ["NOT_APPLICABLE"]


def test_rectangle_rows_and_disc_rounds() -> None:
    rect = solve_part("rectangle", 200, 300, "open", Gauge(25, 28))
    assert rect.construction == "rows"
    assert len(set(rect.counts)) == 1 and rect.counts[0] == 50
    assert round_line(rect.rounds[0], "de", "crochet", "rows").startswith(
        "R1: 51 Lm anschlagen"
    )
    assert round_line(rect.rounds[1], "en", "knit", "rows").startswith("Row 2: knit across")
    disc = solve_part("disc", 100, 1, "open", Gauge(25, 28))
    assert disc.counts[:2] == (6, 12)
    for before, after in zip(disc.rounds, disc.rounds[1:], strict=False):
        assert consumed_and_produced(after.tokens) == (before.count, after.count)


@pytest.mark.parametrize("name", ["scarf", "blanket", "coaster"])
def test_flat_templates_render(name: str) -> None:
    result = solve_figure(TEMPLATES[name])
    assert result["preview"]["points"]
    assert render_figure_pdf(result).startswith(b"%PDF")
    rows = result["parts"][0]["rows"]
    assert sum(row["to"] - row["from"] + 1 for row in rows) == result["parts"][0]["round_count"]


def test_flat_parts_cannot_be_attached() -> None:
    spec = {
        "name": "x", "gauge": {"stitches_per_100mm": 25, "rows_per_100mm": 28},
        "colors": [{"id": "a", "label": "A", "hex": "#123456"}],
        "parts": [
            {"id": "body", "label": "K", "shape": "sphere", "width_mm": 40, "height_mm": 40,
             "color": "a"},
            {"id": "flag", "label": "F", "shape": "rectangle", "width_mm": 40,
             "height_mm": 40, "color": "a", "attach": {"to": "body", "at": 0.5, "angles": [0]}},
        ],
    }
    with pytest.raises(FigureError):
        solve_figure(spec)


def test_calibration_scales_gauge_by_measurement() -> None:
    gauge = {"stitches_per_100mm": 25.0, "rows_per_100mm": 28.0}
    wider = calibrate_gauge(gauge, planned_width_mm=20, planned_height_mm=40,
                            measured_mm=25, measure_mode="diameter", measured_height_mm=44)
    assert wider["stitches_per_100mm"] == 20.0
    assert wider["rows_per_100mm"] == 25.5
    flat = calibrate_gauge(gauge, planned_width_mm=20, planned_height_mm=40,
                           measured_mm=31.4159, measure_mode="flat_width",
                           measured_height_mm=None)
    assert flat["stitches_per_100mm"] == 25.0 and flat["rows_per_100mm"] == 28.0
    with pytest.raises(FigureError):
        calibrate_gauge(gauge, planned_width_mm=20, planned_height_mm=40, measured_mm=20,
                        measure_mode="volume", measured_height_mm=None)


@pytest.mark.parametrize(
    ("text", "subject"),
    [
        ("Ein kleiner grauer Hase", "Hase"),
        ("Fuchs, 15 cm", "Fuchs"),
        ("rosa Katze", "Katze"),
        ("Maus", "Maus"),
        ("Schweinchen", "Schwein"),
        ("grüner Frosch", "Frosch"),
        ("Schneemann", "Schneemann"),
        ("Fliegenpilz", "Pilz"),
        ("gestrickter Teddy", "Teddy"),
        ("Mütze Kopfumfang 54 cm", "Mütze"),
        ("Schal 180 cm", "Schal"),
        ("Babydecke 80 x 90 cm", "Babydecke"),
        ("Untersetzer 12 cm", "Untersetzer"),
    ],
)
def test_offline_composer_produces_solvable_specs(text: str, subject: str) -> None:
    proposal = compose_offline(text)
    assert proposal["source"] == "offline"
    assert subject in proposal["spec"]["name"]
    result = solve_figure(proposal["spec"])
    assert result["total_stitches"] > 0


def test_offline_composer_applies_size_color_and_technique() -> None:
    fox = solve_figure(compose_offline("Fuchs 20 cm")["spec"])
    height = fox["bounds_mm"]["max"][1] - fox["bounds_mm"]["min"][1]
    assert 170 <= height <= 230
    cat = compose_offline("eine blaue Katze")["spec"]
    assert cat["colors"][0]["hex"] == "#3C6EB4"
    assert compose_offline("gestrickter Bär")["spec"]["technique"] == "knit"
    hat = compose_offline("Mütze Kopfumfang 54 cm")["spec"]
    assert hat["parts"][0]["circumference_mm"] == pytest.approx(540 * 0.93, abs=0.1)
    blanket = compose_offline("Decke 70 x 90 cm")["spec"]["parts"][0]
    assert (blanket["width_mm"], blanket["height_mm"]) == (700, 900)


def test_unknown_subject_falls_back_with_explanation() -> None:
    proposal = compose_offline("ein Drache mit Flügeln")
    assert proposal["spec"]["parts"][0]["shape"] == "sphere"
    assert "Kein bekanntes Motiv" in proposal["notes_de"][0]


def test_every_builder_is_valid() -> None:
    for _keywords, builder, _label in SUBJECTS:
        solve_figure(builder())


def test_composer_rejects_empty_text_and_unavailable_claude(monkeypatch: Any) -> None:
    with pytest.raises(FigureError):
        compose_offline("   ")
    monkeypatch.setattr("crochet_ai.figure_compose.claude_available", lambda: False)
    with pytest.raises(FigureError) as error:
        compose("Fuchs", use_claude=True)
    assert error.value.code == "compose.unavailable"


class _FakeMessages:
    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        text = self.replies[len(self.calls) - 1]
        return SimpleNamespace(
            stop_reason="end_turn", model=kwargs["model"],
            content=[SimpleNamespace(type="text", text=text)],
        )


def _fake_client(replies: list[str]) -> Any:
    messages = _FakeMessages(replies)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


def test_claude_reply_is_validated_and_repaired_once() -> None:
    import json

    good = json.dumps(TEMPLATES["chick"])
    client, messages = _fake_client(['{"name": "x"}', f"Here you go: {good}"])
    proposal = compose_with_claude("ein Küken", client=client)
    assert proposal["source"] == "claude"
    assert proposal["spec"]["name"] == "Küken"
    assert len(messages.calls) == 2
    first = messages.calls[0]
    assert first["model"] == "claude-opus-5-5"
    assert first["fallbacks"] == "default"
    assert "thinking" not in first and "temperature" not in first
    # The repair turn appends the rejected reply and the validation error.
    assert messages.calls[1]["messages"][-1]["role"] == "user"


def test_claude_invalid_twice_fails_closed() -> None:
    client, _ = _fake_client(["no json", "still none"])
    with pytest.raises(FigureError) as error:
        compose_with_claude("Fuchs", client=client)
    assert error.value.code == "compose.invalid"
