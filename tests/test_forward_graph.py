from copy import deepcopy
from dataclasses import FrozenInstanceError

import pytest
from conftest import make_increase_ir, resolved_artifacts, resolved_validator
from ring_fixtures import make_multi_ring_ir

from crochet_ai.canonical import jcs_bytes
from crochet_ai.forward_graph import ForwardGraphError, lower_forward_graph
from crochet_ai.physical_projection import PhysicalSemanticProjection


def lower(value=None, material=None):
    source = make_multi_ring_ir() if value is None else value
    _, resolved_material = resolved_artifacts()
    chosen_material = resolved_material if material is None else material
    projection = PhysicalSemanticProjection(
        source,
        chosen_material,
        validator=resolved_validator(),
    )
    graph = lower_forward_graph(
        projection,
        chosen_material,
        "tension_fixture_default",
        "RELAXED_UNSTUFFED",
        validator=resolved_validator(),
    )
    return projection, graph


def test_ring_lowers_to_stable_attachment_course_wale_and_yarn_edges() -> None:
    projection, graph = lower()

    assert graph.projection_sha256 == projection.sha256
    assert len(graph.nodes) == 12
    assert len(graph.material_responses) == 6
    assert len(graph.shaping_groups) == 6
    assert all(group.shaping == "PLAIN" for group in graph.shaping_groups)
    assert {item.effective_stitch_pitch_mm for item in graph.material_responses} == {4}
    assert {item.effective_course_pitch_mm for item in graph.material_responses} == {3.5}
    assert len([edge for edge in graph.edges if edge.edge_type == "WALE"]) == 6
    assert len([edge for edge in graph.edges if edge.edge_type == "COURSE"]) == 6
    assert not [edge for edge in graph.edges if edge.edge_type == "YARN_PATH"]
    assert len(graph.yarn_path_links) == 5
    assert [item.operation_type for item in graph.construction_operations] == [
        "MAGIC_RING",
        "CLOSE",
    ]
    assert [item.sequence_index for item in graph.construction_operations] == [0, 7]
    ring_boundary, close_boundary = graph.frontier_boundaries
    assert ring_boundary.attachment_location_ids == tuple(f"loc_ring_{i}" for i in range(6))
    assert close_boundary.attachment_location_ids == tuple(f"loc_top_{i}" for i in range(6))
    assert ring_boundary.frontier_transition_id == graph.construction_operations[
        0
    ].frontier_transition_ids[0]
    assert close_boundary.frontier_transition_id == graph.construction_operations[
        1
    ].frontier_transition_ids[0]
    node_ids = {node.attachment_location_id for node in graph.nodes}
    assert all(
        edge.source_location_id in node_ids and edge.target_location_id in node_ids
        for edge in graph.edges
    )
    assert graph.nodes == tuple(sorted(graph.nodes, key=lambda node: node.attachment_location_id))
    assert graph.edges == tuple(
        sorted(
            graph.edges,
            key=lambda edge: (
                edge.edge_type,
                edge.course_id,
                edge.stitch_id or "",
                edge.source_location_id,
                edge.target_location_id,
            ),
        )
    )
    with pytest.raises(FrozenInstanceError):
        graph.material_responses[0].effective_stitch_pitch_mm = 100


def test_increase_keeps_shaping_arity_and_all_wale_incidences() -> None:
    projection, graph = lower(make_increase_ir())

    projected = projection.to_dict()
    operation_events = [
        event for event in projected["construction_sequence"]
        if event["subject_ref"]["entity_type"] == "CONSTRUCTION_OPERATION"
    ]
    assert [item.sequence_index for item in graph.construction_operations] == [
        event["sequence_index"] for event in operation_events
    ]

    group, = graph.shaping_groups
    assert group.shaping == "INCREASE"
    assert group.base_arity == 1
    assert group.top_arity == 2
    assert group.base_attachment_location_ids == ("loc_fixture_magic_anchor",)
    assert group.top_attachment_location_ids == (
        "loc_fixture_stitch_top",
        "loc_fixture_stitch_top_2",
    )
    incidences = [edge for edge in graph.edges if edge.edge_type == "WALE"]
    assert {
        (edge.source_location_id, edge.target_location_id) for edge in incidences
    } == {
        ("loc_fixture_magic_anchor", "loc_fixture_stitch_top"),
        ("loc_fixture_magic_anchor", "loc_fixture_stitch_top_2"),
    }
    course_links = [edge for edge in graph.edges if edge.edge_type == "COURSE"]
    assert {
        (edge.source_location_id, edge.target_location_id) for edge in course_links
    } == {
        ("loc_fixture_stitch_top", "loc_fixture_stitch_top_2"),
        ("loc_fixture_stitch_top_2", "loc_fixture_stitch_top"),
    }
    assert graph.yarn_path_links == ()


