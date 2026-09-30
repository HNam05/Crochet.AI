from __future__ import annotations

import json
from dataclasses import replace
from typing import TypedDict

import pytest

from crochet_ai.target_mesh_boundaries import (
    DirectedBoundaryDiagnostic,
    MeshBoundaryError,
    diagnose_indexed_triangle_mesh_boundaries,
)
from crochet_ai.target_mesh_canonical_order import (
    CanonicalOrderDiagnostic,
    diagnose_indexed_triangle_mesh_canonical_order,
)
from crochet_ai.target_mesh_decode import (
    MESH_MEDIA_TYPE,
    DecodedIndexedTriangleMesh,
    decode_indexed_triangle_mesh,
)

FRAME = "frame_directed_boundary_test"
class Limits(TypedDict):
    media_type: str
    expected_coordinate_frame_id: str
    max_bytes: int
    max_vertices: int
    max_faces: int


LIMITS: Limits = {
    "media_type": MESH_MEDIA_TYPE,
    "expected_coordinate_frame_id": FRAME,
    "max_bytes": 100_000,
    "max_vertices": 100,
    "max_faces": 100,
}
ANNULUS_VERTICES = [
    (-2.0, -2.0, 0.0), (2.0, -2.0, 0.0), (2.0, 2.0, 0.0), (-2.0, 2.0, 0.0),
    (-1.0, -1.0, 0.0), (1.0, -1.0, 0.0), (1.0, 1.0, 0.0), (-1.0, 1.0, 0.0),
]
ANNULUS_FACES = [
    (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
    (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
]
TETRA_VERTICES = [(0., 0., 0.), (1., 0., 0.), (0., 1., 0.), (0., 0., 1.)]
TETRA_FACES = [(0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)]


def encode(vertices: list[tuple[float, float, float]], faces: list[tuple[int, int, int]]) -> bytes:
    value = {
        "representation_version": "INDEXED_TRIANGLE_MESH_V1",
        "coordinate_system": {
            "length_unit": "MILLIMETER", "handedness": "RIGHT_HANDED",
            "coordinate_frame_id": FRAME,
        },
        "vertices": [{"position_mm": list(point)} for point in vertices],
        "faces": [{"vertex_indices": list(face)} for face in faces],
    }
    return json.dumps(value, separators=(",", ":")).encode()


def analyze(
    raw: bytes,
    *,
    max_bytes: int = LIMITS["max_bytes"],
    max_vertices: int = LIMITS["max_vertices"],
    max_faces: int = LIMITS["max_faces"],
) -> tuple[DecodedIndexedTriangleMesh, CanonicalOrderDiagnostic, DirectedBoundaryDiagnostic]:
    options: Limits = LIMITS | {
        "max_bytes": max_bytes,
        "max_vertices": max_vertices,
        "max_faces": max_faces,
    }
    decoded = decode_indexed_triangle_mesh(raw, **options)
    ordering = diagnose_indexed_triangle_mesh_canonical_order(raw, decoded, **options)
    report = diagnose_indexed_triangle_mesh_boundaries(raw, decoded, ordering, **options)
    return decoded, ordering, report


def test_annulus_uses_source_face_induced_directed_cycles() -> None:
    _, _, report = analyze(encode(ANNULUS_VERTICES, ANNULUS_FACES))
    # Expected independently from the face tuples: outer boundary is CCW,
    # inner boundary is clockwise for this consistently wound sheet.
    loops_as_positions = {
        tuple(ANNULUS_VERTICES[report.ordered_to_source_vertex_indices[v]] for v in loop)
        for loop in report.boundary_loops
    }
    assert loops_as_positions == {
        ((-2., -2., 0.), (2., -2., 0.), (2., 2., 0.), (-2., 2., 0.)),
        ((-1., -1., 0.), (-1., 1., 0.), (1., 1., 0.), (1., -1., 0.)),
    }
    assert report.status == "DIRECTED_BOUNDARIES_DIAGNOSTIC_ONLY"


def test_vertex_face_permutations_preserve_ordered_loop_and_component_keys() -> None:
    _, _, first = analyze(encode(ANNULUS_VERTICES, ANNULUS_FACES))
    old_at_new = (5, 2, 7, 0, 3, 6, 1, 4)
    new_of_old = {old: new for new, old in enumerate(old_at_new)}
    permuted_vertices = [ANNULUS_VERTICES[i] for i in old_at_new]
    permuted_faces: list[tuple[int, int, int]] = [
        (new_of_old[face[0]], new_of_old[face[1]], new_of_old[face[2]])
        for face in reversed(ANNULUS_FACES)
    ]
    _, _, second = analyze(encode(permuted_vertices, permuted_faces))
    assert first.boundary_loops == second.boundary_loops
    assert tuple(c.ordered_face_key for c in first.components) == tuple(
        c.ordered_face_key for c in second.components
    )


def test_reversing_all_faces_reverses_boundary_direction() -> None:
    reverse: list[tuple[int, int, int]] = [
        (a, c, b) for a, b, c in ANNULUS_FACES
    ]
    _, _, normal = analyze(encode(ANNULUS_VERTICES, ANNULUS_FACES))
    _, _, reversed_report = analyze(encode(ANNULUS_VERTICES, reverse))
    normal_positions = {
        tuple(ANNULUS_VERTICES[normal.ordered_to_source_vertex_indices[v]] for v in loop)
        for loop in normal.boundary_loops
    }
    reversed_positions = {
        tuple(ANNULUS_VERTICES[reversed_report.ordered_to_source_vertex_indices[v]] for v in loop)
        for loop in reversed_report.boundary_loops
    }
    reverse_edges = {
        frozenset((loop[(i + 1) % len(loop)], loop[i]) for i in range(len(loop)))
        for loop in normal_positions
    }
    actual_edges = {
        frozenset((loop[i], loop[(i + 1) % len(loop)]) for i in range(len(loop)))
        for loop in reversed_positions
    }
    assert actual_edges == reverse_edges


def test_disjoint_sheets_are_sorted_and_closed_mesh_has_no_loops() -> None:
    vertices = ANNULUS_VERTICES + [(x + 10., y, z) for x, y, z in ANNULUS_VERTICES]
    faces: list[tuple[int, int, int]] = ANNULUS_FACES + [
        (face[0] + 8, face[1] + 8, face[2] + 8) for face in ANNULUS_FACES
    ]
    _, _, report = analyze(encode(vertices, faces))
    assert len(report.components) == 2
    assert report.components[0].ordered_vertex_key < report.components[1].ordered_vertex_key
    _, _, closed = analyze(encode(TETRA_VERTICES, TETRA_FACES))
    assert closed.boundary_loops == ()


def test_tampered_decode_ordering_and_invalid_topology_fail_closed() -> None:
    raw = encode(ANNULUS_VERTICES, ANNULUS_FACES)
    decoded, ordering, _ = analyze(raw)
    with pytest.raises(MeshBoundaryError, match="decoded_source_mismatch"):
        diagnose_indexed_triangle_mesh_boundaries(
            raw, replace(decoded, parser_version="bad"), ordering, **LIMITS
        )
    with pytest.raises(MeshBoundaryError, match="ordering_mismatch"):
        tampered_order = replace(ordering, diagnostic_sha256="0" * 64)
        diagnose_indexed_triangle_mesh_boundaries(raw, decoded, tampered_order, **LIMITS)
    inconsistent: list[tuple[int, int, int]] = ANNULUS_FACES.copy()
    a, b, c = inconsistent[0]
    inconsistent[0] = (a, c, b)
    invalid_raw = encode(ANNULUS_VERTICES, inconsistent)
    invalid_decoded = decode_indexed_triangle_mesh(invalid_raw, **LIMITS)
    invalid_order = diagnose_indexed_triangle_mesh_canonical_order(
        invalid_raw, invalid_decoded, **LIMITS
    )
    with pytest.raises(MeshBoundaryError, match=r"preconditions_failed"):
        diagnose_indexed_triangle_mesh_boundaries(
            invalid_raw, invalid_decoded, invalid_order, **LIMITS
        )


@pytest.mark.parametrize("limit", ["max_bytes", "max_vertices", "max_faces"])
def test_caller_budgets_are_enforced(limit: str) -> None:
    raw = encode(ANNULUS_VERTICES, ANNULUS_FACES)
    decoded, ordering, _ = analyze(raw)
    max_bytes = len(raw) - 1 if limit == "max_bytes" else LIMITS["max_bytes"]
    max_vertices = 7 if limit == "max_vertices" else LIMITS["max_vertices"]
    max_faces = 7 if limit == "max_faces" else LIMITS["max_faces"]
    with pytest.raises(MeshBoundaryError, match="source_invalid"):
        diagnose_indexed_triangle_mesh_boundaries(
            raw,
            decoded,
            ordering,
            media_type=MESH_MEDIA_TYPE,
            expected_coordinate_frame_id=FRAME,
            max_bytes=max_bytes,
            max_vertices=max_vertices,
            max_faces=max_faces,
        )
