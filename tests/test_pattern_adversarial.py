"""Independent text mutations protecting the Pattern V1 trust boundary."""

from copy import deepcopy

import pytest
from conftest import make_closed_ir, make_increase_ir, resolved_artifacts, resolved_validator
from hypothesis import given, settings
from hypothesis import strategies as st

from crochet_ai.diagnostics import FailureCode
from crochet_ai.equivalence import semantic_bytes
from crochet_ai.pattern import (
    PatternFormatError,
    TerminologyProfile,
    build_certification_manifest,
    export_pattern,
    parse_pattern,
    parse_pattern_text,
)
from crochet_ai.pattern_context import PatternParseContext, PatternYarnBinding


def context() -> PatternParseContext:
    design, material = resolved_artifacts()
    return PatternParseContext(
        design, (PatternYarnBinding("Yarn A", material, "Natural", "#C8B08A"),)
    )


TEXT = (
    "CROCHET PATTERN V1\nTerminology: US\n\nMaterials\n"
    "Yarn A: external material binding.\n\nInstructions\n"
    "Make a magic ring with Yarn A; set Marker A.\n"
    "Round 1 (cyclic, anchor Marker A):\nWork 1 sc. (1)\n"
    "Close work.\n\nEND\n"
)


def test_unknown_anchor_cannot_be_repaired_by_context() -> None:
    with pytest.raises(PatternFormatError):
        parse_pattern(TEXT.replace("anchor Marker A", "anchor Marker Z"), context=context())


def test_duplicate_course_numbers_are_rejected_by_text_parser() -> None:
    text = TEXT.replace(
        "Close work.",
        "Round 1 (cyclic, anchor Marker B):\nWork 1 sc. (1)\nClose work.",
    )
    with pytest.raises(PatternFormatError):
        parse_pattern_text(text)


def test_stitches_cannot_resume_after_close() -> None:
    text = TEXT.replace(
        "Close work.",
        "Close work.\nRound 2 (cyclic, anchor Marker B):\nWork 1 sc. (1)",
    )
    with pytest.raises(PatternFormatError):
        parse_pattern_text(text)


@pytest.mark.parametrize("cut", range(len(TEXT.splitlines())))
def test_truncated_lines_return_structured_errors(cut: int) -> None:
    text = "\n".join(TEXT.splitlines()[:cut]) + "\n"
    with pytest.raises(PatternFormatError):
        parse_pattern_text(text)


def test_invalid_unicode_returns_structured_error() -> None:
    with pytest.raises(PatternFormatError):
        parse_pattern_text(TEXT.replace("Marker A", "\ud800"))


def test_unbounded_integer_returns_structured_error() -> None:
    with pytest.raises(PatternFormatError):
        parse_pattern_text(TEXT.replace("(1)", "(" + "9" * 5000 + ")"))


def test_export_is_independent_of_entity_table_order() -> None:
    source = make_increase_ir()
    reordered = deepcopy(source)
    for table in ("attachment_locations", "frontiers", "stitches", "construction_operations"):
        reordered[table].reverse()
    validator = resolved_validator()
    assert export_pattern(source, TerminologyProfile.US_EN, validator=validator) == export_pattern(
        reordered, TerminologyProfile.US_EN, validator=validator
    )


def test_certification_does_not_sign_arbitrary_text() -> None:
    with pytest.raises(PatternFormatError):
        build_certification_manifest(
            make_closed_ir(), "not a pattern", TerminologyProfile.US_EN,
            validator=resolved_validator(),
        )


def test_export_does_not_silently_change_work_direction() -> None:
    source = make_closed_ir()
    source["courses"][0]["work_direction"] = "COUNTERCLOCKWISE"
    validator = resolved_validator()
    assert validator.validate_crochet_ir(source).ok
    with pytest.raises(PatternFormatError):
        export_pattern(source, TerminologyProfile.US_EN, validator=validator)


def test_export_rejects_a_valid_but_unexpressed_frontier_rotation() -> None:
    source = make_increase_ir()
    source["frontiers"][1]["attachment_location_ids"].reverse()
    source["frontiers"][1]["anchor_attachment_location_id"] = (
        source["frontiers"][1]["attachment_location_ids"][0]
    )
    source["frontier_transitions"][2]["retired_attachment_location_ids"].reverse()
    validator = resolved_validator()
    assert validator.validate_crochet_ir(source).ok
    with pytest.raises(PatternFormatError):
        export_pattern(source, TerminologyProfile.US_EN, validator=validator)


