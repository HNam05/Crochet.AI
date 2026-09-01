from __future__ import annotations

from copy import deepcopy

import pytest
from conftest import (
    make_closed_ir,
    make_increase_ir,
    make_reattach_ir,
    make_reserve_ir,
    make_split_join_ir,
    resolved_validator,
)
from hypothesis import given
from hypothesis import strategies as st

from crochet_ai import SemanticValidator
from crochet_ai.canonical import CanonicalProfile, canonical_hash
from crochet_ai.schema import validate_schema


def structural_validator() -> SemanticValidator:
    return resolved_validator()


def codes(report: object) -> set[str]:
    return {item.code for item in report.diagnostics}


def keys(report: object) -> set[str]:
    return {item.message_key for item in report.diagnostics}


def test_closed_ir_passes_schema_and_semantics(closed_ir: dict[str, object]) -> None:
    assert validate_schema("crochet_ir", closed_ir).ok
    assert structural_validator().validate_crochet_ir(closed_ir).ok


def test_schema_valid_does_not_imply_semantically_valid() -> None:
    from conftest import load_fixture

    value = load_fixture("crochet-ir.magic-ring-single-course.valid.json")
    assert validate_schema("crochet_ir", value).ok
    report = structural_validator().validate_crochet_ir(value)
    assert not report.ok
    assert "frontier.unintended_terminal_boundary" in keys(report)


def test_dangling_reference_fails_closed(closed_ir: dict[str, object]) -> None:
    closed_ir["stitches"][0]["yarn_id"] = "yarn_missing"
    report = structural_validator().validate_crochet_ir(closed_ir)
    assert not report.ok
    assert "E_REFERENCE" in codes(report)


def test_non_sc_shaping_is_representable_but_unsupported() -> None:
    value = make_increase_ir()
    value["stitches"][0]["stitch_type"] = "DOUBLE_CROCHET"
    report = structural_validator().validate_crochet_ir(value)
    assert "stitch.unsupported_form" in keys(report)
    assert "E_UNSUPPORTED_FEATURE" in codes(report)


def test_explicit_cyclic_singleton_chain_gap_is_valid() -> None:
    value = make_closed_ir()
    stitch = value["stitches"][0]
    stitch["stitch_type"] = "CHAIN"
    stitch["base_arity"] = 0
    stitch["base_attachment_location_ids"] = []
    stitch["frontier_edit"] = {
        "edit_type": "INSERT_AT_GAP",
        "frontier_id": "frontier_fixture_initial",
        "left_location_id": "loc_fixture_magic_anchor",
        "right_location_id": "loc_fixture_magic_anchor",
    }
    value["frontiers"][1]["attachment_location_ids"] = [
        "loc_fixture_magic_anchor",
        "loc_fixture_stitch_top",
    ]
    value["frontiers"][1]["anchor_attachment_location_id"] = "loc_fixture_magic_anchor"
    value["frontier_transitions"][1]["retired_attachment_location_ids"] = []
    value["frontier_transitions"][2]["retired_attachment_location_ids"] = [
        "loc_fixture_magic_anchor",
        "loc_fixture_stitch_top",
    ]
    assert validate_schema("crochet_ir", value).ok
    assert structural_validator().validate_crochet_ir(value).ok


@pytest.mark.parametrize(
    ("left", "right", "message_key"),
    [
        (None, None, "edit.illegal_cyclic_gap"),
        ("loc_fixture_magic_anchor", None, "edit.illegal_cyclic_gap"),
        (None, "loc_fixture_magic_anchor", "edit.illegal_cyclic_gap"),
    ],
)
def test_cyclic_chain_gap_never_uses_implicit_anchor(
    left: str | None, right: str | None, message_key: str
) -> None:
    value = make_closed_ir()
    stitch = value["stitches"][0]
    stitch["stitch_type"] = "CHAIN"
    stitch["base_arity"] = 0
    stitch["base_attachment_location_ids"] = []
    stitch["frontier_edit"] = {
        "edit_type": "INSERT_AT_GAP",
        "frontier_id": "frontier_fixture_initial",
        "left_location_id": left,
        "right_location_id": right,
    }
    value["frontier_transitions"][1]["retired_attachment_location_ids"] = []
    assert validate_schema("crochet_ir", value).ok
    report = structural_validator().validate_crochet_ir(value)
    assert message_key in keys(report)


