from __future__ import annotations

from copy import deepcopy

from conftest import make_split_join_ir, resolved_validator
from hypothesis import given, settings
from hypothesis import strategies as st

from crochet_ai import SemanticValidator

MUTATIONS = (
    "duplicate_split_owner",
    "retire_delta_mismatch",
    "created_delta_mismatch",
    "edit_target_mismatch",
    "reuse_consumed_frontier",
    "unknown_location",
    "noncontiguous_transition_index",
    "join_output_leaks_consumed_site",
)


def structural_validator() -> SemanticValidator:
    return resolved_validator()


def _mutate(value: dict[str, object], mutation: str) -> None:
    if mutation == "duplicate_split_owner":
        value["frontiers"][3]["attachment_location_ids"] = ["loc_fixture_stitch_top"]
        value["frontiers"][3]["anchor_attachment_location_id"] = "loc_fixture_stitch_top"
    elif mutation == "retire_delta_mismatch":
        value["frontier_transitions"][5]["retired_attachment_location_ids"] = [
            "loc_fixture_stitch_top"
        ]
    elif mutation == "created_delta_mismatch":
        value["frontier_transitions"][1]["created_attachment_location_ids"] = [
            "loc_fixture_stitch_top"
        ]
    elif mutation == "edit_target_mismatch":
        value["stitches"][0]["frontier_edit"]["frontier_id"] = "frontier_fixture_split_a"
    elif mutation == "reuse_consumed_frontier":
        value["frontier_transitions"][5]["input_frontier_ids"] = [
            "frontier_fixture_after_sc",
            "frontier_fixture_branch_b_after",
        ]
    elif mutation == "unknown_location":
        value["frontier_transitions"][5]["retired_attachment_location_ids"][0] = "loc_missing"
    elif mutation == "noncontiguous_transition_index":
        value["frontier_transitions"][2]["transition_index"] = 20
    elif mutation == "join_output_leaks_consumed_site":
        value["frontiers"][6]["attachment_location_ids"] = [
            "loc_fixture_branch_a_top",
            "loc_fixture_branch_b_top_2",
        ]
        value["frontiers"][6]["anchor_attachment_location_id"] = "loc_fixture_branch_a_top"
    else:
        raise AssertionError(mutation)


@settings(deadline=None)
@given(mutation=st.sampled_from(MUTATIONS))
def test_generated_malformed_ownership_states_are_rejected(mutation: str) -> None:
    value = make_split_join_ir()
    _mutate(value, mutation)
    assert not structural_validator().validate_crochet_ir(value).ok


@settings(deadline=None)
@given(st.lists(st.sampled_from(MUTATIONS), min_size=1, max_size=5, unique=True))
def test_composed_malformed_states_never_gain_validity(mutations: list[str]) -> None:
    value = make_split_join_ir()
    for mutation in mutations:
        _mutate(value, mutation)
    assert not structural_validator().validate_crochet_ir(value).ok


def test_diagnostics_are_deterministically_ordered_and_identified() -> None:
    value = make_split_join_ir()
    for mutation in ("duplicate_split_owner", "retire_delta_mismatch", "edit_target_mismatch"):
        _mutate(value, mutation)
    validator = structural_validator()
    first = validator.validate_crochet_ir(deepcopy(value))
    second = validator.validate_crochet_ir(deepcopy(value))
    assert first == second
    assert [item.diagnostic_id for item in first.diagnostics] == sorted(
        (item.diagnostic_id for item in second.diagnostics),
        key=lambda identifier: next(
            item.sort_key() for item in second.diagnostics if item.diagnostic_id == identifier
        ),
    )
