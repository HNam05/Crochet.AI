from __future__ import annotations

from copy import deepcopy

import pytest
from conftest import (
    make_closed_ir,
    make_increase_ir,
    make_reserve_ir,
    make_split_join_ir,
    resolved_artifacts,
    resolved_validator,
)

from crochet_ai.diagnostics import ArtifactValidationError
from crochet_ai.equivalence import semantic_bytes
from crochet_ai.pattern import PatternFormatError, TerminologyProfile
from crochet_ai.pattern_context import PatternParseContext, PatternYarnBinding
from crochet_ai.pattern_m1b import export_pattern_m1b, parse_pattern_m1b, parse_pattern_m1b_text
from crochet_ai.validation import SemanticValidator


def context() -> PatternParseContext:
    design, material = resolved_artifacts()
    return PatternParseContext(
        design,
        (PatternYarnBinding("Yarn A", material, "Natural", "#C8B08A"),),
    )


def _validated(value: dict) -> SemanticValidator:
    validator = resolved_validator()
    report = validator.validate_crochet_ir(value)
    assert report.ok, report
    return validator


def _plain_family(source: dict, family: str) -> dict:
    value = deepcopy(source)
    value["stitches"][0]["stitch_type"] = family
    return value


def _chain_fixture() -> dict:
    """One visible chain inserted at the sole cyclic gap of an independent raw IR."""
    value = deepcopy(make_closed_ir())
    stitch = value["stitches"][0]
    anchor = stitch["base_attachment_location_ids"][0]
    top = stitch["top_attachment_location_ids"][0]
    stitch.update(
        stitch_type="CHAIN",
        base_arity=0,
        base_attachment_location_ids=[],
        frontier_edit={
            "edit_type": "INSERT_AT_GAP",
            "frontier_id": "frontier_fixture_initial",
            "left_location_id": anchor,
            "right_location_id": anchor,
        },
    )
    value["frontiers"][1]["attachment_location_ids"] = [anchor, top]
    value["frontiers"][1]["anchor_attachment_location_id"] = anchor
    value["frontier_transitions"][1]["retired_attachment_location_ids"] = []
    value["frontier_transitions"][1]["created_attachment_location_ids"] = [top]
    value["frontier_transitions"][2]["retired_attachment_location_ids"] = [anchor, top]
    return value


@pytest.mark.parametrize(
    "family,source_factory",
    [
        ("CHAIN", _chain_fixture),
        ("SLIP_STITCH", make_closed_ir),
        ("SINGLE_CROCHET", make_closed_ir),
        ("HALF_DOUBLE_CROCHET", make_closed_ir),
        ("DOUBLE_CROCHET", make_closed_ir),
        ("TREBLE_CROCHET", make_closed_ir),
    ],
)
def test_every_plain_stitch_family_round_trips_from_raw_ir(family, source_factory):
    source = source_factory()
    if family != "CHAIN":
        source = _plain_family(source, family)
    validator = _validated(source)
    text = export_pattern_m1b(source, TerminologyProfile.US_EN, validator=validator)
    parsed = parse_pattern_m1b(text, context=context())
    assert validator.validate_crochet_ir(parsed).ok
    assert semantic_bytes(parsed, validator=validator) == semantic_bytes(
        source, validator=validator
    )


def test_binary_sc_increase_round_trips_from_raw_ir():
    source = make_increase_ir()
    validator = _validated(source)
    text = export_pattern_m1b(source, TerminologyProfile.UK_EN, validator=validator)
    parsed = parse_pattern_m1b(text, context=context())
    assert validator.validate_crochet_ir(parsed).ok
    assert semantic_bytes(parsed, validator=validator) == semantic_bytes(
        source, validator=validator
    )


@pytest.mark.parametrize(
    "before,after",
    [
        ("as active", "as reserved"),
        ("as reserved", "as active"),
        ("using Marker B", "using Marker A"),
    ],
)
def test_partition_and_retired_marker_corruption_cannot_be_repaired(before, after):
    source = make_reserve_ir()
    validator = _validated(source)
    text = export_pattern_m1b(source, TerminologyProfile.US_EN, validator=validator)
    damaged = text.replace(before, after, 1)
    with pytest.raises(PatternFormatError):
        parse_pattern_m1b_text(damaged)