def test_split_and_join_replay_conserves_every_location() -> None:
    value = make_split_join_ir()
    assert validate_schema("crochet_ir", value).ok
    report = structural_validator().validate_crochet_ir(value)
    assert report.ok, report.diagnostics


def test_join_orientation_is_semantic_and_checked() -> None:
    value = make_split_join_ir()
    join = next(
        operation
        for operation in value["construction_operations"]
        if operation["operation_type"] == "JOIN"
    )
    join["join_input_mappings"].reverse()
    assert validate_schema("crochet_ir", value).ok
    report = structural_validator().validate_crochet_ir(value)
    assert "join.mapping_order" in keys(report)


def test_reserve_obligation_cannot_be_lost() -> None:
    value = make_reserve_ir()
    assert validate_schema("crochet_ir", value).ok
    assert structural_validator().validate_crochet_ir(value).ok
    lost = deepcopy(value)
    lost["construction_operations"] = [
        item
        for item in lost["construction_operations"]
        if item["operation_id"] != "op_fixture_close_reserved"
    ]
    lost["construction_sequence"] = lost["construction_sequence"][:-1]
    lost["frontiers"] = [
        item
        for item in lost["frontiers"]
        if item["frontier_id"] != "frontier_fixture_closed_reserved"
    ]
    lost["frontier_transitions"] = lost["frontier_transitions"][:-1]
    lost["derivations"] = [
        item
        for item in lost["derivations"]
        if item["derivation_id"] != "deriv_fixture_close_reserved"
    ]
    lost["yarn_paths"][0]["segments"][0]["event_ids"] = lost["yarn_paths"][0]["segments"][0][
        "event_ids"
    ][:-1]
    lost["branches"][0]["terminal_frontier_ids"] = ["frontier_fixture_closed_active"]
    lost["components"][0]["terminal_frontier_ids"] = ["frontier_fixture_closed_active"]
    assert validate_schema("crochet_ir", lost).ok
    report = structural_validator().validate_crochet_ir(lost)
    assert "frontier.unintended_terminal_boundary" in keys(report)


@given(index=st.integers(min_value=0, max_value=3))
def test_property_event_index_mutation_is_rejected(index: int) -> None:
    value = make_split_join_ir()
    value["construction_sequence"][index]["sequence_index"] += 7
    report = structural_validator().validate_crochet_ir(value)
    assert not report.ok
    assert "sequence.noncontiguous" in keys(report)


@given(st.sampled_from(["left", "right", "both"]))
def test_property_cyclic_gap_missing_neighbors_is_rejected(missing: str) -> None:
    value = make_closed_ir()
    stitch = value["stitches"][0]
    stitch["stitch_type"] = "CHAIN"
    stitch["base_arity"] = 0
    stitch["base_attachment_location_ids"] = []
    left = None if missing in {"left", "both"} else "loc_fixture_magic_anchor"
    right = None if missing in {"right", "both"} else "loc_fixture_magic_anchor"
    stitch["frontier_edit"] = {
        "edit_type": "INSERT_AT_GAP",
        "frontier_id": "frontier_fixture_initial",
        "left_location_id": left,
        "right_location_id": right,
    }
    value["frontier_transitions"][1]["retired_attachment_location_ids"] = []
    assert not structural_validator().validate_crochet_ir(value).ok


def test_design_and_material_semantics(
    design_spec: dict[str, object], material_profile: dict[str, object]
) -> None:
    validator = SemanticValidator()
    assert validator.validate_material_profile(material_profile).ok
    assert validator.validate_design_spec(design_spec).ok
    inline = deepcopy(design_spec)
    inline["material_profile"] = {"binding_type": "INLINE", "profile": material_profile}
    assert validator.validate_design_spec(inline).ok


