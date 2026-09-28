"""Core 1.1 checks against independent hand-assembled ring fixtures."""

from copy import deepcopy

import pytest
from conftest import make_closed_ir, resolved_artifacts, resolved_validator
from hypothesis import given, settings
from hypothesis import strategies as st
from ring_fixtures import make_multi_ring_ir

from crochet_ai.canonical import CanonicalProfile, canonical_bytes
from crochet_ai.equivalence import semantic_bytes
from crochet_ai.pattern import (
    PatternFormatError,
    TerminologyProfile,
    export_pattern,
    parse_pattern,
    parse_pattern_text,
)
from crochet_ai.pattern_context import PatternParseContext, PatternYarnBinding
from crochet_ai.schema import validate_schema


@pytest.mark.parametrize("profile", tuple(TerminologyProfile))
@pytest.mark.parametrize("count", [2, 6, 30])
def test_independent_ring_text_round_trip(profile: TerminologyProfile, count: int) -> None:
    value = make_multi_ring_ir(count)
    validator = resolved_validator()
    design, material = resolved_artifacts()
    context = PatternParseContext(
        design, (PatternYarnBinding("Yarn A", material, "Natural", "#C8B08A"),)
    )
    text = export_pattern(value, profile, validator=validator)
    assert f"for {count} stitches" in text
    rebound = parse_pattern(text, context=context)
    assert rebound["schema_version"] == "1.1.0"
    assert semantic_bytes(value, validator=validator) == semantic_bytes(
        rebound, validator=validator
    )


@pytest.mark.parametrize(
    "before,after",
    [
        ("for 6 stitches", "for 5 stitches"),
        ("at Marker B", "at Marker A"),
        ("mark Marker G", "mark Marker H"),
        ("Work 1 sc at Marker A", "Work 1 sc increase at Marker A"),
        ("Work 1 sc at Marker F; mark Marker L. (6)\n", ""),
        ("Work 1 sc at Marker B", "Round 2 (cyclic, anchor Marker G):\nWork 1 sc at Marker B"),
    ],
)
def test_visible_multi_ring_corruption_fails_without_context(before: str, after: str) -> None:
    text = export_pattern(
        make_multi_ring_ir(), TerminologyProfile.US_EN, validator=resolved_validator()
    )
    assert before in text
    with pytest.raises(PatternFormatError):
        parse_pattern_text(text.replace(before, after))


@given(st.integers(min_value=2, max_value=16))
@settings(max_examples=15, deadline=None)
def test_explicit_sites_form_one_valid_ring(count: int) -> None:
    """N independent single-use sites produce N tops on one cyclic frontier."""
    value = make_multi_ring_ir(count)
    assert validate_schema("crochet_ir", value).ok
    report = resolved_validator().validate_crochet_ir(value)
    assert report.ok, report.diagnostics
    assert len(value["components"]) == 1
    assert len(value["stitches"]) == count


@pytest.mark.parametrize(
    "schema,semantics",
    [
        ("1.0.0", "CROCHET_CORE_1.1.0"),
        ("1.1.0", "CROCHET_CORE_1.0.0"),
        ("1.2.0", "CROCHET_CORE_1.1.0"),
        ("1.1.0", "CROCHET_CORE_9.0.0"),
    ],
)
def test_mismatched_or_unknown_versions_fail(schema: str, semantics: str) -> None:
    value = make_multi_ring_ir()
    value.update(schema_version=schema, semantics_profile=semantics)
    assert not validate_schema("crochet_ir", value).ok


def test_legacy_contract_does_not_accept_multi_site_ring() -> None:
    value = make_multi_ring_ir()
    value.update(schema_version="1.0.0", semantics_profile="CROCHET_CORE_1.0.0")
    value["required_capabilities"].remove("MULTI_STITCH_RING_V1")
    assert not validate_schema("crochet_ir", value).ok
    assert resolved_validator().validate_crochet_ir(make_closed_ir()).ok


@pytest.mark.parametrize(
    "defect", ["capability", "duplicate", "ordinal", "type", "reuse", "shaping"]
)
def test_ring_defects_fail_independently(defect: str) -> None:
    value = make_multi_ring_ir()
    if defect == "capability":
        value["required_capabilities"].remove("MULTI_STITCH_RING_V1")
    elif defect == "duplicate":
        value["construction_operations"][0]["attachment_location_ids"][1] = "loc_ring_0"
    elif defect == "ordinal":
        value["attachment_locations"][1]["ordinal_within_producer"] = 0
    elif defect == "type":
        value["attachment_locations"][0]["location_type"] = "TOP_LOOP"
    elif defect == "reuse":
        value["stitches"][1]["base_attachment_location_ids"] = ["loc_ring_0"]
    else:
        value["stitches"][0]["stitch_type"] = "DOUBLE_CROCHET"
    assert not resolved_validator().validate_crochet_ir(value).ok


def test_entity_permutations_preserve_new_version_identity() -> None:
    value = make_multi_ring_ir()
    shuffled = deepcopy(value)
    for table in ("stitches", "attachment_locations", "frontiers", "construction_operations"):
        shuffled[table].reverse()
    validator = resolved_validator()
    assert canonical_bytes(
        value, CanonicalProfile.CROCHET_IR, validator=validator
    ) == canonical_bytes(shuffled, CanonicalProfile.CROCHET_IR, validator=validator)
    assert semantic_bytes(value, validator=validator) == semantic_bytes(
        shuffled, validator=validator
    )


