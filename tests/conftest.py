from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from crochet_ai import SemanticValidator
from crochet_ai.canonical import CanonicalProfile, canonical_hash

FIXTURES = Path(__file__).parent / "fixtures" / "schema-valid"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def resolved_artifacts() -> tuple[dict[str, Any], dict[str, Any]]:
    material = load_fixture("material-profile.minimal.valid.json")
    design = load_fixture("design-spec.analytic-sphere.valid.json")
    design["material_profile"] = {
        "binding_type": "INLINE",
        "profile": deepcopy(material),
    }
    return design, material


def resolved_validator() -> SemanticValidator:
    design, material = resolved_artifacts()
    return SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={(material["profile_id"], material["revision"]): material},
    )


def _bind_resolved_artifacts(value: dict[str, Any]) -> None:
    design, material = resolved_artifacts()
    value["design_spec_ref"] = {
        "design_spec_id": design["design_spec_id"],
        "sha256": canonical_hash(design, CanonicalProfile.DESIGN_SPEC),
    }
    material_hash = canonical_hash(material, CanonicalProfile.MATERIAL_PROFILE)
    for yarn in value["yarns"]:
        yarn["material_profile_ref"] = {
            "profile_id": material["profile_id"],
            "revision": material["revision"],
            "sha256": material_hash,
        }


def _derivation(identifier: str, operation_id: str) -> dict[str, Any]:
    return {
        "derivation_id": identifier,
        "method": "MANUAL_BOOTSTRAP",
        "rule_id": f"fixture.{operation_id}",
        "rule_version": "1.0.0",
        "parameter_sha256": "0" * 64,
        "subject_refs": [{"entity_type": "CONSTRUCTION_OPERATION", "operation_id": operation_id}],
    }


def _subject_derivation(
    identifier: str, entity_type: str, id_field: str, entity_id: str
) -> dict[str, Any]:
    return {
        "derivation_id": identifier,
        "method": "MANUAL_BOOTSTRAP",
        "rule_id": f"fixture.{entity_id}",
        "rule_version": "1.0.0",
        "parameter_sha256": "0" * 64,
        "subject_refs": [{"entity_type": entity_type, id_field: entity_id}],
    }


def _operation(
    identifier: str,
    operation_type: str,
    inputs: list[str],
    outputs: list[str],
    derivation_id: str,
    *,
    attachments: list[str] | None = None,
    mappings: list[dict[str, Any]] | None = None,
    join_method: str = "NONE",
) -> dict[str, Any]:
    return {
        "operation_id": identifier,
        "operation_type": operation_type,
        "input_frontier_ids": inputs,
        "output_frontier_ids": outputs,
        "attachment_location_ids": attachments or [],
        "join_input_mappings": mappings or [],
        "input_yarn_ids": [],
        "output_yarn_ids": [],
        "opening_id": None,
        "design_requirement_id": None,
        "join_method": join_method,
        "derivation_id": derivation_id,
    }


def _event(identifier: str, index: int, operation_id: str, transition_id: str) -> dict[str, Any]:
    return {
        "event_id": identifier,
        "sequence_index": index,
        "subject_ref": {"entity_type": "CONSTRUCTION_OPERATION", "operation_id": operation_id},
        "active_yarn_id_before": "yarn_fixture_main",
        "active_yarn_id_after": "yarn_fixture_main",
        "active_color_id_before": "color_fixture_natural",
        "active_color_id_after": "color_fixture_natural",
        "frontier_transition_ids": [transition_id],
    }


def _frontier(
    identifier: str,
    transition_id: str,
    locations: list[str],
    lifecycle: str,
) -> dict[str, Any]:
    return {
        "frontier_id": identifier,
        "component_id": "component_fixture_main",
        "branch_id": "branch_fixture_main",
        "topology": "CYCLIC",
        "lifecycle_state": lifecycle,
        "attachment_location_ids": locations,
        "anchor_attachment_location_id": locations[0] if locations else None,
        "active_yarn_id": "yarn_fixture_main" if lifecycle in {"ACTIVE", "RESERVED"} else None,
        "created_by_transition_id": transition_id,
    }


