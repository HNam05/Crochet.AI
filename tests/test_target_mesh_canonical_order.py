from __future__ import annotations

import json
from dataclasses import replace

import pytest

from crochet_ai.target_mesh_canonical_order import (
    MeshCanonicalOrderError,
    diagnose_indexed_triangle_mesh_canonical_order,
)
from crochet_ai.target_mesh_decode import MESH_MEDIA_TYPE, decode_indexed_triangle_mesh

FRAME = "frame_canonical_order_test"
LIMITS = {
    "media_type": MESH_MEDIA_TYPE,
    "expected_coordinate_frame_id": FRAME,
    "max_bytes": 100_000,
    "max_vertices": 100,
    "max_faces": 100,
}
TETRA_VERTICES = [
    (0.0, 0.0, 0.0),
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0),
]
TETRA_FACES = [(0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)]


def encode(
    vertices: list[tuple[float, float, float]], faces: list[tuple[int, int, int]]
) -> bytes:
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


def analyze(raw: bytes, **limits: object):
    decoded = decode_indexed_triangle_mesh(raw, **(LIMITS | limits))
    return decoded, diagnose_indexed_triangle_mesh_canonical_order(
        raw, decoded, **(LIMITS | limits)
    )


def permuted_tetrahedron() -> bytes:
    old_vertex_at_new_index = (2, 0, 3, 1)
    new_index_of_old = {old: new for new, old in enumerate(old_vertex_at_new_index)}
    vertices = [TETRA_VERTICES[old] for old in old_vertex_at_new_index]
    faces = [
        tuple(new_index_of_old[index] for index in face)
        for face in reversed(TETRA_FACES)
    ]
    return encode(vertices, faces)


def test_mesh_identity_is_invariant_to_vertex_and_face_permutations() -> None:
    _, first = analyze(encode(TETRA_VERTICES, TETRA_FACES))
    _, permuted = analyze(permuted_tetrahedron())

    assert first.derived_vertices_mm == permuted.derived_vertices_mm
    assert first.derived_faces == permuted.derived_faces
    assert first.identity_unavailable_reason == "v0_geometry_and_normalization_unverified"
    assert not hasattr(first, "canonical_mesh_sha256")
    assert first.diagnostic_sha256 != permuted.diagnostic_sha256
    assert first.status == "ORDERING_DIAGNOSTIC_ONLY"


def test_both_maps_are_inverse_and_source_dependent() -> None:
    _, first = analyze(encode(TETRA_VERTICES, TETRA_FACES))
    _, permuted = analyze(permuted_tetrahedron())

    assert first.derived_to_source_vertex_indices == (0, 3, 2, 1)
    assert tuple(
        first.source_to_derived_vertex_indices[index]
        for index in first.derived_to_source_vertex_indices
    ) == tuple(range(4))
    assert tuple(
        first.source_to_derived_face_indices[index]
        for index in first.derived_to_source_face_indices
    ) == tuple(range(4))
    assert first.source_to_derived_vertex_indices != permuted.source_to_derived_vertex_indices
    assert first.source_to_derived_face_indices != permuted.source_to_derived_face_indices


@pytest.mark.parametrize(
    ("vertices", "faces", "reason"),
    [
        (
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
            [(0, 1, 2), (0, 1, 2)],
            "index_topology_invalid",
        ),
        (
            [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 0.0)],
            [(0, 1, 2), (0, 2, 1), (0, 1, 3)],
            "exactly_coincident_vertices",
        ),
        ([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0)], [(0, 1, 2)], "zero_area_faces"),
    ],
)
def test_invalid_preconditions_keep_mesh_hash_absent(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
    reason: str,
) -> None:
    _, report = analyze(encode(vertices, faces))
    assert report.identity_unavailable_reason is not None
    assert reason in report.identity_unavailable_reason
    assert "v0_geometry_and_normalization_unverified" in report.identity_unavailable_reason
    assert report.diagnostic_sha256


def test_tampered_source_and_decoded_record_fail_closed() -> None:
    raw = encode(TETRA_VERTICES, TETRA_FACES)
    decoded, _ = analyze(raw)
    with pytest.raises(MeshCanonicalOrderError, match="decoded_source_mismatch"):
        diagnose_indexed_triangle_mesh_canonical_order(
            raw, replace(decoded, parser_version="tampered"), **LIMITS
        )
    with pytest.raises(MeshCanonicalOrderError, match="source_invalid"):
        diagnose_indexed_triangle_mesh_canonical_order(raw + b"x", decoded, **LIMITS)


def test_input_budgets_are_enforced() -> None:
    raw = encode(TETRA_VERTICES, TETRA_FACES)
    decoded, _ = analyze(raw)
    with pytest.raises(MeshCanonicalOrderError, match="source_invalid"):
        diagnose_indexed_triangle_mesh_canonical_order(
            raw, decoded, **(LIMITS | {"max_bytes": len(raw) - 1})
        )
    with pytest.raises(MeshCanonicalOrderError, match="source_invalid"):
        diagnose_indexed_triangle_mesh_canonical_order(
            raw, decoded, **(LIMITS | {"max_vertices": len(TETRA_VERTICES) - 1})
        )
    with pytest.raises(MeshCanonicalOrderError, match="source_invalid"):
        diagnose_indexed_triangle_mesh_canonical_order(
            raw, decoded, **(LIMITS | {"max_faces": len(TETRA_FACES) - 1})
        )
