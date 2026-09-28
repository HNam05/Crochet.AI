from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from math import dist, pi, sin
from typing import Any

import pytest
from conftest import resolved_artifacts, resolved_validator
from ring_fixtures import make_multi_ring_ir

from crochet_ai.canonical import jcs_bytes
from crochet_ai.forward_graph import (
    ForwardGraph,
    GraphNode,
    StitchMaterialResponse,
    StitchShapingGroup,
    lower_forward_graph,
)
from crochet_ai.forward_initialization import (
    ForwardInitialization,
    ForwardInitializationError,
    initialize_forward_graph,
)
from crochet_ai.forward_inputs import ForwardInputs, admit_forward_inputs
from crochet_ai.physical_projection import PhysicalSemanticProjection


def _inputs(max_vertices: int = 100) -> ForwardInputs:
    loading = {
        "schema_version": "1.0.0",
        "loading_profile_id": "loading-unloaded-v1",
        "state": "UNLOADED_UNPRESSURIZED",
    }
    model = {
        "schema_version": "1.0.0",
        "model_profile_id": "f0-stretch-hypothesis-v1",
        "status": "HYPOTHESIS",
        "source_provenance_id": "initialization-study-01",
        "stiffness_course_n_per_mm": 0.8,
        "stiffness_wale_n_per_mm": 0.4,
    }
    units = {
        "force_residual_n": "N",
        "position_step_mm": "mm",
        "relative_energy_change": "dimensionless",
        "contact_penetration_mm": "mm",
        "volume_orientation_epsilon_mm3": "mm^3",
        "mode_equivalence_rms_mm": "mm",
    }
    config = {
        "schema_version": "1.0.0",
        "config_id": "initialization-run-v1",
        "model_version": "F0_STRETCH_PROTOTYPE",
        "work_budgets": {
            "max_initializations": 1,
            "max_initialization_vertices": max_vertices,
            "max_optimizer_iterations": 10,
            "max_energy_evaluations": 20,
            "max_line_search_trials": 10,
            "max_linear_iterations": 30,
            "max_contact_pairs_evaluated": 40,
        },
        "tolerances": {
            name: {
                "value": 0.01,
                "unit": unit,
                "rationale": f"Experimental fixture threshold for {name}.",
                "owner": "forward-model",
                "validation_path_id": f"fixture-{name}",
            }
            for name, unit in units.items()
        },
    }
    return admit_forward_inputs(loading, model, config)


def _actual(value: dict[str, Any] | None = None) -> tuple[PhysicalSemanticProjection, ForwardGraph]:
    source = make_multi_ring_ir() if value is None else value
    _, material = resolved_artifacts()
    projection = PhysicalSemanticProjection(source, material, validator=resolved_validator())
    graph = lower_forward_graph(
        projection,
        material,
        "tension_fixture_default",
        "RELAXED_UNSTUFFED",
        validator=resolved_validator(),
    )
    return projection, graph


