"""M1A tests: controlled visible text, not a hidden CrochetIR serialization."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

import pytest
from conftest import make_closed_ir, make_increase_ir, resolved_artifacts, resolved_validator

from crochet_ai.equivalence import semantic_bytes
from crochet_ai.pattern import (
    PatternFormatError,
    TerminologyProfile,
    export_pattern,
    parse_pattern,
    parse_pattern_text,
    verify_semantic_round_trip,
)
from crochet_ai.pattern_context import PatternParseContext, PatternYarnBinding

VALIDATOR = resolved_validator()


def _context() -> PatternParseContext:
    design, material = resolved_artifacts()
    return PatternParseContext(
        design, (PatternYarnBinding("Yarn A", material, "Natural", "#C8B08A"),)
    )


def _text(stitch: str = "Work 1 sc. (1)", *, cyclic: bool = True) -> str:
    heading = "Round 1 (cyclic, anchor Marker A):" if cyclic else "Row 1 (linear):"
    start = (
        "Make a magic ring with Yarn A; set Marker A." if cyclic else "Start Yarn A at Marker A."
    )
    return "\n".join(
        (
            "CROCHET PATTERN V1",
            "Terminology: US",
            "",
            "Materials",
            "Yarn A: external material binding.",
            "",
            "Instructions",
            start,
            heading,
            stitch,
            "Close work.",
            "",
            "END",
            "",
        )
    )


@pytest.mark.parametrize("source", (make_closed_ir, make_increase_ir))
@pytest.mark.parametrize("profile", tuple(TerminologyProfile))
def test_magic_ring_sc_and_increase_round_trip(
    source: Callable[[], dict[str, Any]], profile: TerminologyProfile
) -> None:
    value = source()
    text = export_pattern(value, profile, validator=VALIDATOR)
    rebound = parse_pattern(text, context=_context())
    assert semantic_bytes(value, validator=VALIDATOR) == semantic_bytes(
        rebound, validator=VALIDATOR
    )
    assert verify_semantic_round_trip(value, profile, context=_context(), validator=VALIDATOR).ok


def test_foundation_chain_and_linear_row_build_valid_ir() -> None:
    text = _text("Work 1 ch. (1)", cyclic=False)
    value = parse_pattern(text, context=_context())
    assert value["courses"][0]["course_form"] == "LINEAR"
    assert value["stitches"][0]["stitch_type"] == "CHAIN"


def test_decrease_round_builds_binary_sc() -> None:
    text = _text("Work 1 sc increase. (2)")
    text = text.replace(
        "Work 1 sc increase. (2)\nClose", "Work 1 sc increase. (2)\nWork 1 sc decrease. (1)\nClose"
    )
    value = parse_pattern(text, context=_context())
    assert [item["shaping"] for item in value["stitches"]] == ["INCREASE", "DECREASE"]


@pytest.mark.parametrize(
    ("profile", "word"),
    (
        (TerminologyProfile.US_EN, "sc"),
        (TerminologyProfile.UK_EN, "dc"),
        (TerminologyProfile.DE_DE, "fM"),
    ),
)
def test_terminology_profiles_map_to_identical_semantics(
    profile: TerminologyProfile, word: str
) -> None:
    text = (
        _text()
        .replace("Terminology: US", f"Terminology: {profile.value[:2]}")
        .replace("Work 1 sc.", f"Work 1 {word}.")
    )
    result = parse_pattern(text, context=_context())
    assert result["stitches"][0]["stitch_type"] == "SINGLE_CROCHET"


@pytest.mark.parametrize(
    "mutate",
    (
        lambda text: text.replace("(1)", "(2)"),
        lambda text: text.replace(", anchor Marker A", ""),
        lambda text: text.replace("Work 1 sc.", "Work 2 sc."),
        lambda text: text.replace("Work 1 sc.", "Work 1 hdc."),
    ),
)
def test_corrupted_visible_structure_fails_closed(mutate: Callable[[str], str]) -> None:
    with pytest.raises(PatternFormatError):
        parse_pattern(mutate(_text()), context=_context())


def test_context_cannot_compensate_for_missing_structure() -> None:
    text = _text().replace("Work 1 sc. (1)\n", "")
    with pytest.raises(PatternFormatError):
        parse_pattern(text, context=_context())


def test_no_hidden_ir_channel_or_json_ledger() -> None:
    text = export_pattern(make_closed_ir(), TerminologyProfile.US_EN, validator=VALIDATOR)
    assert all(
        token not in text for token in ("BASE64", "crochet_ir_id", '{"', "sha256", "STITCHES:")
    )
    assert parse_pattern_text(text) == parse_pattern_text(text)


def test_parse_context_external_identity_is_not_construction() -> None:
    context = _context()
    assert set(context.__dataclass_fields__) == {"design_spec", "yarn_bindings"}
    malformed = PatternParseContext(deepcopy(context.design_spec), ())
    with pytest.raises(PatternFormatError):
        parse_pattern(_text(), context=malformed)
