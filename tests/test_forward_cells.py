from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from typing import Any

import pytest

from crochet_ai.canonical import jcs_bytes
from crochet_ai.forward_cells import (
    ForwardSurfaceCellsError,
    build_forward_surface_cells,
)
from crochet_ai.forward_graph import ForwardGraph, GraphEdge, GraphNode, StitchShapingGroup
from crochet_ai.physical_projection import PhysicalSemanticProjection


def _handbuilt_two_course_fixture(
    count: int = 4, course_count: int = 2
) -> tuple[PhysicalSemanticProjection, ForwardGraph]:
    """A small independent topology fixture, not lowered from solver output."""
    assert count in {2, 3, 4}
    assert course_count in {2, 3}
    anchors = [f"anchor_{index}" for index in range(count)]
    loop_names = [
        ["lower_z", "lower_a", "lower_m", "lower_b"],
        ["upper_q", "upper_c", "upper_x", "upper_d"],
        ["last_p", "last_e", "last_r", "last_f"],
    ]
    loops = [loop[:count] for loop in loop_names[:course_count]]
    course_ids = ["course_first", "course_next", "course_last"][:course_count]
    courses: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    stitches: list[dict[str, Any]] = []
    locations = [
        {
            "attachment_location_id": identifier,
            "location_type": "MAGIC_RING_ANCHOR",
        }
        for identifier in anchors
    ]
    groups: list[StitchShapingGroup] = []
    nodes = [GraphNode(identifier, "MAGIC_RING_ANCHOR") for identifier in anchors]
    for course_index, (course_id, tops) in enumerate(zip(course_ids, loops, strict=True)):
        event_ids: list[str] = []
        for ordinal, top_id in enumerate(tops):
            stitch_id = f"stitch_{course_index}_{ordinal}"
            event_id = f"event_{course_index}_{ordinal}"
            base_id = anchors[ordinal] if course_index == 0 else loops[course_index - 1][ordinal]
            event_ids.append(event_id)
            events.append(
                {
                    "event_id": event_id,
                    "sequence_index": len(events),
                    "subject_ref": {"entity_type": "STITCH", "stitch_id": stitch_id},
                }
            )
            stitches.append(
                {
                    "stitch_id": stitch_id,
                    "course_id": course_id,
                    "stitch_type": "SINGLE_CROCHET",
                    "shaping": "PLAIN",
                    "base_attachment_location_ids": [base_id],
                    "top_attachment_location_ids": [top_id],
                }
            )
            locations.append({"attachment_location_id": top_id, "location_type": "TOP_LOOP"})
            nodes.append(GraphNode(top_id, "TOP_LOOP"))
            groups.append(StitchShapingGroup(stitch_id, "PLAIN", (base_id,), (top_id,), 1, 1))
        courses.append(
            {
                "course_id": course_id,
                "course_form": "CYCLIC",
                "work_direction": "CLOCKWISE",
                "member_event_ids": event_ids,
            }
        )

    value: dict[str, Any] = {
        "profile": "FORWARD_PHYSICAL_SEMANTICS_V1",
        "course_order": course_ids,
        "courses": courses,
        "construction_sequence": events,
        "stitches": stitches,
        "attachment_locations": locations,
    }
    projection = _projection(value)
    edges: list[GraphEdge] = []
    for stitch in stitches:
        edges.append(
            GraphEdge(
                "WALE",
                stitch["base_attachment_location_ids"][0],
                stitch["top_attachment_location_ids"][0],
                stitch["course_id"],
                stitch["stitch_id"],
            )
        )
    for course, tops in zip(courses, loops, strict=True):
        for left, right in zip(tops, (*tops[1:], tops[0]), strict=True):
            edges.append(GraphEdge("COURSE", left, right, course["course_id"]))
    graph = ForwardGraph(
        projection.sha256,
        "b" * 64,
        tuple(nodes),
        tuple(groups),
        tuple(edges),
        (),
        (),
        (),
        (),
    )
    return projection, graph


