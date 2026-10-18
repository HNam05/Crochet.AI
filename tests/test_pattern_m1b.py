from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest
from conftest import (
    make_closed_ir,
    make_reattach_ir,
    make_reserve_ir,
    make_split_join_ir,
    resolved_artifacts,
    resolved_validator,
)

from crochet_ai.equivalence import semantic_bytes
from crochet_ai.pattern import PatternFormatError, TerminologyProfile
from crochet_ai.pattern_context import PatternParseContext, PatternYarnBinding
from crochet_ai.pattern_m1b import (
    bind_pattern_m1b_semantics,
    export_pattern_m1b,
    parse_pattern_m1b,
    parse_pattern_m1b_text,
)


def context():
    design, material = resolved_artifacts()
    return PatternParseContext(
        design, (PatternYarnBinding("Yarn A", material, "Natural", "#C8B08A"),)
    )


@pytest.mark.parametrize(
    "factory", [make_closed_ir, make_reserve_ir, make_split_join_ir, make_reattach_ir]
)
@pytest.mark.parametrize("profile", list(TerminologyProfile))
def test_independent_topology_fixtures_round_trip(factory, profile):
    source = factory()
    validator = resolved_validator()
    text = export_pattern_m1b(source, profile, validator=validator)
    assert text.startswith("CROCHET PATTERN M1B V1\n")
    assert "sha256" not in text.lower() and "base64" not in text.lower()
    assert source["crochet_ir_id"] not in text
    parsed = parse_pattern_m1b(text, context=context())
    assert validator.validate_crochet_ir(parsed).ok
    assert semantic_bytes(parsed, validator=validator) == semantic_bytes(
        source, validator=validator
    )
    permuted = deepcopy(source)
    for table in permuted.values():
        if isinstance(table, list) and table and isinstance(table[0], dict):
            table.reverse()
    assert export_pattern_m1b(permuted, profile, validator=validator) == text


def test_reservation_cannot_be_lost_or_repaired_by_context():
    text = export_pattern_m1b(
        make_reserve_ir(), TerminologyProfile.US_EN, validator=resolved_validator()
    )
    lines = text.splitlines(keepends=True)
    removed = "".join(line for line in lines if ": Reserve;" not in line)
    with pytest.raises(PatternFormatError):
        parse_pattern_m1b(removed, context=context())
    with pytest.raises(PatternFormatError):
        parse_pattern_m1b_text(text.replace("as reserved", "as active"))


@pytest.mark.parametrize(
    "text", ["x" * 200001, "\n" * 8193, "\ud800"], ids=["bytes", "lines", "unicode"]
)
def test_text_limits_and_invalid_unicode_fail_before_replay(text):
    with pytest.raises(PatternFormatError):
        parse_pattern_m1b_text(text)


@pytest.mark.parametrize(
    "field,value",
    [
        ("terminology", "US_EN"),
        ("core", []),
        ("capabilities", ["CORE_STITCHES_V1"]),
        ("instructions", (None,)),
    ],
)
def test_untrusted_direct_ast_fields_fail_with_format_diagnostic(field, value):
    ast = parse_pattern_m1b_text(
        export_pattern_m1b(
            make_closed_ir(), TerminologyProfile.US_EN, validator=resolved_validator()
        )
    )
    with pytest.raises(PatternFormatError):
        bind_pattern_m1b_semantics(replace(ast, **{field: value}), context())