def _transition(
    identifier: str,
    index: int,
    operation_id: str,
    transition_type: str,
    inputs: list[str],
    outputs: list[str],
    *,
    retired: list[str] | None = None,
    created: list[str] | None = None,
    reserved: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "frontier_transition_id": identifier,
        "transition_index": index,
        "after_event_index": index,
        "caused_by_subject_ref": {
            "entity_type": "CONSTRUCTION_OPERATION",
            "operation_id": operation_id,
        },
        "transition_type": transition_type,
        "input_frontier_ids": inputs,
        "output_frontier_ids": outputs,
        "retired_attachment_location_ids": retired or [],
        "created_attachment_location_ids": created or [],
        "reserved_attachment_location_ids": reserved or [],
        "opening_id": None,
    }


def make_closed_ir() -> dict[str, Any]:
    value = load_fixture("crochet-ir.magic-ring-single-course.valid.json")
    value = deepcopy(value)
    value["construction_operations"].append(
        _operation(
            "op_fixture_close",
            "CLOSE",
            ["frontier_fixture_after_sc"],
            ["frontier_fixture_closed"],
            "deriv_fixture_close",
        )
    )
    value["construction_sequence"].append(
        _event("ev_fixture_close", 2, "op_fixture_close", "ftrans_fixture_close")
    )
    value["frontiers"].append(
        _frontier("frontier_fixture_closed", "ftrans_fixture_close", [], "CLOSED")
    )
    value["frontier_transitions"].append(
        _transition(
            "ftrans_fixture_close",
            2,
            "op_fixture_close",
            "CLOSE",
            ["frontier_fixture_after_sc"],
            ["frontier_fixture_closed"],
            retired=["loc_fixture_stitch_top"],
        )
    )
    value["branches"][0]["terminal_frontier_ids"] = ["frontier_fixture_closed"]
    value["components"][0]["terminal_frontier_ids"] = ["frontier_fixture_closed"]
    value["yarn_paths"][0]["segments"][0]["event_ids"] = [
        "ev_fixture_sc_001",
        "ev_fixture_close",
    ]
    value["derivations"].append(_derivation("deriv_fixture_close", "op_fixture_close"))
    _bind_resolved_artifacts(value)
    return value


def make_increase_ir() -> dict[str, Any]:
    value = make_closed_ir()
    value["required_capabilities"].append("SHAPING_V1")
    value["stitches"][0]["shaping"] = "INCREASE"
    value["stitches"][0]["top_arity"] = 2
    value["stitches"][0]["top_attachment_location_ids"] = [
        "loc_fixture_stitch_top",
        "loc_fixture_stitch_top_2",
    ]
    value["attachment_locations"].append(
        {
            "attachment_location_id": "loc_fixture_stitch_top_2",
            "location_type": "TOP_LOOP",
            "producer_ref": {"entity_type": "STITCH", "stitch_id": "st_fixture_sc_001"},
            "ordinal_within_producer": 1,
        }
    )
    value["frontiers"][1]["attachment_location_ids"] = [
        "loc_fixture_stitch_top",
        "loc_fixture_stitch_top_2",
    ]
    value["frontier_transitions"][1]["created_attachment_location_ids"] = [
        "loc_fixture_stitch_top",
        "loc_fixture_stitch_top_2",
    ]
    value["frontier_transitions"][2]["retired_attachment_location_ids"] = [
        "loc_fixture_stitch_top",
        "loc_fixture_stitch_top_2",
    ]
    return value


def _remove_close(value: dict[str, Any]) -> None:
    value["construction_operations"] = [
        item
        for item in value["construction_operations"]
        if item["operation_id"] != "op_fixture_close"
    ]
    value["construction_sequence"] = value["construction_sequence"][:2]
    value["frontiers"] = [
        item for item in value["frontiers"] if item["frontier_id"] != "frontier_fixture_closed"
    ]
    value["frontier_transitions"] = value["frontier_transitions"][:2]
    value["derivations"] = [
        item for item in value["derivations"] if item["derivation_id"] != "deriv_fixture_close"
    ]
    value["yarn_paths"][0]["segments"][0]["event_ids"] = ["ev_fixture_sc_001"]