def _change_course_bases(
    projection: PhysicalSemanticProjection,
    graph: ForwardGraph,
    course_id: str,
    bases: list[str],
) -> tuple[PhysicalSemanticProjection, ForwardGraph]:
    value = projection.to_dict()
    course_stitches = [
        stitch for stitch in value["stitches"] if stitch["course_id"] == course_id
    ]
    groups = {group.stitch_id: group for group in graph.shaping_groups}
    for stitch, base_id in zip(course_stitches, bases, strict=True):
        stitch["base_attachment_location_ids"] = [base_id]
        groups[stitch["stitch_id"]] = replace(
            groups[stitch["stitch_id"]], base_attachment_location_ids=(base_id,)
        )
    new_graph_groups = tuple(groups.values())
    stitch_by_id = {stitch["stitch_id"]: stitch for stitch in value["stitches"]}
    wale_edges = [
        GraphEdge(
            "WALE",
            group.base_attachment_location_ids[0],
            group.top_attachment_location_ids[0],
            stitch_by_id[group.stitch_id]["course_id"],
            group.stitch_id,
        )
        for group in new_graph_groups
    ]
    course_edges = [edge for edge in graph.edges if edge.edge_type == "COURSE"]
    changed_projection, changed_graph = _with_value(projection, graph, value)
    return changed_projection, replace(
        changed_graph, shaping_groups=new_graph_groups, edges=tuple(wale_edges + course_edges)
    )


def _projection(value: dict[str, Any]) -> PhysicalSemanticProjection:
    encoded = jcs_bytes(value)
    digest = sha256(b"Crochet.AI\0FORWARD_PHYSICAL_SEMANTICS_V1\0" + encoded).hexdigest()
    result = object.__new__(PhysicalSemanticProjection)
    object.__setattr__(result, "canonical_bytes", encoded)
    object.__setattr__(result, "sha256", digest)
    return result


def _with_value(
    projection: PhysicalSemanticProjection, graph: ForwardGraph, value: dict[str, Any]
) -> tuple[PhysicalSemanticProjection, ForwardGraph]:
    changed_projection = _projection(value)
    return changed_projection, replace(graph, projection_sha256=changed_projection.sha256)


def test_handbuilt_two_course_strip_has_ordered_oriented_quads_and_hash_binding() -> None:
    projection, graph = _handbuilt_two_course_fixture()
    result = build_forward_surface_cells(projection, graph)
    assert result.status == "EXPERIMENTAL_TOPOLOGY"
    assert result.projection_sha256 == projection.sha256
    assert result.material_sha256 == graph.material_sha256
    assert result.lower_boundary_location_ids == (
        "lower_z",
        "lower_a",
        "lower_m",
        "lower_b",
    )
    assert result.upper_boundary_location_ids == (
        "upper_q",
        "upper_c",
        "upper_x",
        "upper_d",
    )
    assert b'"lower_boundary_location_ids"' in result.canonical_bytes
    assert b'"upper_boundary_location_ids"' in result.canonical_bytes
    assert [cell.ordinal for cell in result.cells] == [0, 1, 2, 3]
    assert [cell.attachment_location_ids for cell in result.cells] == [
        ("lower_z", "lower_a", "upper_c", "upper_q"),
        ("lower_a", "lower_m", "upper_x", "upper_c"),
        ("lower_m", "lower_b", "upper_d", "upper_x"),
        ("lower_b", "lower_z", "upper_q", "upper_d"),
    ]
    again = build_forward_surface_cells(projection, graph)
    assert result.canonical_bytes == again.canonical_bytes
    assert result.sha256 == again.sha256


def test_rotation_and_twisted_wale_mapping_are_rejected_without_normalization() -> None:
    projection, graph = _handbuilt_two_course_fixture()
    # A one-place phase shift preserves a bijection and cyclic adjacency, but
    # the strip profile deliberately requires exact declared ordinal alignment.
    shifted_projection, shifted_graph = _change_course_bases(
        projection,
        graph,
        "course_next",
        ["lower_a", "lower_m", "lower_b", "lower_z"],
    )
    with pytest.raises(ForwardSurfaceCellsError, match="course_phase_mismatch"):
        build_forward_surface_cells(shifted_projection, shifted_graph)


@pytest.mark.parametrize("case", ["duplicate", "missing", "wrong"])
def test_course_and_wale_graph_edges_must_match_exact_projection(case: str) -> None:
    projection, graph = _handbuilt_two_course_fixture()
    if case == "duplicate":
        graph = replace(graph, edges=(*graph.edges, graph.edges[0]))
    elif case == "missing":
        graph = replace(graph, edges=graph.edges[1:])
    else:
        wrong = replace(graph.edges[0], target_location_id="upper_d")
        graph = replace(graph, edges=(wrong, *graph.edges[1:]))
    with pytest.raises(ForwardSurfaceCellsError, match="graph_edge_set_mismatch"):
        build_forward_surface_cells(projection, graph)


