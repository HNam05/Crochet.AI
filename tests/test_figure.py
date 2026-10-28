"""Figure parts, assembly math and independent CrochetIR validation of figure parts."""

from __future__ import annotations

from copy import deepcopy
from itertools import pairwise

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from crochet_ai.figure import FigureError, figure_text, parse_figure, solve_figure
from crochet_ai.figure_ir import compile_part_ir, part_artifacts, verify_figure
from crochet_ai.figure_parts import (
    SHAPE_ENDS,
    Gauge,
    PartError,
    consumed_and_produced,
    round_notation,
    shaping_tokens,
    solve_part,
)
from crochet_ai.figure_pdf import render_figure_pdf
from crochet_ai.figure_templates import TEMPLATES

GAUGE = Gauge(25, 28)
COMMIT = "a" * 40
COLORS = {"main": ("Braun", "#9C6B3F"), "accent": ("Beige", "#E7CFA8")}


def _replay(counts_tokens: list[tuple[int, tuple[str, ...]]]) -> None:
    for (before, _), (after, tokens) in pairwise(counts_tokens):
        assert consumed_and_produced(tokens) == (before, after)


@pytest.mark.parametrize(
    ("shape", "end"), [(shape, end) for shape, ends in SHAPE_ENDS.items() for end in ends]
)
def test_every_shape_and_end_produces_a_consistent_schedule(shape: str, end: str) -> None:
    schedule = solve_part(shape, 30, 30, end, GAUGE)
    rounds = schedule.rounds
    assert rounds[0].tokens == ("sc",) * rounds[0].count
    assert 4 <= rounds[0].count <= 8
    _replay([(r.count, r.tokens) for r in rounds])
    if end == "closed":
        assert rounds[-1].count <= 6
    assert schedule.max_residual_mm < 3 * GAUGE.stitch_pitch_mm


def test_sphere_follows_the_six_per_round_disc_rule_and_is_symmetric() -> None:
    counts = solve_part("sphere", 60, 60, "closed", GAUGE).counts
    assert counts[:2] == (6, 12)
    assert counts[-1] == 6
    peak = counts.index(max(counts))
    assert all(a <= b for a, b in pairwise(counts[: peak + 1]))
    assert abs(len(counts) - 2 * (peak + 1)) <= 4


def test_open_tube_keeps_constant_rounds_and_ends_at_its_width() -> None:
    schedule = solve_part("tube", 20, 40, "open", GAUGE)
    assert schedule.counts[-1] == schedule.counts[-2] == schedule.counts[-5]
    assert abs(schedule.counts[-1] * GAUGE.stitch_pitch_mm - 20 * 3.14159) < GAUGE.stitch_pitch_mm


def test_staggered_shaping_shifts_by_half_a_gap() -> None:
    assert shaping_tokens(12, 18, staggered=False) == ("sc", "inc") * 6
    assert shaping_tokens(18, 24, staggered=True) == ("sc", "inc", "sc") * 6
    assert round_notation(("sc", "inc", "sc") * 6) == "(1 fM, zun, 1 fM) x 6"
    assert round_notation(("sc", "sc", "inc") * 6, "en") == "(2 sc, inc) x 6"
    assert round_notation(("dec",) * 6) == "6 abn"


@settings(max_examples=60, deadline=None)
@given(before=st.integers(3, 120), delta=st.integers(-60, 120), stagger=st.booleans())
def test_shaping_tokens_always_balance(before: int, delta: int, stagger: bool) -> None:
    after = before + delta
    if not (before / 2 <= after <= 2 * before) or after < 1:
        return
    tokens = shaping_tokens(before, after, stagger)
    assert consumed_and_produced(tokens) == (before, after)


def test_invalid_end_and_oversized_parts_fail_closed() -> None:
    with pytest.raises(PartError):
        solve_part("sphere", 30, 30, "open", GAUGE)
    with pytest.raises(PartError):
        solve_part("tube", 300, 400, "open", Gauge(60, 60))


@pytest.mark.parametrize("name", sorted(TEMPLATES))
def test_templates_solve_and_render(name: str) -> None:
    result = solve_figure(TEMPLATES[name])
    assert result["verification_state"] == "NOT_VERIFIED"
    assert result["preview"]["points"]
    assert len(result["assembly"]) == sum(
        len(p["attach"]["angles"]) for p in TEMPLATES[name]["parts"] if "attach" in p
    )
    text = figure_text(result)
    assert "R1: MR, 6 fM (6)" in text or "R1: MR, 4 fM (4)" in text
    assert render_figure_pdf(result).startswith(b"%PDF")