def make_split_join_ir() -> dict[str, Any]:
    value = make_increase_ir()
    value["required_capabilities"].append("FRONTIER_BRANCHING_V1")
    _remove_close(value)
    top_a, top_b = "loc_fixture_stitch_top", "loc_fixture_stitch_top_2"
    produced = [
        ("loc_fixture_branch_a_top", "st_fixture_branch_a", 0),
        ("loc_fixture_branch_b_top_1", "st_fixture_branch_b", 0),
        ("loc_fixture_branch_b_top_2", "st_fixture_branch_b", 1),
        ("loc_fixture_joined_top", "st_fixture_joined", 0),
    ]
    for location_id, stitch_id, ordinal in produced:
        value["attachment_locations"].append(
            {
                "attachment_location_id": location_id,
                "location_type": "TOP_LOOP",
                "producer_ref": {"entity_type": "STITCH", "stitch_id": stitch_id},
                "ordinal_within_producer": ordinal,
            }
        )
    stitch_specs = [
        (
            "st_fixture_branch_a",
            "PLAIN",
            [top_a],
            ["loc_fixture_branch_a_top"],
            "frontier_fixture_split_a",
            "course_fixture_branch_a",
            "deriv_fixture_branch_a_stitch",
        ),
        (
            "st_fixture_branch_b",
            "INCREASE",
            [top_b],
            ["loc_fixture_branch_b_top_1", "loc_fixture_branch_b_top_2"],
            "frontier_fixture_split_b",
            "course_fixture_branch_b",
            "deriv_fixture_branch_b_stitch",
        ),
        (
            "st_fixture_joined",
            "PLAIN",
            ["loc_fixture_branch_b_top_2"],
            ["loc_fixture_joined_top"],
            "frontier_fixture_joined_active",
            "course_fixture_joined",
            "deriv_fixture_joined_stitch",
        ),
    ]
    for stitch_id, shaping, bases, tops, frontier_id, course_id, derivation_id in stitch_specs:
        value["stitches"].append(
            {
                "stitch_id": stitch_id,
                "stitch_type": "SINGLE_CROCHET",
                "shaping": shaping,
                "base_arity": len(bases),
                "top_arity": len(tops),
                "base_attachment_location_ids": bases,
                "top_attachment_location_ids": tops,
                "frontier_edit": {"edit_type": "REPLACE_SPAN", "frontier_id": frontier_id},
                "yarn_id": "yarn_fixture_main",
                "color_id": "color_fixture_natural",
                "course_id": course_id,
                "derivation_id": derivation_id,
            }
        )
    value["construction_operations"].extend(
        [
            _operation(
                "op_fixture_split",
                "SPLIT",
                ["frontier_fixture_after_sc"],
                ["frontier_fixture_split_a", "frontier_fixture_split_b"],
                "deriv_fixture_split",
            ),
            _operation(
                "op_fixture_join",
                "JOIN",
                ["frontier_fixture_branch_a_after", "frontier_fixture_branch_b_after"],
                ["frontier_fixture_joined_active"],
                "deriv_fixture_join",
                attachments=["loc_fixture_branch_a_top", "loc_fixture_branch_b_top_1"],
                mappings=[
                    {
                        "input_frontier_id": "frontier_fixture_branch_a_after",
                        "orientation": "FORWARD",
                        "consumed_attachment_location_ids": ["loc_fixture_branch_a_top"],
                    },
                    {
                        "input_frontier_id": "frontier_fixture_branch_b_after",
                        "orientation": "FORWARD",
                        "consumed_attachment_location_ids": ["loc_fixture_branch_b_top_1"],
                    },
                ],
                join_method="CROCHETED",
            ),
            _operation(
                "op_fixture_close_joined",
                "CLOSE",
                ["frontier_fixture_joined_after"],
                ["frontier_fixture_joined_closed"],
                "deriv_fixture_close_joined",
            ),
        ]
    )
    value["construction_sequence"].append(
        _event("ev_fixture_split", 2, "op_fixture_split", "ftrans_fixture_split")
    )
    for event_id, index, stitch_id, transition_id in (
        ("ev_fixture_branch_a", 3, "st_fixture_branch_a", "ftrans_fixture_branch_a"),
        ("ev_fixture_branch_b", 4, "st_fixture_branch_b", "ftrans_fixture_branch_b"),
    ):
        value["construction_sequence"].append(
            {
                "event_id": event_id,
                "sequence_index": index,
                "subject_ref": {"entity_type": "STITCH", "stitch_id": stitch_id},
                "active_yarn_id_before": "yarn_fixture_main",
                "active_yarn_id_after": "yarn_fixture_main",
                "active_color_id_before": "color_fixture_natural",
                "active_color_id_after": "color_fixture_natural",
                "frontier_transition_ids": [transition_id],
            }
        )
    value["construction_sequence"].append(
        _event("ev_fixture_join", 5, "op_fixture_join", "ftrans_fixture_join")
    )
    value["construction_sequence"].append(
        {
            "event_id": "ev_fixture_joined",
            "sequence_index": 6,
            "subject_ref": {"entity_type": "STITCH", "stitch_id": "st_fixture_joined"},
            "active_yarn_id_before": "yarn_fixture_main",
            "active_yarn_id_after": "yarn_fixture_main",
            "active_color_id_before": "color_fixture_natural",
            "active_color_id_after": "color_fixture_natural",
            "frontier_transition_ids": ["ftrans_fixture_joined"],
        }
    )
    value["construction_sequence"].append(
        _event(
            "ev_fixture_close_joined",
            7,
            "op_fixture_close_joined",
            "ftrans_fixture_close_joined",
        )
    )
    value["frontiers"].extend(
        [
            _frontier("frontier_fixture_split_a", "ftrans_fixture_split", [top_a], "ACTIVE"),
            _frontier("frontier_fixture_split_b", "ftrans_fixture_split", [top_b], "ACTIVE"),
            _frontier(
                "frontier_fixture_branch_a_after",
                "ftrans_fixture_branch_a",
                ["loc_fixture_branch_a_top"],
                "ACTIVE",
            ),
            _frontier(
                "frontier_fixture_branch_b_after",
                "ftrans_fixture_branch_b",
                ["loc_fixture_branch_b_top_1", "loc_fixture_branch_b_top_2"],
                "ACTIVE",
            ),
            _frontier(
                "frontier_fixture_joined_active",
                "ftrans_fixture_join",
                ["loc_fixture_branch_b_top_2"],
                "ACTIVE",
            ),
            _frontier(
                "frontier_fixture_joined_after",
                "ftrans_fixture_joined",
                ["loc_fixture_joined_top"],
                "ACTIVE",
            ),
            _frontier(
                "frontier_fixture_joined_closed",
                "ftrans_fixture_close_joined",
                [],
                "CLOSED",
            ),
        ]
    )
    frontier_branches = {
        "frontier_fixture_split_a": "branch_fixture_split_a",
        "frontier_fixture_split_b": "branch_fixture_split_b",
        "frontier_fixture_branch_a_after": "branch_fixture_split_a",
        "frontier_fixture_branch_b_after": "branch_fixture_split_b",
        "frontier_fixture_joined_active": "branch_fixture_joined",
        "frontier_fixture_joined_after": "branch_fixture_joined",
        "frontier_fixture_joined_closed": "branch_fixture_joined",
    }
    for frontier in value["frontiers"]:
        if frontier["frontier_id"] in frontier_branches:
            frontier["branch_id"] = frontier_branches[frontier["frontier_id"]]
    value["frontier_transitions"].extend(
        [
            _transition(
                "ftrans_fixture_split",
                2,
                "op_fixture_split",
                "SPLIT",
                ["frontier_fixture_after_sc"],
                ["frontier_fixture_split_a", "frontier_fixture_split_b"],
            ),
            _transition(
                "ftrans_fixture_join",
                5,
                "op_fixture_join",
                "JOIN",
                ["frontier_fixture_branch_a_after", "frontier_fixture_branch_b_after"],
                ["frontier_fixture_joined_active"],
                retired=["loc_fixture_branch_a_top", "loc_fixture_branch_b_top_1"],
            ),
            {
                "frontier_transition_id": "ftrans_fixture_branch_a",
                "transition_index": 3,
                "after_event_index": 3,
                "caused_by_subject_ref": {
                    "entity_type": "STITCH",
                    "stitch_id": "st_fixture_branch_a",
                },
                "transition_type": "ADVANCE",
                "input_frontier_ids": ["frontier_fixture_split_a"],
                "output_frontier_ids": ["frontier_fixture_branch_a_after"],
                "retired_attachment_location_ids": [top_a],
                "created_attachment_location_ids": ["loc_fixture_branch_a_top"],
                "reserved_attachment_location_ids": [],
                "opening_id": None,
            },
            {
                "frontier_transition_id": "ftrans_fixture_branch_b",
                "transition_index": 4,
                "after_event_index": 4,
                "caused_by_subject_ref": {
                    "entity_type": "STITCH",
                    "stitch_id": "st_fixture_branch_b",
                },
                "transition_type": "ADVANCE",
                "input_frontier_ids": ["frontier_fixture_split_b"],
                "output_frontier_ids": ["frontier_fixture_branch_b_after"],
                "retired_attachment_location_ids": [top_b],
                "created_attachment_location_ids": [
                    "loc_fixture_branch_b_top_1",
                    "loc_fixture_branch_b_top_2",
                ],
                "reserved_attachment_location_ids": [],
                "opening_id": None,
            },
            {
                "frontier_transition_id": "ftrans_fixture_joined",
                "transition_index": 6,
                "after_event_index": 6,
                "caused_by_subject_ref": {
                    "entity_type": "STITCH",
                    "stitch_id": "st_fixture_joined",
                },
                "transition_type": "ADVANCE",
                "input_frontier_ids": ["frontier_fixture_joined_active"],
                "output_frontier_ids": ["frontier_fixture_joined_after"],
                "retired_attachment_location_ids": ["loc_fixture_branch_b_top_2"],
                "created_attachment_location_ids": ["loc_fixture_joined_top"],
                "reserved_attachment_location_ids": [],
                "opening_id": None,
            },
            _transition(
                "ftrans_fixture_close_joined",
                7,
                "op_fixture_close_joined",
                "CLOSE",
                ["frontier_fixture_joined_after"],
                ["frontier_fixture_joined_closed"],
                retired=["loc_fixture_joined_top"],
            ),
        ]
    )
    value["frontier_transitions"] = sorted(
        value["frontier_transitions"], key=lambda item: item["transition_index"]
    )
    course_specs = [
        (
            "course_fixture_branch_a",
            "branch_fixture_split_a",
            "ev_fixture_branch_a",
            "frontier_fixture_split_a",
            "frontier_fixture_branch_a_after",
            "deriv_fixture_branch_a_course",
        ),
        (
            "course_fixture_branch_b",
            "branch_fixture_split_b",
            "ev_fixture_branch_b",
            "frontier_fixture_split_b",
            "frontier_fixture_branch_b_after",
            "deriv_fixture_branch_b_course",
        ),
        (
            "course_fixture_joined",
            "branch_fixture_joined",
            "ev_fixture_joined",
            "frontier_fixture_joined_active",
            "frontier_fixture_joined_after",
            "deriv_fixture_joined_course",
        ),
    ]
    for course_id, branch_id, event_id, input_id, output_id, derivation_id in course_specs:
        value["courses"].append(
            {
                "course_id": course_id,
                "ordinal": 0,
                "component_id": "component_fixture_main",
                "branch_id": branch_id,
                "course_form": "CYCLIC",
                "turn_mode": "CONTINUOUS_SPIRAL",
                "work_direction": "CLOCKWISE",
                "member_event_ids": [event_id],
                "input_frontier_ids": [input_id],
                "output_frontier_ids": [output_id],
                "derivation_id": derivation_id,
            }
        )
        value["course_order"].append(course_id)
    value["branches"][0]["terminal_frontier_ids"] = ["frontier_fixture_after_sc"]
    value["branches"].extend(
        [
            {
                "branch_id": "branch_fixture_split_a",
                "component_id": "component_fixture_main",
                "parent_branch_ids": ["branch_fixture_main"],
                "created_by_transition_id": "ftrans_fixture_split",
                "course_ids": ["course_fixture_branch_a"],
                "entry_frontier_ids": ["frontier_fixture_split_a"],
                "terminal_frontier_ids": ["frontier_fixture_branch_a_after"],
            },
            {
                "branch_id": "branch_fixture_split_b",
                "component_id": "component_fixture_main",
                "parent_branch_ids": ["branch_fixture_main"],
                "created_by_transition_id": "ftrans_fixture_split",
                "course_ids": ["course_fixture_branch_b"],
                "entry_frontier_ids": ["frontier_fixture_split_b"],
                "terminal_frontier_ids": ["frontier_fixture_branch_b_after"],
            },
            {
                "branch_id": "branch_fixture_joined",
                "component_id": "component_fixture_main",
                "parent_branch_ids": ["branch_fixture_split_a", "branch_fixture_split_b"],
                "created_by_transition_id": "ftrans_fixture_join",
                "course_ids": ["course_fixture_joined"],
                "entry_frontier_ids": ["frontier_fixture_joined_active"],
                "terminal_frontier_ids": ["frontier_fixture_joined_closed"],
            },
        ]
    )
    value["components"][0]["branch_ids"] = [
        "branch_fixture_main",
        "branch_fixture_split_a",
        "branch_fixture_split_b",
        "branch_fixture_joined",
    ]
    value["components"][0]["terminal_frontier_ids"] = ["frontier_fixture_joined_closed"]
    value["yarn_paths"][0]["segments"][0]["event_ids"].extend(
        [
            "ev_fixture_split",
            "ev_fixture_branch_a",
            "ev_fixture_branch_b",
            "ev_fixture_join",
            "ev_fixture_joined",
            "ev_fixture_close_joined",
        ]
    )
    value["derivations"].extend(
        [
            _derivation("deriv_fixture_split", "op_fixture_split"),
            _derivation("deriv_fixture_join", "op_fixture_join"),
            _derivation("deriv_fixture_close_joined", "op_fixture_close_joined"),
            _subject_derivation(
                "deriv_fixture_branch_a_stitch",
                "STITCH",
                "stitch_id",
                "st_fixture_branch_a",
            ),
            _subject_derivation(
                "deriv_fixture_branch_b_stitch",
                "STITCH",
                "stitch_id",
                "st_fixture_branch_b",
            ),
            _subject_derivation(
                "deriv_fixture_joined_stitch",
                "STITCH",
                "stitch_id",
                "st_fixture_joined",
            ),
            _subject_derivation(
                "deriv_fixture_branch_a_course",
                "COURSE",
                "course_id",
                "course_fixture_branch_a",
            ),
            _subject_derivation(
                "deriv_fixture_branch_b_course",
                "COURSE",
                "course_id",
                "course_fixture_branch_b",
            ),
            _subject_derivation(
                "deriv_fixture_joined_course",
                "COURSE",
                "course_id",
                "course_fixture_joined",
            ),
        ]
    )
    return value


