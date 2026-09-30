from __future__ import annotations

import json
from dataclasses import replace

import pytest

from crochet_ai.target_mesh_decode import MESH_MEDIA_TYPE, decode_indexed_triangle_mesh
from crochet_ai.target_mesh_pair_relations import (
    MeshPairRelationsError,
    diagnose_indexed_triangle_mesh_pair_relations,
)
from crochet_ai.target_mesh_topology import diagnose_indexed_triangle_mesh

FRAME = "frame_pair_relations_test"
LIMITS = {
    "media_type": MESH_MEDIA_TYPE,
    "expected_coordinate_frame_id": FRAME,
    "max_bytes": 100_000,
    "max_vertices": 100,
    "max_faces": 100,
    "max_face_pairs_evaluated": 100,
}


def mesh_bytes(vertices: list[tuple[float, float, float]],
               faces: list[tuple[int, int, int]]) -> bytes:
    value = {
        "representation_version": "INDEXED_TRIANGLE_MESH_V1",
        "coordinate_system": {
            "length_unit": "MILLIMETER",
            "handedness": "RIGHT_HANDED",
            "coordinate_frame_id": FRAME,
        },
        "vertices": [{"position_mm": list(point)} for point in vertices],
        "faces": [{"vertex_indices": list(face)} for face in faces],
    }
    return json.dumps(value, separators=(",", ":")).encode()


def analyze(raw: bytes, **overrides: object):
    decoded = decode_indexed_triangle_mesh(
        raw,
        media_type=MESH_MEDIA_TYPE,
        expected_coordinate_frame_id=FRAME,
        max_bytes=LIMITS["max_bytes"],
        max_vertices=LIMITS["max_vertices"],
        max_faces=LIMITS["max_faces"],
    )
    topology = diagnose_indexed_triangle_mesh(
        raw,
        decoded,
        media_type=MESH_MEDIA_TYPE,
        expected_coordinate_frame_id=FRAME,
        max_bytes=LIMITS["max_bytes"],
        max_vertices=LIMITS["max_vertices"],
        max_faces=LIMITS["max_faces"],
    )
    report = diagnose_indexed_triangle_mesh_pair_relations(
        raw, decoded, topology, **(LIMITS | overrides)
    )
    return decoded, topology, report


def test_exact_intended_shared_edge_and_vertex_are_allowed() -> None:
    edge_raw = mesh_bytes(
        [(0, 0, 0), (2, 0, 0), (0, 2, 0), (1, -1, 0)],
        [(0, 1, 2), (1, 0, 3)],
    )
    _, _, edge = analyze(edge_raw)
    assert edge.relations[0].relation_kind == "SEGMENT"
    assert edge.relations[0].shared_indexed_vertex_count == 2
    assert edge.relations[0].intended_simplex_allowance == "SHARED_EDGE"
    assert not edge.relations[0].forbidden

    vertex_raw = mesh_bytes(
        [(0, 0, 0), (2, 0, 0), (0, 2, 0), (0, 0, 1), (0, -1, 1)],
        [(0, 1, 2), (0, 3, 4)],
    )
    _, _, vertex = analyze(vertex_raw)
    assert vertex.relations[0].relation_kind == "POINT"
    assert vertex.relations[0].shared_indexed_vertex_count == 1
    assert vertex.relations[0].intended_simplex_allowance == "SHARED_VERTEX"
    assert not vertex.relations[0].forbidden


def test_shared_edge_with_coplanar_area_overlap_is_forbidden() -> None:
    raw = mesh_bytes(
        [(0, 0, 0), (2, 0, 0), (0, 2, 0), (1, 1, 0)],
        [(0, 1, 2), (1, 0, 3)],
    )
    _, _, report = analyze(raw)
    relation = report.relations[0]
    assert relation.relation_kind == "COPLANAR_AREA"
    assert relation.coplanar
    assert relation.intended_simplex_allowance == "NONE"
    assert relation.forbidden


@pytest.mark.parametrize(
    "vertices,faces",
    [
        ([(0, 0, 0), (2, 0, 0), (0, 2, 0), (1, -1, -1), (1, 2, 1), (1, 0, 1)],
         [(0, 1, 2), (3, 4, 5)]),
        ([(0, 0, 0), (2, 0, 0), (0, 2, 0), (2, 0, 0), (3, -1, 0), (3, 1, 0)],
         [(0, 1, 2), (3, 4, 5)]),
        ([(0, 0, 0), (2, 0, 0), (0, 2, 0), (0, 0, 0), (2, 0, 0), (0, 2, 0)],
         [(0, 1, 2), (3, 4, 5)]),
    ],
)
def test_nonadjacent_crossing_touch_and_coincidence_are_forbidden(vertices, faces) -> None:
    _, _, report = analyze(mesh_bytes(vertices, faces))
    assert report.relations[0].relation_kind != "DISJOINT"
    assert report.relations[0].shared_indexed_vertex_count == 0
    assert report.relations[0].forbidden


def test_disjoint_pair_is_reported_without_forbidden_classification() -> None:
    raw = mesh_bytes(
        [(0, 0, 0), (1, 0, 0), (0, 1, 0),
         (0, 0, 2), (1, 0, 2), (0, 1, 2),
         (0, 0, 4), (1, 0, 4), (0, 1, 4)],
        [(0, 1, 2), (3, 4, 5), (6, 7, 8)],
    )
    _, _, report = analyze(raw)
    assert report.relations[0].relation_kind == "DISJOINT"
    assert not report.relations[0].forbidden