def test_extra_graph_node_is_rejected() -> None:
    projection, graph = _handbuilt_two_course_fixture()
    graph = replace(graph, nodes=(*graph.nodes, GraphNode("orphan", "TOP_LOOP")))
    with pytest.raises(ForwardSurfaceCellsError, match="graph_node_set_mismatch"):
        build_forward_surface_cells(projection, graph)


def test_shaped_stitch_is_rejected() -> None:
    projection, graph = _handbuilt_two_course_fixture()
    value = projection.to_dict()
    value["stitches"][0]["shaping"] = "INCREASE"
    changed_projection, changed_graph = _with_value(projection, graph, value)
    with pytest.raises(ForwardSurfaceCellsError, match="unsupported_stitch"):
        build_forward_surface_cells(changed_projection, changed_graph)


def test_single_course_has_no_surface_pair_and_is_rejected() -> None:
    projection, graph = _handbuilt_two_course_fixture()
    value = projection.to_dict()
    value["course_order"] = ["course_first"]
    value["courses"] = value["courses"][:1]
    value["construction_sequence"] = value["construction_sequence"][:4]
    value["stitches"] = value["stitches"][:4]
    locations = value["attachment_locations"]
    keep = {f"anchor_{index}" for index in range(4)} | {
        f"lower_{suffix}" for suffix in ("z", "a", "m", "b")
    }
    value["attachment_locations"] = [
        location for location in locations if location["attachment_location_id"] in keep
    ]
    changed_projection = _projection(value)
    node_ids = keep
    graph = replace(
        graph,
        projection_sha256=changed_projection.sha256,
        nodes=tuple(node for node in graph.nodes if node.attachment_location_id in node_ids),
        shaping_groups=graph.shaping_groups[:4],
        edges=tuple(edge for edge in graph.edges if edge.course_id == "course_first"),
    )
    with pytest.raises(ForwardSurfaceCellsError, match="adjacent_course_pair_missing"):
        build_forward_surface_cells(changed_projection, graph)


def test_three_loop_surface_is_supported_and_two_loop_surface_is_rejected() -> None:
    projection, graph = _handbuilt_two_course_fixture(count=3)
    result = build_forward_surface_cells(projection, graph)
    assert len(result.cells) == 3
    too_small_projection, too_small_graph = _handbuilt_two_course_fixture(count=2)
    with pytest.raises(ForwardSurfaceCellsError, match="course_too_small"):
        build_forward_surface_cells(too_small_projection, too_small_graph)


def test_duplicate_and_older_course_bases_are_rejected() -> None:
    projection, graph = _handbuilt_two_course_fixture()
    duplicate_projection, duplicate_graph = _change_course_bases(
        projection, graph, "course_next", ["lower_z", "lower_z", "lower_m", "lower_b"]
    )
    with pytest.raises(ForwardSurfaceCellsError, match="duplicate_course_base"):
        build_forward_surface_cells(duplicate_projection, duplicate_graph)

    projection, graph = _handbuilt_two_course_fixture(course_count=3)
    older_projection, older_graph = _change_course_bases(
        projection, graph, "course_last", ["lower_z", "lower_a", "lower_m", "lower_b"]
    )
    with pytest.raises(ForwardSurfaceCellsError, match="course_base_set_mismatch"):
        build_forward_surface_cells(older_projection, older_graph)


def test_reversed_non_cycle_wale_mapping_is_rejected() -> None:
    projection, graph = _handbuilt_two_course_fixture()
    reversed_projection, reversed_graph = _change_course_bases(
        projection, graph, "course_next", ["lower_z", "lower_b", "lower_m", "lower_a"]
    )
    with pytest.raises(ForwardSurfaceCellsError, match="course_adjacency_mismatch"):
        build_forward_surface_cells(reversed_projection, reversed_graph)


def test_opposite_adjacent_work_directions_are_rejected() -> None:
    projection, graph = _handbuilt_two_course_fixture()
    value = projection.to_dict()
    value["courses"][1]["work_direction"] = "COUNTERCLOCKWISE"
    changed_projection, changed_graph = _with_value(projection, graph, value)
    with pytest.raises(ForwardSurfaceCellsError, match="course_direction_mismatch"):
        build_forward_surface_cells(changed_projection, changed_graph)