def test_assembly_positions_are_symmetric_round_and_stitch_coordinates() -> None:
    result = solve_figure(TEMPLATES["teddy"])
    arms = [step for step in result["assembly"] if step["part"] == "arm"]
    assert len(arms) == 2 and arms[0]["round"] == arms[1]["round"]
    n = arms[0]["round_stitches"]
    # Mirror angles 80/280 map to mirrored stitch indices around the back marker.
    assert abs((arms[0]["stitch"] - 1) + (arms[1]["stitch"] - 1) - (n - 1)) <= 1
    eyes = result["features"][0]
    assert eyes["type"] == "eye" and len(eyes["stitches"]) == 2
    assert "Sicherheitsaugen" in eyes["text_de"]


def test_color_stripes_create_color_change_notes() -> None:
    result = solve_figure(TEMPLATES["teddy"])
    leg = next(p for p in result["parts"] if p["id"] == "leg")
    notes = [note for row in leg["rows"] for note in row["notes"]]
    assert any(note.startswith("Mit Beige beginnen") for note in notes)
    assert any(note.startswith("Farbwechsel zu Braun") for note in notes)


def test_spec_validation_is_strict_and_german() -> None:
    spec = deepcopy(TEMPLATES["teddy"])
    spec["parts"][1]["attach"]["to"] = "missing"
    with pytest.raises(FigureError) as error:
        parse_figure(spec)
    assert "vorher definiertes Teil" in error.value.message_de
    spec = deepcopy(TEMPLATES["teddy"])
    spec["parts"][0]["surprise"] = 1
    with pytest.raises(FigureError):
        parse_figure(spec)
    spec = deepcopy(TEMPLATES["teddy"])
    spec["parts"][2]["attach"]["to"] = "arm"
    spec["parts"].append(spec["parts"].pop(2))
    with pytest.raises(FigureError):
        parse_figure(spec)


@pytest.mark.parametrize(
    ("shape", "end", "stripes"),
    [
        ("sphere", "closed", ()),
        ("dome", "flat", ()),
        ("tube", "open", ((0.0, 0.2, "accent"),)),
        ("cylinder", "closed", ((0.3, 0.6, "accent"),)),
        ("cone", "open", ()),
    ],
)
def test_figure_parts_pass_the_independent_semantic_validator(
    shape: str, end: str, stripes: tuple[tuple[float, float, str], ...]
) -> None:
    schedule = solve_part(shape, 24, 24, end, GAUGE, color="main", stripes=stripes)
    design, material = part_artifacts(schedule, "part", COLORS, software_commit=COMMIT)
    ir = compile_part_ir(schedule, design, material, software_commit=COMMIT)
    operations = [o["operation_type"] for o in ir["construction_operations"]]
    assert operations[0] == "MAGIC_RING"
    assert operations[-1] == ("CLOSE" if end == "closed" else "DECLARE_OPENING")
    assert ("COLOR_CHANGE" in operations) == bool(stripes)
    # The IR is the printed pattern: stitch shaping order equals the round tokens.
    shaping = [s["shaping"] for s in ir["stitches"]]
    expected = [
        {"inc": "INCREASE", "dec": "DECREASE"}.get(t, "PLAIN")
        for r in schedule.rounds
        for t in r.tokens
    ]
    assert shaping == expected


def test_tampered_part_ir_is_rejected_by_the_validator() -> None:
    from crochet_ai.validation import SemanticValidator

    schedule = solve_part("sphere", 24, 24, "closed", GAUGE, color="main")
    design, material = part_artifacts(schedule, "part", COLORS, software_commit=COMMIT)
    ir = compile_part_ir(schedule, design, material, software_commit=COMMIT)
    validator = SemanticValidator(
        material_profiles={material["profile_id"]: material,
                           (material["profile_id"], material["revision"]): material},
        design_specs={design["design_spec_id"]: design},
    )
    increase = next(s for s in ir["stitches"] if s["shaping"] == "INCREASE")
    increase["top_attachment_location_ids"] = increase["top_attachment_location_ids"][:1]
    assert not validator.validate_crochet_ir(ir).ok


def test_verify_figure_reports_every_part() -> None:
    spec = deepcopy(TEMPLATES["chick"])
    records = verify_figure(spec, software_commit=COMMIT)
    assert [r["part"] for r in records] == [p["id"] for p in spec["parts"]]
    assert all(r["status"] == "PASS" for r in records)