@pytest.mark.parametrize("profile", tuple(TerminologyProfile))
def test_explicit_later_courses_preserve_all_base_and_top_arities(
    profile: TerminologyProfile,
) -> None:
    # Hand-authored execution trace, not produced by solver placement or binder helpers.
    text = export_pattern(
        make_multi_ring_ir(), TerminologyProfile.US_EN, validator=resolved_validator()
    )
    rounds = """Round 2 (cyclic, anchor Marker G):
Work 1 sc increase at Marker G; mark Marker M and Marker N. (7)
Work 1 sc increase at Marker H; mark Marker O and Marker P. (8)
Work 1 sc increase at Marker I; mark Marker Q and Marker R. (9)
Work 1 sc increase at Marker J; mark Marker S and Marker T. (10)
Work 1 sc increase at Marker K; mark Marker U and Marker V. (11)
Work 1 sc increase at Marker L; mark Marker W and Marker X. (12)
Round 3 (cyclic, anchor Marker M):
Work 1 sc decrease at Marker M and Marker N; mark Marker Y. (11)
Work 1 sc decrease at Marker O and Marker P; mark Marker Z. (10)
Work 1 sc decrease at Marker Q and Marker R; mark Marker AA. (9)
Work 1 sc decrease at Marker S and Marker T; mark Marker AB. (8)
Work 1 sc decrease at Marker U and Marker V; mark Marker AC. (7)
Work 1 sc decrease at Marker W and Marker X; mark Marker AD. (6)
"""
    text = text.replace("Close work.", rounds + "Close work.")
    design, material = resolved_artifacts()
    context = PatternParseContext(
        design, (PatternYarnBinding("Yarn A", material, "Natural", "#C8B08A"),)
    )
    value = parse_pattern(text, context=context)
    validator = resolved_validator()
    assert validator.validate_crochet_ir(value).ok
    assert [len(course["member_event_ids"]) for course in value["courses"]] == [6, 6, 6]
    arities = [
        (len(stitch["base_attachment_location_ids"]), len(stitch["top_attachment_location_ids"]))
        for stitch in value["stitches"]
    ]
    assert arities == [(1, 1)] * 6 + [(1, 2)] * 6 + [(2, 1)] * 6
    rendered = export_pattern(value, profile, validator=validator)
    assert semantic_bytes(
        parse_pattern(rendered, context=context), validator=validator
    ) == semantic_bytes(value, validator=validator)


def test_cyclic_decrease_across_live_origin_round_trips() -> None:
    text = export_pattern(
        make_multi_ring_ir(), TerminologyProfile.US_EN, validator=resolved_validator()
    )
    second = """Round 2 (cyclic, anchor Marker G):
Work 1 sc decrease at Marker L and Marker G; mark Marker M. (5)
Work 1 sc at Marker H; mark Marker N. (5)
Work 1 sc at Marker I; mark Marker O. (5)
Work 1 sc at Marker J; mark Marker P. (5)
Work 1 sc at Marker K; mark Marker Q. (5)
"""
    design, material = resolved_artifacts()
    context = PatternParseContext(
        design, (PatternYarnBinding("Yarn A", material, "Natural", "#C8B08A"),)
    )
    value = parse_pattern(text.replace("Close work.", second + "Close work."), context=context)
    validator = resolved_validator()
    rendered = export_pattern(value, TerminologyProfile.US_EN, validator=validator)
    assert "at Marker L and Marker G; mark Marker M" in rendered
    assert semantic_bytes(value, validator=validator) == semantic_bytes(
        parse_pattern(rendered, context=context), validator=validator
    )


@pytest.mark.parametrize("defect", ["course_split", "site_order", "unsupported_family"])
def test_ring_initial_course_gate_rejects_semantic_defects(defect: str) -> None:
    value = make_multi_ring_ir()
    if defect == "course_split":
        first = value["courses"][0]
        second = deepcopy(first)
        second.update(
            course_id="course_split",
            ordinal=1,
            member_event_ids=[first["member_event_ids"].pop()],
            input_frontier_ids=["frontier_ring_4"],
            derivation_id="deriv_split",
        )
        first["output_frontier_ids"] = ["frontier_ring_4"]
        value["stitches"][-1]["course_id"] = "course_split"
        value["courses"].append(second)
        value["course_order"].append("course_split")
        value["branches"][0]["course_ids"].append("course_split")
        derivation = deepcopy(
            next(d for d in value["derivations"] if d["derivation_id"] == first["derivation_id"])
        )
        derivation.update(
            derivation_id="deriv_split",
            subject_refs=[{"entity_type": "COURSE", "course_id": "course_split"}],
        )
        value["derivations"].append(derivation)
    elif defect == "site_order":
        sites = value["construction_operations"][0]["attachment_location_ids"]
        sites[0], sites[1] = sites[1], sites[0]
    else:
        value["stitches"][0]["stitch_type"] = "DOUBLE_CROCHET"
    assert validate_schema("crochet_ir", value).ok
    report = resolved_validator().validate_crochet_ir(value)
    assert "magic_ring.initial_course" in {
        diagnostic.message_key for diagnostic in report.diagnostics
    }