def _synthetic(
    direction: str = "CLOCKWISE", *, n: int = 4, course_count: int = 2,
    later_direction: str | None = None,
) -> tuple[PhysicalSemanticProjection, ForwardGraph]:
    anchors = [f"ring_{index}" for index in range(n)]
    ordered_tops = ["loop_z", "loop_a", "loop_m", "loop_b"][:n]
    course_ids = ["course_first", "course_second"] + [
        f"course_{index + 1}" for index in range(2, course_count)
    ]
    course_stitches = [
        [f"s{course_index + 1}_{index}" for index in range(n)]
        for course_index in range(course_count)
    ]
    course_tops = [ordered_tops] + [
        [
            f"next_{name}" if course_index == 1 else f"next_{course_index}_{name}"
            for name in ordered_tops
        ]
        for course_index in range(1, course_count)
    ]
    courses: list[dict[str, Any]] = []
    sequence: list[dict[str, Any]] = []
    stitches: list[dict[str, Any]] = []
    locations = [
        {
            "attachment_location_id": anchor,
            "location_type": "MAGIC_RING_ANCHOR",
            "producer_ref": {"entity_type": "CONSTRUCTION_OPERATION", "operation_id": "ring_op"},
            "ordinal_within_producer": ordinal,
        }
        for ordinal, anchor in enumerate(anchors)
    ]
    groups: list[StitchShapingGroup] = []
    responses: list[StitchMaterialResponse] = []
    nodes = [GraphNode(anchor, "MAGIC_RING_ANCHOR") for anchor in anchors]
    for course_index, course_id in enumerate(course_ids):
        event_ids = [f"event_{sid}" for sid in course_stitches[course_index]]
        course_direction = (
            later_direction if course_index > 0 and later_direction is not None else direction
        )
        courses.append(
            {
                "course_id": course_id,
                "course_form": "CYCLIC",
                "work_direction": course_direction,
                "member_event_ids": event_ids,
            }
        )
        for ordinal, (stitch_id, event_id, top_id) in enumerate(
            zip(course_stitches[course_index], event_ids, course_tops[course_index], strict=True)
        ):
            base_id = (
                anchors[ordinal]
                if course_index == 0
                else course_tops[course_index - 1][ordinal]
            )
            stitches.append(
                {"stitch_id": stitch_id, "course_id": course_id, "stitch_type": "SINGLE_CROCHET"}
            )
            sequence.append(
                {
                    "event_id": event_id,
                    "subject_ref": {"entity_type": "STITCH", "stitch_id": stitch_id},
                }
            )
            locations.append(
                {
                    "attachment_location_id": top_id,
                    "location_type": "TOP_LOOP",
                    "producer_ref": {"entity_type": "STITCH", "stitch_id": stitch_id},
                }
            )
            nodes.append(GraphNode(top_id, "TOP_LOOP"))
            groups.append(StitchShapingGroup(stitch_id, "PLAIN", (base_id,), (top_id,), 1, 1))
            responses.append(
                StitchMaterialResponse(
                    stitch_id,
                    f"response_{stitch_id}",
                    2.0,
                    1.5 if course_index == 1 else 1.0,
                    0.1,
                    0.1,
                )
            )

    projected: dict[str, Any] = {
        "profile": "FORWARD_PHYSICAL_SEMANTICS_V1",
        "course_order": course_ids,
        "courses": courses,
        "construction_sequence": sequence,
        "stitches": stitches,
        "attachment_locations": locations,
        "construction_operations": [
            {
                "operation_id": "ring_op",
                "operation_type": "MAGIC_RING",
                "attachment_location_ids": anchors,
            }
        ],
    }
    canonical = jcs_bytes(projected)
    projection_hash = sha256(b"Crochet.AI\0FORWARD_PHYSICAL_SEMANTICS_V1\0" + canonical).hexdigest()
    projection = object.__new__(PhysicalSemanticProjection)
    object.__setattr__(projection, "canonical_bytes", canonical)
    object.__setattr__(projection, "sha256", projection_hash)
    graph = ForwardGraph(
        projection_hash,
        "b" * 64,
        tuple(nodes),
        tuple(groups),
        (),
        (),
        (),
        (),
        tuple(responses),
    )
    return projection, graph


def _with_course_bases(graph: ForwardGraph, course_index: int, bases: list[str]) -> ForwardGraph:
    course_stitch_prefix = f"s{course_index + 1}_"
    course_groups = [
        group for group in graph.shaping_groups if group.stitch_id.startswith(course_stitch_prefix)
    ]
    assert len(course_groups) == len(bases)
    replacements = {
        group.stitch_id: replace(group, base_attachment_location_ids=(base_id,))
        for group, base_id in zip(course_groups, bases, strict=True)
    }
    return replace(
        graph,
        shaping_groups=tuple(
            replacements.get(group.stitch_id, group) for group in graph.shaping_groups
        ),
    )


def _coordinates(result: ForwardInitialization) -> dict[str, tuple[float, float, float]]:
    return dict(result.coordinates_mm)


def test_handbuilt_ring_anchors_collapse_and_course_chords_match_gauge() -> None:
    projection, graph = _actual()
    result = initialize_forward_graph(projection, graph, _inputs())
    coordinates = _coordinates(result)
    projected = projection.to_dict()
    ring = next(
        operation
        for operation in projected["construction_operations"]
        if operation["operation_type"] == "MAGIC_RING"
    )
    anchors = [
        node.attachment_location_id
        for node in graph.nodes
        if node.location_type == "MAGIC_RING_ANCHOR"
    ]
    assert result.status == "EXPERIMENTAL_INITIALIZATION"
    assert result.anchor_location_groups == (tuple(ring["attachment_location_ids"]),)
    assert set(result.anchor_location_groups[0]) == set(anchors)
    assert {coordinates[anchor] for anchor in anchors} == {(0.0, 0.0, 0.0)}
    top_ids = [
        node.attachment_location_id for node in graph.nodes if node.location_type == "TOP_LOOP"
    ]
    assert len(top_ids) == 6
    for left, right in zip(top_ids, top_ids[1:] + top_ids[:1], strict=True):
        assert dist(coordinates[left], coordinates[right]) == pytest.approx(4.0, abs=1e-12)