def test_non_finite_material_number_is_rejected(
    material_profile: dict[str, object],
) -> None:
    material_profile["hook_diameter_mm"] = float("nan")
    report = SemanticValidator().validate_material_profile(material_profile)
    assert "input.not_ijson" in keys(report)


def test_single_observation_gauge_is_independently_recomputed(
    material_profile: dict[str, object],
) -> None:
    material_profile["calibration_responses"][0]["effective_gauge"]["effective_stitch_pitch_mm"] = (
        999
    )
    report = SemanticValidator().validate_material_profile(material_profile)
    assert "material.gauge_observation_mismatch" in keys(report)


def _replicate_material_profile(material_profile: dict[str, object]) -> dict[str, object]:
    response = material_profile["calibration_responses"][0]
    response["observations"] = [
        {
            "specimen_id": "specimen_fixture_002",
            "stitch_span_count": 2,
            "stitch_span_length_mm": 8,
            "course_span_count": 2,
            "course_span_length_mm": 7,
        },
        {
            "specimen_id": "specimen_fixture_003",
            "stitch_span_count": 2,
            "stitch_span_length_mm": 9,
            "course_span_count": 2,
            "course_span_length_mm": 7.5,
        },
    ]
    response["effective_gauge"] = {
        "effective_stitch_pitch_mm": 4.25,
        "effective_course_pitch_mm": 3.625,
    }
    response["uncertainty"] = {
        "stitch_pitch_standard_uncertainty_mm": 0.25,
        "course_pitch_standard_uncertainty_mm": 0.125,
        "basis": "REPLICATE_COMBINED_STANDARD_UNCERTAINTY",
    }
    return material_profile


def test_replicate_gauge_and_type_a_uncertainty_are_independently_recomputed(
    material_profile: dict[str, object],
) -> None:
    value = _replicate_material_profile(material_profile)
    assert SemanticValidator().validate_material_profile(value).ok

    value["calibration_responses"][0]["effective_gauge"]["effective_stitch_pitch_mm"] = 999
    report = SemanticValidator().validate_material_profile(value)
    assert "material.replicate_gauge_mismatch" in keys(report)


def test_replicate_estimator_is_independent_of_unordered_observation_input_order(
    material_profile: dict[str, object],
) -> None:
    left = _replicate_material_profile(material_profile)
    right = deepcopy(left)
    right["calibration_responses"][0]["observations"].reverse()

    validator = SemanticValidator()
    assert validator.validate_material_profile(left).ok
    assert validator.validate_material_profile(right).ok


def test_replicate_uncertainty_contradiction_fails_closed(
    material_profile: dict[str, object],
) -> None:
    value = _replicate_material_profile(material_profile)
    value["calibration_responses"][0]["uncertainty"][
        "course_pitch_standard_uncertainty_mm"
    ] = 0.5

    report = SemanticValidator().validate_material_profile(value)
    assert "material.replicate_uncertainty_mismatch" in keys(report)


def test_transition_event_index_must_resolve(closed_ir: dict[str, object]) -> None:
    closed_ir["frontier_transitions"][1]["after_event_index"] = 999
    report = structural_validator().validate_crochet_ir(closed_ir)
    assert "transition.event_index_out_of_range" in keys(report)


def test_yarn_segment_dangling_event_is_rejected(closed_ir: dict[str, object]) -> None:
    closed_ir["yarn_paths"][0]["segments"][0]["event_ids"].append("ev_missing")
    report = structural_validator().validate_crochet_ir(closed_ir)
    assert "yarn_segment.dangling_event" in keys(report)


def test_event_color_must_match_active_yarn(closed_ir: dict[str, object]) -> None:
    closed_ir["colors"].append(
        {"color_id": "color_fixture_other", "label": "Other", "srgb_hex": "#000000"}
    )
    closed_ir["construction_sequence"][1]["active_color_id_before"] = "color_fixture_other"
    closed_ir["construction_sequence"][1]["active_color_id_after"] = "color_fixture_other"
    report = structural_validator().validate_crochet_ir(closed_ir)
    assert "sequence.yarn_color_mismatch" in keys(report)


