from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from conftest import make_closed_ir, make_split_join_ir, resolved_validator
from hypothesis import given
from hypothesis import strategies as st

from crochet_ai import are_semantically_equivalent as _are_semantically_equivalent
from crochet_ai import semantic_projection as _semantic_projection
from crochet_ai.diagnostics import ArtifactValidationError
from crochet_ai.equivalence import semantic_bytes as _semantic_bytes
from crochet_ai.equivalence import semantic_hash as _semantic_hash
from crochet_ai.schema import validate_schema

STRUCTURAL_VALIDATOR = resolved_validator()


def are_semantically_equivalent(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return _are_semantically_equivalent(left, right, validator=STRUCTURAL_VALIDATOR)


def semantic_projection(value: dict[str, Any]) -> dict[str, Any]:
    return _semantic_projection(value, validator=STRUCTURAL_VALIDATOR)


def semantic_bytes(value: dict[str, Any]) -> bytes:
    return _semantic_bytes(value, validator=STRUCTURAL_VALIDATOR)


def semantic_hash(value: dict[str, Any]) -> str:
    return _semantic_hash(value, validator=STRUCTURAL_VALIDATOR)


def _all_ids(value: dict[str, Any]) -> set[str]:
    result: set[str] = {value["crochet_ir_id"]}
    fields = {
        "colors": "color_id",
        "yarns": "yarn_id",
        "attachment_locations": "attachment_location_id",
        "stitches": "stitch_id",
        "construction_operations": "operation_id",
        "construction_sequence": "event_id",
        "courses": "course_id",
        "frontiers": "frontier_id",
        "frontier_transitions": "frontier_transition_id",
        "branches": "branch_id",
        "components": "component_id",
        "openings": "opening_id",
        "yarn_paths": "yarn_path_id",
        "derivations": "derivation_id",
    }
    for table, field in fields.items():
        result.update(item[field] for item in value[table])
    for path in value["yarn_paths"]:
        result.update(item["yarn_segment_id"] for item in path["segments"])
    result.update(item["design_requirement_id"] for item in value["openings"])
    return result


def _alpha_rename(value: dict[str, Any], suffix: str) -> dict[str, Any]:
    mapping = {identifier: f"{identifier}_{suffix}" for identifier in _all_ids(value)}

    def visit(node: Any) -> Any:
        if isinstance(node, dict):
            return {key: visit(child) for key, child in node.items()}
        if isinstance(node, list):
            return [visit(child) for child in node]
        if isinstance(node, str):
            return mapping.get(node, node)
        return node

    return visit(value)


def test_alpha_renaming_and_display_metadata_are_equivalent() -> None:
    left = make_split_join_ir()
    right = _alpha_rename(left, "renamed")
    right["colors"][0]["label"] = "Completely different display label"
    right["provenance"]["software_commit"] = "f" * 40
    right["crochet_ir_id"] += "_artifact"
    assert validate_schema("crochet_ir", right).ok
    assert are_semantically_equivalent(left, right)
    assert semantic_projection(left) == semantic_projection(right)
    assert semantic_hash(left) == semantic_hash(right)


@given(
    color_reverse=st.booleans(),
    yarn_reverse=st.booleans(),
    location_reverse=st.booleans(),
    frontier_reverse=st.booleans(),
)
def test_entity_table_permutations_are_equivalent(
    color_reverse: bool,
    yarn_reverse: bool,
    location_reverse: bool,
    frontier_reverse: bool,
) -> None:
    left = make_split_join_ir()
    right = deepcopy(left)
    if color_reverse:
        right["colors"].reverse()
    if yarn_reverse:
        right["yarns"].reverse()
    if location_reverse:
        right["attachment_locations"].reverse()
    if frontier_reverse:
        right["frontiers"].reverse()
    assert are_semantically_equivalent(left, right)


def test_unresolved_material_hash_is_rejected_before_equivalence() -> None:
    left = make_closed_ir()
    right = deepcopy(left)
    right["yarns"][0]["material_profile_ref"]["sha256"] = "1" * 64
    assert semantic_bytes(left)
    with pytest.raises(ArtifactValidationError):
        semantic_bytes(right)
    with pytest.raises(ArtifactValidationError):
        are_semantically_equivalent(left, right)


def test_join_method_and_orientation_are_preserved() -> None:
    left = make_split_join_ir()
    sewn = deepcopy(left)
    sewn_join = next(
        operation
        for operation in sewn["construction_operations"]
        if operation["operation_type"] == "JOIN"
    )
    sewn_join["join_method"] = "SEWN"
    sewn["required_capabilities"].append("SEWN_JOINS_V1")
    reversed_join = deepcopy(left)
    reversed_operation = next(
        operation
        for operation in reversed_join["construction_operations"]
        if operation["operation_type"] == "JOIN"
    )
    reversed_operation["join_input_mappings"][0]["orientation"] = "REVERSED"
    assert not are_semantically_equivalent(left, sewn)
    assert not are_semantically_equivalent(left, reversed_join)


def test_compound_increase_does_not_collapse_to_plain_stitch() -> None:
    left = make_split_join_ir()
    right = deepcopy(left)
    right["stitches"][0]["shaping"] = "PLAIN"
    right["stitches"][0]["top_arity"] = 1
    right["stitches"][0]["top_attachment_location_ids"] = ["loc_fixture_stitch_top"]
    # This deliberately malformed attempted normalization is rejected before projection.
    if validate_schema("crochet_ir", right).ok:
        with pytest.raises(ArtifactValidationError):
            are_semantically_equivalent(left, right)
    else:
        assert not validate_schema("crochet_ir", right).ok