def make_reserve_ir() -> dict[str, Any]:
    value = make_increase_ir()
    value["required_capabilities"].append("FRONTIER_BRANCHING_V1")
    _remove_close(value)
    top_a, top_b = "loc_fixture_stitch_top", "loc_fixture_stitch_top_2"
    value["construction_operations"].append(
        _operation(
            "op_fixture_reserve",
            "RESERVE",
            ["frontier_fixture_after_sc"],
            ["frontier_fixture_continuing", "frontier_fixture_reserved"],
            "deriv_fixture_reserve",
        )
    )
    value["construction_sequence"].append(
        _event("ev_fixture_reserve", 2, "op_fixture_reserve", "ftrans_fixture_reserve")
    )
    value["frontiers"].extend(
        [
            _frontier("frontier_fixture_continuing", "ftrans_fixture_reserve", [top_a], "ACTIVE"),
            _frontier("frontier_fixture_reserved", "ftrans_fixture_reserve", [top_b], "RESERVED"),
        ]
    )
    value["frontier_transitions"].append(
        _transition(
            "ftrans_fixture_reserve",
            2,
            "op_fixture_reserve",
            "RESERVE",
            ["frontier_fixture_after_sc"],
            ["frontier_fixture_continuing", "frontier_fixture_reserved"],
            reserved=[top_b],
        )
    )
    value["yarn_paths"][0]["segments"][0]["event_ids"].append("ev_fixture_reserve")
    for ordinal, (input_id, location_id) in enumerate(
        (("frontier_fixture_continuing", top_a), ("frontier_fixture_reserved", top_b)), start=3
    ):
        suffix = "active" if ordinal == 3 else "reserved"
        operation_id = f"op_fixture_close_{suffix}"
        transition_id = f"ftrans_fixture_close_{suffix}"
        output_id = f"frontier_fixture_closed_{suffix}"
        derivation_id = f"deriv_fixture_close_{suffix}"
        value["construction_operations"].append(
            _operation(operation_id, "CLOSE", [input_id], [output_id], derivation_id)
        )
        value["construction_sequence"].append(
            _event(f"ev_fixture_close_{suffix}", ordinal, operation_id, transition_id)
        )
        value["frontiers"].append(_frontier(output_id, transition_id, [], "CLOSED"))
        value["frontier_transitions"].append(
            _transition(
                transition_id,
                ordinal,
                operation_id,
                "CLOSE",
                [input_id],
                [output_id],
                retired=[location_id],
            )
        )
        value["derivations"].append(_derivation(derivation_id, operation_id))
        value["yarn_paths"][0]["segments"][0]["event_ids"].append(f"ev_fixture_close_{suffix}")
    terminals = ["frontier_fixture_closed_active", "frontier_fixture_closed_reserved"]
    value["branches"][0]["terminal_frontier_ids"] = terminals
    value["components"][0]["terminal_frontier_ids"] = terminals
    value["derivations"].append(_derivation("deriv_fixture_reserve", "op_fixture_reserve"))
    return value