def test_entity_table_order_and_excluded_target_provenance_do_not_change_graph() -> None:
    source = make_multi_ring_ir()
    original_projection, original = lower(source)

    reordered = deepcopy(source)
    for table in reordered.values():
        if isinstance(table, list) and table and isinstance(table[0], dict):
            table.reverse()
    reordered_projection, reordered_graph = lower(reordered)
    assert reordered_projection.canonical_bytes == original_projection.canonical_bytes
    assert reordered_graph == original

    target_changed = deepcopy(source)
    target_changed["provenance"]["input_artifacts"] = [
        {
            "artifact_id": "asset_changed",
            "artifact_role": "TARGET_GEOMETRY",
            "sha256": "f" * 64,
        }
    ]
    target_projection, target_graph = lower(target_changed)
    assert target_projection.canonical_bytes == original_projection.canonical_bytes
    assert target_graph == original


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("ring_transition", "operation_transition_mismatch"),
        ("ring_sites", "operation_boundary_mismatch"),
        ("close_retired", "operation_boundary_mismatch"),
    ],
)
def test_inconsistent_projected_operation_boundary_fails_closed(
    mutation: str, reason: str
) -> None:
    _, material = resolved_artifacts()
    projection = PhysicalSemanticProjection(
        make_multi_ring_ir(), material, validator=resolved_validator()
    )
    value = projection.to_dict()
    ring_event = next(
        event for event in value["construction_sequence"]
        if event["subject_ref"].get("operation_id") == "op_fixture_magic_ring"
    )
    ring_transition = next(
        transition for transition in value["frontier_transitions"]
        if transition["frontier_transition_id"] == ring_event["frontier_transition_ids"][0]
    )
    if mutation == "ring_transition":
        ring_transition["transition_type"] = "CLOSE"
    elif mutation == "ring_sites":
        ring_transition["created_attachment_location_ids"] = ["loc_ring_0"]
    else:
        close_transition = next(
            transition for transition in value["frontier_transitions"]
            if transition["transition_type"] == "CLOSE"
        )
        close_transition["retired_attachment_location_ids"] = ["loc_top_0"]
    forged = object.__new__(PhysicalSemanticProjection)
    object.__setattr__(forged, "canonical_bytes", jcs_bytes(value))
    object.__setattr__(forged, "sha256", projection.sha256)
    with pytest.raises(ForwardGraphError, match=reason):
        lower_forward_graph(
            forged,
            material,
            "tension_fixture_default",
            "RELAXED_UNSTUFFED",
            validator=resolved_validator(),
        )


def test_material_binding_mismatch_and_missing_exact_response_fail_closed() -> None:
    _, material = resolved_artifacts()
    other_material = deepcopy(material)
    other_material["yarn"]["description"] = "Different content identity"
    projection = PhysicalSemanticProjection(
        make_multi_ring_ir(), material, validator=resolved_validator()
    )
    with pytest.raises(ForwardGraphError, match="material_binding_mismatch"):
        lower_forward_graph(
            projection,
            other_material,
            "tension_fixture_default",
            "RELAXED_UNSTUFFED",
            validator=resolved_validator(),
        )

    with pytest.raises(ForwardGraphError, match="material_response_unresolved"):
        lower_forward_graph(
            projection,
            material,
            "unmeasured_tension",
            "RELAXED_UNSTUFFED",
            validator=resolved_validator(),
        )


def test_wrong_input_types_and_target_payload_are_rejected() -> None:
    _, material = resolved_artifacts()
    with pytest.raises(TypeError, match="projection"):
        lower_forward_graph(
            object(),
            material,
            "tension_fixture_default",
            "RELAXED_UNSTUFFED",
            validator=resolved_validator(),
        )  # type: ignore[arg-type]

    projection = PhysicalSemanticProjection(
        make_multi_ring_ir(), material, validator=resolved_validator()
    )
    with pytest.raises(TypeError, match="material"):
        lower_forward_graph(
            projection,
            object(),  # type: ignore[arg-type]
            "tension_fixture_default",
            "RELAXED_UNSTUFFED",
            validator=resolved_validator(),
        )
    with pytest.raises(TypeError):
        lower_forward_graph(
            projection,
            material,
            "tension_fixture_default",
            "RELAXED_UNSTUFFED",
            validator=resolved_validator(),
            target_mesh={},  # type: ignore[call-arg]
        )


def test_material_semantics_are_validated_before_resolution() -> None:
    _, material = resolved_artifacts()
    invalid = deepcopy(material)
    invalid["calibration_responses"][0]["effective_gauge"]["effective_stitch_pitch_mm"] = 99
    projection = PhysicalSemanticProjection(
        make_multi_ring_ir(), material, validator=resolved_validator()
    )
    with pytest.raises(ForwardGraphError, match="invalid_material_profile"):
        lower_forward_graph(
            projection,
            invalid,
            "tension_fixture_default",
            "RELAXED_UNSTUFFED",
            validator=resolved_validator(),
        )