def test_ring_anchor_group_preserves_operation_site_order_past_lexical_boundary() -> None:
    projection, graph = _actual(make_multi_ring_ir(count=11))
    result = initialize_forward_graph(projection, graph, _inputs())
    projected = projection.to_dict()
    ring = next(
        operation
        for operation in projected["construction_operations"]
        if operation["operation_type"] == "MAGIC_RING"
    )
    assert result.anchor_location_groups == (tuple(ring["attachment_location_ids"]),)
    assert result.anchor_location_groups[0].index("loc_ring_2") < result.anchor_location_groups[
        0
    ].index("loc_ring_10")


def test_two_course_polygon_uses_declared_order_and_axial_course_pitch() -> None:
    projection, graph = _synthetic()
    result = initialize_forward_graph(projection, graph, _inputs())
    coordinates = _coordinates(result)
    radius = 2.0 / (2.0 * sin(pi / 4))
    assert coordinates["loop_z"][0] == pytest.approx(radius)
    assert coordinates["loop_a"][1] < 0.0  # CLOCKWISE follows declared member order.
    assert {
        coordinates[f"next_{name}"][2] for name in ("loop_z", "loop_a", "loop_m", "loop_b")
    } == {1.5}
    for row in (("loop_z", "loop_a", "loop_m", "loop_b"),):
        for left, right in zip(row, row[1:] + row[:1], strict=True):
            assert dist(coordinates[left], coordinates[right]) == pytest.approx(2.0, abs=1e-12)


def test_three_course_polygon_advances_by_each_representable_course_pitch() -> None:
    projection, graph = _synthetic(course_count=3)
    result = initialize_forward_graph(projection, graph, _inputs())
    coordinates = _coordinates(result)

    third_course_z = {
        coordinates[f"next_2_{name}"][2]
        for name in ("loop_z", "loop_a", "loop_m", "loop_b")
    }
    assert third_course_z == {2.5}


def test_later_course_pitch_must_make_representable_axial_progress() -> None:
    projection, graph = _synthetic(course_count=3)
    third_course_stitches = {f"s3_{index}" for index in range(4)}
    graph = replace(
        graph,
        material_responses=tuple(
            replace(response, effective_course_pitch_mm=1e-16)
            if response.stitch_id in third_course_stitches
            else response
            for response in graph.material_responses
        ),
    )

    with pytest.raises(
        ForwardInitializationError, match=r"initialization\.axial_progress_unrepresentable"
    ):
        initialize_forward_graph(projection, graph, _inputs())


def test_later_course_pitch_must_not_overflow_axial_coordinate() -> None:
    projection, graph = _synthetic(course_count=3)
    later_course_stitches = {f"s{course}_{index}" for course in (2, 3) for index in range(4)}
    graph = replace(
        graph,
        material_responses=tuple(
            replace(response, effective_course_pitch_mm=1e308)
            if response.stitch_id in later_course_stitches
            else response
            for response in graph.material_responses
        ),
    )

    with pytest.raises(
        ForwardInitializationError, match=r"initialization\.axial_progress_unrepresentable"
    ):
        initialize_forward_graph(projection, graph, _inputs())


def test_work_direction_mirrors_polygon_and_initialization_is_byte_deterministic() -> None:
    projection, graph = _synthetic("CLOCKWISE")
    clockwise_a = initialize_forward_graph(projection, graph, _inputs())
    clockwise_b = initialize_forward_graph(projection, graph, _inputs())
    ccw_projection, ccw_graph = _synthetic("COUNTERCLOCKWISE")
    counterclockwise = initialize_forward_graph(ccw_projection, ccw_graph, _inputs())
    cw = _coordinates(clockwise_a)
    ccw = _coordinates(counterclockwise)
    assert clockwise_a.canonical_bytes == clockwise_b.canonical_bytes
    assert clockwise_a.sha256 == clockwise_b.sha256
    assert cw["loop_a"][1] == pytest.approx(-ccw["loop_a"][1])
    assert cw["loop_a"][0] == pytest.approx(ccw["loop_a"][0])