def make_reattach_ir() -> dict[str, Any]:
    value = make_reserve_ir()
    top_b = "loc_fixture_stitch_top_2"
    close_reserved = next(
        operation
        for operation in value["construction_operations"]
        if operation["operation_id"] == "op_fixture_close_reserved"
    )
    close_reserved["input_frontier_ids"] = ["frontier_fixture_reattached"]
    close_event = next(
        event
        for event in value["construction_sequence"]
        if event["event_id"] == "ev_fixture_close_reserved"
    )
    close_event["sequence_index"] = 6
    close_transition = next(
        transition
        for transition in value["frontier_transitions"]
        if transition["frontier_transition_id"] == "ftrans_fixture_close_reserved"
    )
    close_transition["transition_index"] = 5
    close_transition["after_event_index"] = 6
    close_transition["input_frontier_ids"] = ["frontier_fixture_reattached"]

    cut_before = _operation(
        "op_fixture_cut_before_reattach",
        "CUT_YARN",
        [],
        [],
        "deriv_fixture_cut_before_reattach",
    )
    cut_before["input_yarn_ids"] = ["yarn_fixture_main"]
    attach = _operation(
        "op_fixture_reattach",
        "ATTACH",
        ["frontier_fixture_reserved"],
        ["frontier_fixture_reattached"],
        "deriv_fixture_reattach",
        attachments=[top_b],
    )
    attach["output_yarn_ids"] = ["yarn_fixture_main"]
    cut_after = _operation(
        "op_fixture_cut_after_reattach",
        "CUT_YARN",
        [],
        [],
        "deriv_fixture_cut_after_reattach",
    )
    cut_after["input_yarn_ids"] = ["yarn_fixture_main"]
    value["construction_operations"].extend([cut_before, attach, cut_after])
    value["construction_sequence"].extend(
        [
            {
                "event_id": "ev_fixture_cut_before_reattach",
                "sequence_index": 4,
                "subject_ref": {
                    "entity_type": "CONSTRUCTION_OPERATION",
                    "operation_id": "op_fixture_cut_before_reattach",
                },
                "active_yarn_id_before": "yarn_fixture_main",
                "active_yarn_id_after": None,
                "active_color_id_before": "color_fixture_natural",
                "active_color_id_after": None,
                "frontier_transition_ids": [],
            },
            {
                "event_id": "ev_fixture_reattach",
                "sequence_index": 5,
                "subject_ref": {
                    "entity_type": "CONSTRUCTION_OPERATION",
                    "operation_id": "op_fixture_reattach",
                },
                "active_yarn_id_before": None,
                "active_yarn_id_after": "yarn_fixture_main",
                "active_color_id_before": None,
                "active_color_id_after": "color_fixture_natural",
                "frontier_transition_ids": ["ftrans_fixture_reattach"],
            },
            {
                "event_id": "ev_fixture_cut_after_reattach",
                "sequence_index": 7,
                "subject_ref": {
                    "entity_type": "CONSTRUCTION_OPERATION",
                    "operation_id": "op_fixture_cut_after_reattach",
                },
                "active_yarn_id_before": "yarn_fixture_main",
                "active_yarn_id_after": None,
                "active_color_id_before": "color_fixture_natural",
                "active_color_id_after": None,
                "frontier_transition_ids": [],
            },
        ]
    )
    value["frontiers"].append(
        _frontier(
            "frontier_fixture_reattached",
            "ftrans_fixture_reattach",
            [top_b],
            "ACTIVE",
        )
    )
    reattach_transition = _transition(
        "ftrans_fixture_reattach",
        4,
        "op_fixture_reattach",
        "REATTACH",
        ["frontier_fixture_reserved"],
        ["frontier_fixture_reattached"],
    )
    reattach_transition["after_event_index"] = 5
    value["frontier_transitions"].append(reattach_transition)
    value["derivations"].extend(
        [
            _derivation("deriv_fixture_cut_before_reattach", "op_fixture_cut_before_reattach"),
            _derivation("deriv_fixture_reattach", "op_fixture_reattach"),
            _derivation("deriv_fixture_cut_after_reattach", "op_fixture_cut_after_reattach"),
        ]
    )
    value["yarn_paths"][0]["segments"] = [
        {
            "yarn_segment_id": "yseg_fixture_before_reattach",
            "start_operation_id": "op_fixture_magic_ring",
            "start_operation_type": "MAGIC_RING",
            "event_ids": [
                "ev_fixture_sc_001",
                "ev_fixture_reserve",
                "ev_fixture_close_active",
            ],
            "end_operation_id": "op_fixture_cut_before_reattach",
            "end_operation_type": "CUT_YARN",
        },
        {
            "yarn_segment_id": "yseg_fixture_after_reattach",
            "start_operation_id": "op_fixture_reattach",
            "start_operation_type": "ATTACH",
            "event_ids": ["ev_fixture_close_reserved"],
            "end_operation_id": "op_fixture_cut_after_reattach",
            "end_operation_type": "CUT_YARN",
        },
    ]
    return value


@pytest.fixture
def material_profile() -> dict[str, Any]:
    return load_fixture("material-profile.minimal.valid.json")


@pytest.fixture
def design_spec(material_profile: dict[str, Any]) -> dict[str, Any]:
    value = load_fixture("design-spec.analytic-sphere.valid.json")
    value["material_profile"] = {
        "binding_type": "INLINE",
        "profile": deepcopy(material_profile),
    }
    return value


@pytest.fixture
def closed_ir() -> dict[str, Any]:
    return make_closed_ir()