def test_frozen_ring_anchor_cannot_be_reused_by_a_second_plain_stitch() -> None:
    """Independent two-stitch fixture exposes the foundation-contract limitation."""
    source = make_closed_ir()
    first = source["stitches"][0]
    previous_top = first["top_attachment_location_ids"][0]
    second = deepcopy(first)
    second.update(stitch_id="st_second", base_attachment_location_ids=[previous_top],
                  top_attachment_location_ids=["loc_second"], derivation_id="deriv_second")
    second["frontier_edit"]["frontier_id"] = "frontier_fixture_after_sc"
    subject = {"entity_type": "STITCH", "stitch_id": "st_second"}
    source["stitches"].append(second)
    source["attachment_locations"].append({
        "attachment_location_id": "loc_second", "location_type": "TOP_LOOP",
        "producer_ref": subject, "ordinal_within_producer": 0,
    })
    derivation = deepcopy(source["derivations"][0])
    derivation.update(derivation_id="deriv_second", subject_refs=[subject])
    source["derivations"].append(derivation)
    frontier = deepcopy(source["frontiers"][1])
    frontier.update(frontier_id="frontier_second", attachment_location_ids=["loc_second"],
                    anchor_attachment_location_id="loc_second",
                    created_by_transition_id="ftrans_second")
    source["frontiers"].append(frontier)
    transition = deepcopy(source["frontier_transitions"][1])
    transition.update(frontier_transition_id="ftrans_second", transition_index=2,
                      after_event_index=2, caused_by_subject_ref=subject,
                      input_frontier_ids=["frontier_fixture_after_sc"],
                      output_frontier_ids=["frontier_second"],
                      retired_attachment_location_ids=[previous_top],
                      created_attachment_location_ids=["loc_second"])
    close_transition = source["frontier_transitions"][2]
    close_transition.update(transition_index=3, after_event_index=3,
                            input_frontier_ids=["frontier_second"],
                            retired_attachment_location_ids=["loc_second"])
    source["frontier_transitions"].insert(2, transition)
    event = deepcopy(source["construction_sequence"][1])
    event.update(event_id="ev_second", sequence_index=2, subject_ref=subject,
                 frontier_transition_ids=["ftrans_second"])
    source["construction_sequence"][2]["sequence_index"] = 3
    source["construction_sequence"].insert(2, event)
    source["construction_operations"][-1]["input_frontier_ids"] = ["frontier_second"]
    source["courses"][0]["member_event_ids"].append("ev_second")
    source["courses"][0]["output_frontier_ids"] = ["frontier_second"]
    source["yarn_paths"][0]["segments"][0]["event_ids"].insert(1, "ev_second")
    validator = resolved_validator()
    assert validator.validate_crochet_ir(source).ok
    ring = first["base_attachment_location_ids"][0]
    second["base_attachment_location_ids"] = [ring]
    transition["retired_attachment_location_ids"] = [ring]
    report = validator.validate_crochet_ir(source)
    assert not report.ok
    assert any(item.code == FailureCode.FRONTIER for item in report.diagnostics)


def test_color_changes_keep_order_and_separate_yarn_segments() -> None:
    design, material = resolved_artifacts()
    bindings = PatternParseContext(design, (
        PatternYarnBinding("Yarn A", material, "Natural", "#C8B08A"),
        PatternYarnBinding("Yarn B", material, "Blue", "#0000FF"),
    ))
    text = TEXT.replace(
        "Yarn A: external material binding.",
        "Yarn A: external material binding.\nYarn B: external material binding.",
    ).replace(
        "Work 1 sc. (1)",
        "Work 1 sc. (1)\nChange to Yarn B.\nWork 1 sc increase. (2)\n"
        "Change to Yarn A.\nWork 1 sc decrease. (1)",
    )
    value = parse_pattern(text, context=bindings)
    events = value["construction_sequence"]
    assert [event["subject_ref"]["entity_type"] for event in events] == [
        "CONSTRUCTION_OPERATION", "STITCH", "CONSTRUCTION_OPERATION", "STITCH",
        "CONSTRUCTION_OPERATION", "STITCH", "CONSTRUCTION_OPERATION",
    ]
    paths = value["yarn_paths"]
    assert [len(path["segments"]) for path in paths] == [2, 1]
    assert paths[0]["segments"][0]["end_operation_type"] == "COLOR_CHANGE"
    assert paths[1]["segments"][0]["end_operation_type"] == "COLOR_CHANGE"
    assert paths[0]["segments"][1]["end_operation_type"] is None
    exported = export_pattern(value, TerminologyProfile.US_EN, validator=resolved_validator())
    assert exported == text
    rebound = parse_pattern(exported, context=bindings)
    assert semantic_bytes(value, validator=resolved_validator()) == semantic_bytes(
        rebound, validator=resolved_validator()
    )


def test_multiple_courses_preserve_their_current_anchors() -> None:
    text = TEXT.replace(
        "Close work.",
        "Round 2 (cyclic, anchor Marker B):\nWork 1 sc increase. (2)\nClose work.",
    )
    value = parse_pattern(text, context=context())
    assert len(value["courses"]) == 2
    assert export_pattern(value, TerminologyProfile.US_EN, validator=resolved_validator()) == text
    with pytest.raises(PatternFormatError):
        parse_pattern_text(text.replace("anchor Marker B", "anchor Marker A"))


def test_more_than_twenty_six_markers_round_trip() -> None:
    instructions = "\n".join("Work 1 sc. (1)" for _ in range(30))
    text = TEXT.replace("Work 1 sc. (1)", instructions).replace(
        "Close work.", "Round 2 (cyclic, anchor Marker AE):\nWork 1 sc. (1)\nClose work."
    )
    value = parse_pattern(text, context=context())
    assert export_pattern(value, TerminologyProfile.US_EN, validator=resolved_validator()) == text


@given(st.text(max_size=200))
@settings(max_examples=100, deadline=None)
def test_arbitrary_input_never_leaks_unstructured_parser_errors(text: str) -> None:
    """Independent arbitrary Unicode input must reject with a V9 diagnostic."""
    with pytest.raises(PatternFormatError) as error:
        parse_pattern_text(text)
    assert error.value.report.diagnostics[0].gate == "V9"


@given(st.integers(min_value=0, max_value=len(TEXT)))
@settings(max_examples=100, deadline=None)
def test_character_truncation_never_recovers_missing_structure(cut: int) -> None:
    """Every strict prefix is incomplete; the oracle is the handwritten envelope."""
    text = TEXT[:cut]
    if text == TEXT:
        parse_pattern_text(text)
    else:
        with pytest.raises(PatternFormatError):
            parse_pattern_text(text)