def test_created_location_producer_must_match_transition_subject(
    closed_ir: dict[str, object],
) -> None:
    closed_ir["attachment_locations"][0]["producer_ref"] = {
        "entity_type": "CONSTRUCTION_OPERATION",
        "operation_id": "op_fixture_close",
    }
    report = structural_validator().validate_crochet_ir(closed_ir)
    assert "attachment.producer_transition_mismatch" in keys(report)


def test_frontier_operation_cannot_omit_paired_transition(
    closed_ir: dict[str, object],
) -> None:
    extra_operation = deepcopy(closed_ir["construction_operations"][-1])
    extra_operation["operation_id"] = "op_fixture_close_unpaired"
    extra_operation["derivation_id"] = "deriv_fixture_close_unpaired"
    closed_ir["construction_operations"].append(extra_operation)
    closed_ir["construction_sequence"].append(
        {
            "event_id": "ev_fixture_close_unpaired",
            "sequence_index": 3,
            "subject_ref": {
                "entity_type": "CONSTRUCTION_OPERATION",
                "operation_id": "op_fixture_close_unpaired",
            },
            "active_yarn_id_before": "yarn_fixture_main",
            "active_yarn_id_after": "yarn_fixture_main",
            "active_color_id_before": "color_fixture_natural",
            "active_color_id_after": "color_fixture_natural",
            "frontier_transition_ids": [],
        }
    )
    closed_ir["derivations"].append(
        {
            "derivation_id": "deriv_fixture_close_unpaired",
            "method": "MANUAL_BOOTSTRAP",
            "rule_id": "fixture.close-unpaired",
            "rule_version": "1.0.0",
            "parameter_sha256": "0" * 64,
            "subject_refs": [
                {
                    "entity_type": "CONSTRUCTION_OPERATION",
                    "operation_id": "op_fixture_close_unpaired",
                }
            ],
        }
    )
    closed_ir["yarn_paths"][0]["segments"][0]["event_ids"].append("ev_fixture_close_unpaired")
    report = structural_validator().validate_crochet_ir(closed_ir)
    assert "sequence.subject_transition_count" in keys(report)


def test_branch_parent_cycle_is_rejected(closed_ir: dict[str, object]) -> None:
    closed_ir["branches"][0]["parent_branch_ids"] = ["branch_fixture_main"]
    report = structural_validator().validate_crochet_ir(closed_ir)
    assert "branch.parent_cycle" in keys(report)


def test_branch_terminal_cannot_continue_inside_same_branch(
    closed_ir: dict[str, object],
) -> None:
    closed_ir["branches"][0]["terminal_frontier_ids"] = ["frontier_fixture_initial"]
    report = structural_validator().validate_crochet_ir(closed_ir)
    assert "branch.nonterminal_frontier" in keys(report)


def test_course_boundaries_must_match_member_replay(closed_ir: dict[str, object]) -> None:
    closed_ir["courses"][0]["output_frontier_ids"] = ["frontier_fixture_initial"]
    report = structural_validator().validate_crochet_ir(closed_ir)
    assert "course.frontier_boundary_mismatch" in keys(report)


def test_entity_derivation_must_name_its_subject(closed_ir: dict[str, object]) -> None:
    closed_ir["stitches"][0]["derivation_id"] = "deriv_fixture_close"
    report = structural_validator().validate_crochet_ir(closed_ir)
    assert "derivation.subject_mismatch" in keys(report)


def test_design_spec_reference_is_content_addressed(
    closed_ir: dict[str, object], design_spec: dict[str, object]
) -> None:
    closed_ir["design_spec_ref"] = {
        "design_spec_id": design_spec["design_spec_id"],
        "sha256": canonical_hash(design_spec, CanonicalProfile.DESIGN_SPEC),
    }
    validator = structural_validator()
    assert validator.validate_crochet_ir(closed_ir, design_spec).ok
    closed_ir["design_spec_ref"]["sha256"] = "f" * 64
    report = validator.validate_crochet_ir(closed_ir, design_spec)
    assert "design_spec_ref.content_mismatch" in keys(report)