@pytest.mark.parametrize("case", ["phase_rotation", "reversal", "duplicate", "missing"])
def test_later_course_must_consume_previous_top_loops_in_ordinal_order(case: str) -> None:
    projection, graph = _synthetic()
    previous = ["loop_z", "loop_a", "loop_m", "loop_b"]
    if case == "phase_rotation":
        bases = previous[1:] + previous[:1]
    elif case == "reversal":
        bases = list(reversed(previous))
    elif case == "duplicate":
        bases = [previous[0], previous[0], *previous[2:]]
    else:
        bases = [*previous[:-1], "next_loop_b"]
    malformed = _with_course_bases(graph, 1, bases)
    with pytest.raises(ForwardInitializationError, match="wale_order_mismatch"):
        initialize_forward_graph(projection, malformed, _inputs())


def test_later_course_cannot_attach_to_an_older_course() -> None:
    projection, graph = _synthetic(course_count=3)
    third_course_bases = ["loop_z", "loop_a", "loop_m", "loop_b"]
    malformed = _with_course_bases(graph, 2, third_course_bases)
    with pytest.raises(ForwardInitializationError, match="wale_order_mismatch"):
        initialize_forward_graph(projection, malformed, _inputs())


def test_adjacent_courses_must_share_work_direction() -> None:
    projection, graph = _synthetic(later_direction="COUNTERCLOCKWISE")
    with pytest.raises(ForwardInitializationError, match="work_direction_inconsistent"):
        initialize_forward_graph(projection, graph, _inputs())


def test_excluded_target_provenance_does_not_change_initialization() -> None:
    source = make_multi_ring_ir()
    projection, graph = _actual(source)
    baseline = initialize_forward_graph(projection, graph, _inputs())
    changed = deepcopy(source)
    changed["provenance"]["input_artifacts"] = [
        {
            "artifact_id": "asset_target_changed",
            "artifact_role": "TARGET_GEOMETRY",
            "sha256": "f" * 64,
        }
    ]
    target_projection, target_graph = _actual(changed)
    altered = initialize_forward_graph(target_projection, target_graph, _inputs())
    assert altered.canonical_bytes == baseline.canonical_bytes
    assert altered.sha256 == baseline.sha256


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("nonuniform_stitch", "stitch_pitch_nonuniform"),
        ("nonuniform_course", "course_pitch_nonuniform"),
        ("missing_response", "material_response_coverage"),
        ("shaping", "unsupported_shaping"),
        ("small_course", "course_too_small"),
        ("vertex_budget", "vertex_budget_exhausted"),
        ("unknown_node", "location_set_mismatch"),
    ],
)
def test_unsupported_or_incomplete_initialization_fails_closed(case: str, reason: str) -> None:
    projection, graph = _synthetic(n=2 if case == "small_course" else 4)
    inputs = _inputs(max_vertices=2 if case == "vertex_budget" else 100)
    if case == "nonuniform_stitch":
        graph = replace(
            graph,
            material_responses=(
                graph.material_responses[0],
                *graph.material_responses[1:3],
                replace(graph.material_responses[3], effective_stitch_pitch_mm=2.5),
                *graph.material_responses[4:],
            ),
        )
    elif case == "nonuniform_course":
        graph = replace(
            graph,
            material_responses=(
                *graph.material_responses[:-1],
                replace(graph.material_responses[-1], effective_course_pitch_mm=1.8),
            ),
        )
    elif case == "missing_response":
        graph = replace(graph, material_responses=graph.material_responses[:-1])
    elif case == "shaping":
        graph = replace(
            graph,
            shaping_groups=(
                replace(graph.shaping_groups[0], shaping="INCREASE"),
                *graph.shaping_groups[1:],
            ),
        )
    elif case == "unknown_node":
        graph = replace(graph, nodes=(*graph.nodes, GraphNode("orphan", "TOP_LOOP")))
    with pytest.raises(ForwardInitializationError, match=reason):
        initialize_forward_graph(projection, graph, inputs)


def test_projection_mismatch_and_target_argument_are_rejected() -> None:
    projection, graph = _synthetic()
    mismatch = object.__new__(PhysicalSemanticProjection)
    object.__setattr__(mismatch, "canonical_bytes", projection.canonical_bytes)
    object.__setattr__(mismatch, "sha256", "d" * 64)
    with pytest.raises(ForwardInitializationError, match="projection_hash_mismatch"):
        initialize_forward_graph(mismatch, graph, _inputs())
    with pytest.raises(TypeError):
        initialize_forward_graph(projection, graph, _inputs(), target_mesh={})  # type: ignore[call-arg]