def test_large_rational_witnesses_are_encoded_without_unsafe_json_integers() -> None:
    raw = mesh_bytes(
        [(1e100, 0, 0), (1e100 + 1e85, 0, 0), (1e100, 1e85, 0),
         (1e100, 0, 0), (1e100 + 1e85, 0, 0), (1e100, 1e85, 0)],
        [(0, 1, 2), (3, 4, 5)],
    )
    _, _, report = analyze(raw)
    assert report.relations[0].relation_kind == "COPLANAR_AREA"
    assert all(
        isinstance(numerator, str) and isinstance(denominator, str)
        for point in report.relations[0].witnesses
        for numerator, denominator in point
    )


def test_three_shared_identities_fail_as_malformed_simplex() -> None:
    raw = mesh_bytes(
        [(0, 0, 0), (1, 0, 0), (0, 1, 0)],
        [(0, 1, 2), (2, 1, 0)],
    )
    decoded = decode_indexed_triangle_mesh(raw, **{k: LIMITS[k] for k in (
        "media_type", "expected_coordinate_frame_id", "max_bytes", "max_vertices", "max_faces"
    )})
    topology = diagnose_indexed_triangle_mesh(
        raw, decoded, **{k: LIMITS[k] for k in (
            "media_type", "expected_coordinate_frame_id", "max_bytes", "max_vertices", "max_faces"
        )}
    )
    with pytest.raises(MeshPairRelationsError, match="shared_simplex_malformed"):
        diagnose_indexed_triangle_mesh_pair_relations(raw, decoded, topology, **LIMITS)


def test_zero_area_face_fails_closed_before_pair_report() -> None:
    raw = mesh_bytes(
        [(0, 0, 0), (1, 0, 0), (2, 0, 0), (0, 1, 1), (1, 1, 1)],
        [(0, 1, 2), (0, 3, 4)],
    )
    decoded = decode_indexed_triangle_mesh(raw, **{k: LIMITS[k] for k in (
        "media_type", "expected_coordinate_frame_id", "max_bytes", "max_vertices", "max_faces"
    )})
    topology = diagnose_indexed_triangle_mesh(
        raw, decoded, **{k: LIMITS[k] for k in (
            "media_type", "expected_coordinate_frame_id", "max_bytes", "max_vertices", "max_faces"
        )}
    )
    with pytest.raises(MeshPairRelationsError, match="zero_area_face"):
        diagnose_indexed_triangle_mesh_pair_relations(raw, decoded, topology, **LIMITS)


def test_pair_budget_is_checked_before_pair_evaluation() -> None:
    raw = mesh_bytes(
        [(0, 0, 0), (1, 0, 0), (0, 1, 0),
         (0, 0, 2), (1, 0, 2), (0, 1, 2),
         (0, 0, 4), (1, 0, 4), (0, 1, 4)],
        [(0, 1, 2), (3, 4, 5), (6, 7, 8)],
    )
    decoded = decode_indexed_triangle_mesh(raw, **{k: LIMITS[k] for k in (
        "media_type", "expected_coordinate_frame_id", "max_bytes", "max_vertices", "max_faces"
    )})
    topology = diagnose_indexed_triangle_mesh(
        raw, decoded, **{k: LIMITS[k] for k in (
            "media_type", "expected_coordinate_frame_id", "max_bytes", "max_vertices", "max_faces"
        )}
    )
    with pytest.raises(MeshPairRelationsError, match="pair_budget_exhausted"):
        diagnose_indexed_triangle_mesh_pair_relations(
            raw, decoded, topology, **(LIMITS | {"max_face_pairs_evaluated": 2})
        )


def test_provenance_and_full_topology_report_are_revalidated() -> None:
    raw = mesh_bytes(
        [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 2), (1, 0, 2), (0, 1, 2)],
        [(0, 1, 2), (3, 4, 5)],
    )
    decoded, topology, _ = analyze(raw)
    with pytest.raises(MeshPairRelationsError, match="decoded_source_mismatch"):
        diagnose_indexed_triangle_mesh_pair_relations(
            raw, replace(decoded, parser_version="changed"), topology, **LIMITS
        )
    with pytest.raises(MeshPairRelationsError, match="topology_mismatch"):
        diagnose_indexed_triangle_mesh_pair_relations(
            raw, decoded, replace(topology, issues=()), **LIMITS
        )


def test_relation_report_is_repeatable_and_face_vertex_order_invariant() -> None:
    first_raw = mesh_bytes(
        [(0, 0, 0), (2, 0, 0), (0, 2, 0), (1, -1, 0)],
        [(0, 1, 2), (1, 0, 3)],
    )
    decoded, topology, first = analyze(first_raw)
    repeated = diagnose_indexed_triangle_mesh_pair_relations(
        first_raw, decoded, topology, **LIMITS
    )
    assert first == repeated

    reordered_raw = mesh_bytes(
        [(0, 0, 0), (2, 0, 0), (0, 2, 0), (1, -1, 0)],
        [(1, 2, 0), (0, 3, 1)],
    )
    _, _, reordered = analyze(reordered_raw)
    assert reordered.relations[0].relation_kind == first.relations[0].relation_kind
    assert reordered.relations[0].witnesses == first.relations[0].witnesses