def test_course_ordinal_must_be_branch_local_and_contiguous(
    closed_ir: dict[str, object],
) -> None:
    closed_ir["courses"][0]["ordinal"] = 99
    report = structural_validator().validate_crochet_ir(closed_ir)
    assert "course.ordinal_sequence" in keys(report)


def test_external_references_fail_closed_without_resolution(
    closed_ir: dict[str, object],
) -> None:
    report = SemanticValidator().validate_crochet_ir(closed_ir)
    assert "design_spec_ref.unresolved" in keys(report)
    assert "material_profile_ref.unresolved" in keys(report)


def test_external_reference_hashes_match_resolved_canonical_content(
    closed_ir: dict[str, object],
    design_spec: dict[str, object],
    material_profile: dict[str, object],
) -> None:
    closed_ir["design_spec_ref"] = {
        "design_spec_id": design_spec["design_spec_id"],
        "sha256": canonical_hash(design_spec, CanonicalProfile.DESIGN_SPEC),
    }
    material_hash = canonical_hash(material_profile, CanonicalProfile.MATERIAL_PROFILE)
    closed_ir["yarns"][0]["material_profile_ref"] = {
        "profile_id": material_profile["profile_id"],
        "revision": material_profile["revision"],
        "sha256": material_hash,
    }
    validator = SemanticValidator(
        material_profiles={material_profile["profile_id"]: material_profile}
    )
    assert validator.validate_crochet_ir(closed_ir, design_spec).ok
    closed_ir["yarns"][0]["material_profile_ref"]["sha256"] = "f" * 64
    report = validator.validate_crochet_ir(closed_ir, design_spec)
    assert "material_profile_ref.content_mismatch" in keys(report)


def test_reattach_target_must_belong_to_reserved_frontier() -> None:
    value = make_reattach_ir()
    assert validate_schema("crochet_ir", value).ok
    assert structural_validator().validate_crochet_ir(value).ok
    operation = next(
        item
        for item in value["construction_operations"]
        if item["operation_id"] == "op_fixture_reattach"
    )
    operation["attachment_location_ids"] = ["loc_fixture_stitch_top"]
    report = structural_validator().validate_crochet_ir(value)
    assert "reattach.contract" in keys(report)


def test_unused_color_is_rejected(closed_ir: dict[str, object]) -> None:
    closed_ir["colors"].append(
        {
            "color_id": "color_fixture_unused",
            "label": "Unused",
            "srgb_hex": "#010203",
        }
    )
    report = structural_validator().validate_crochet_ir(closed_ir)
    assert "color.unused" in keys(report)


def test_diagnostics_include_reproducibility_context(
    closed_ir: dict[str, object],
) -> None:
    closed_ir["courses"][0]["ordinal"] = 99
    diagnostic = structural_validator().validate_crochet_ir(closed_ir).diagnostics[0]
    assert set(diagnostic.reproducibility) == {
        "software_commit",
        "parameters_hash",
        "random_seed",
    }


def test_implied_capability_must_be_declared() -> None:
    value = make_increase_ir()
    value["required_capabilities"].remove("SHAPING_V1")
    report = structural_validator().validate_crochet_ir(value)
    assert "capability.missing_declaration" in keys(report)


def test_live_cyclic_frontier_must_begin_at_its_declared_anchor() -> None:
    """A cyclic snapshot cannot encode the same boundary from a different origin."""
    value = make_split_join_ir()
    frontier = next(
        item
        for item in value["frontiers"]
        if item["frontier_id"] == "frontier_fixture_branch_b_after"
    )
    frontier["attachment_location_ids"].reverse()

    report = structural_validator().validate_crochet_ir(value)

    assert "frontier.cyclic_anchor_origin" in keys(report)