@pytest.mark.parametrize(
    "before,after",
    [
        ("gap Marker A, Marker A", "gap Marker B, Marker A"),
        ("cyclic/Marker A/Yarn A", "cyclic/Marker B/Yarn A"),
    ],
)
def test_chain_gap_and_cyclic_anchor_corruption_fails_closed(before, after):
    source = _chain_fixture()
    validator = _validated(source)
    text = export_pattern_m1b(source, TerminologyProfile.US_EN, validator=validator)
    assert before in text
    with pytest.raises(PatternFormatError):
        parse_pattern_m1b_text(text.replace(before, after, 1))


def test_reversed_join_input_order_binds_a_distinct_valid_construction():
    source = make_split_join_ir()
    validator = _validated(source)
    text = export_pattern_m1b(source, TerminologyProfile.US_EN, validator=validator)
    join = next(line for line in text.splitlines() if ": Join;" in line)
    parts = join.split("; inputs ", 1)[1].rsplit("; method ", 1)
    inputs = parts[0].split(" | ")
    assert len(inputs) == 2
    reversed_text = text.replace(
        join, join.replace(" | ".join(inputs), " | ".join(reversed(inputs))), 1
    )
    parsed = parse_pattern_m1b(reversed_text, context=context())
    assert validator.validate_crochet_ir(parsed).ok
    assert semantic_bytes(parsed, validator=validator) != semantic_bytes(
        parse_pattern_m1b(text, context=context()), validator=validator
    )


def test_external_binding_must_match_visible_yarn_symbols_and_design():
    source = make_closed_ir()
    validator = _validated(source)
    text = export_pattern_m1b(source, TerminologyProfile.US_EN, validator=validator)
    design, material = resolved_artifacts()
    wrong_yarn = PatternParseContext(
        design,
        (PatternYarnBinding("Yarn B", material, "Natural", "#C8B08A"),),
    )
    with pytest.raises(PatternFormatError):
        parse_pattern_m1b(text, context=wrong_yarn)
    malformed_material = deepcopy(material)
    malformed_material["revision"] = True
    with pytest.raises(ArtifactValidationError):
        parse_pattern_m1b(
            text,
            context=PatternParseContext(
                design,
                (PatternYarnBinding("Yarn A", malformed_material, "Natural", "#C8B08A"),),
            ),
        )
    # The visible pattern contains no DesignSpec identity: the supplied context is
    # authoritative and the binder must bind to its exact validated artifact.
    rebound_design = deepcopy(design)
    rebound_design["design_spec_id"] = "ds_context_rebound"
    rebound = parse_pattern_m1b(
        text,
        context=PatternParseContext(
            rebound_design,
            (PatternYarnBinding("Yarn A", material, "Natural", "#C8B08A"),),
        ),
    )
    assert rebound["design_spec_ref"]["design_spec_id"] == "ds_context_rebound"
    assert (
        rebound["design_spec_ref"] != parse_pattern_m1b(text, context=context())["design_spec_ref"]
    )


def test_changed_join_method_binds_to_distinct_semantics_when_declared():
    original = make_split_join_ir()
    original_validator = _validated(original)
    original_text = export_pattern_m1b(
        original, TerminologyProfile.US_EN, validator=original_validator
    )

    sewn = deepcopy(original)
    sewn["required_capabilities"].append("SEWN_JOINS_V1")
    next(op for op in sewn["construction_operations"] if op["operation_type"] == "JOIN")[
        "join_method"
    ] = "SEWN"
    sewn_validator = _validated(sewn)
    sewn_text = export_pattern_m1b(sewn, TerminologyProfile.US_EN, validator=sewn_validator)
    assert "; method sewn;" in sewn_text
    assert semantic_bytes(sewn, validator=sewn_validator) != semantic_bytes(
        original, validator=original_validator
    )
    assert set(parse_pattern_m1b(sewn_text, context=context())["required_capabilities"]) == set(
        sewn["required_capabilities"]
    )
    assert original_text != sewn_text


@pytest.mark.parametrize(
    "mutation",
    [
        lambda text: text.replace("gap Marker A, Marker A", "gap none, none", 1),
        lambda text: text.replace("total 1", "total 0", 1),
        lambda text: text.replace("Core: 1.0.0", "Core: 9.9.9", 1),
    ],
)
def test_invalid_gap_totals_and_core_markers_fail_closed(mutation):
    source = _chain_fixture()
    validator = _validated(source)
    text = export_pattern_m1b(source, TerminologyProfile.US_EN, validator=validator)
    with pytest.raises(PatternFormatError):
        parse_pattern_m1b_text(mutation(text))
