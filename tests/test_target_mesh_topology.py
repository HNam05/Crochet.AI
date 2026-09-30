from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256

import pytest

from crochet_ai import target_mesh_topology
from crochet_ai.canonical import jcs_bytes
from crochet_ai.target_mesh_decode import MESH_MEDIA_TYPE, decode_indexed_triangle_mesh
from crochet_ai.target_mesh_topology import (
    MeshTopologyError,
    TopologyDiagnostic,
    diagnose_indexed_triangle_mesh,
)

FRAME = "frame_topology_test"


def mesh_value(
    vertices: int,
    faces: tuple[tuple[int, int, int], ...],
) -> dict[str, object]:
    return {
        "representation_version": "INDEXED_TRIANGLE_MESH_V1",
        "coordinate_system": {
            "length_unit": "MILLIMETER",
            "handedness": "RIGHT_HANDED",
            "coordinate_frame_id": FRAME,
        },
        "vertices": [
            {"position_mm": [float(index), float(index % 2), float(index % 3)]}
            for index in range(vertices)
        ],
        "faces": [{"vertex_indices": face} for face in faces],
    }


def analyze(
    faces: tuple[tuple[int, int, int], ...],
    vertices: int,
):
    raw = json.dumps(mesh_value(vertices, faces), separators=(",", ":")).encode()
    decoded = decode_indexed_triangle_mesh(
        raw,
        media_type=MESH_MEDIA_TYPE,
        expected_coordinate_frame_id=FRAME,
        max_bytes=100_000,
        max_vertices=100,
        max_faces=100,
    )
    report = diagnose_indexed_triangle_mesh(
        raw,
        decoded,
        media_type=MESH_MEDIA_TYPE,
        expected_coordinate_frame_id=FRAME,
        max_bytes=100_000,
        max_vertices=100,
        max_faces=100,
    )
    return raw, decoded, report


def codes(report: TopologyDiagnostic) -> set[str]:
    return {issue.code for issue in report.issues}


def test_tetrahedron_has_exact_closed_manifold_topology() -> None:
    _, _, report = analyze(((0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)), 4)
    assert report.status == "EXACT_TOPOLOGY_DIAGNOSTIC_ONLY"
    assert report.edge_count == 6
    assert report.boundary_edge_count == 0
    assert report.component_face_indices == ((0, 1, 2, 3),)
    assert report.issues == ()
    assert report.issue_count == 0
    assert report.orientable


def test_open_disk_reports_one_boundary_loop() -> None:
    _, _, report = analyze(((0, 1, 2), (0, 2, 3)), 4)
    assert report.boundary_edge_count == 4
    assert report.boundary_loops == ((0, 1, 2, 3),)
    assert report.issues == ()


def test_duplicate_faces_distinguish_same_and_reversed_winding() -> None:
    _, _, report = analyze(((0, 1, 2), (0, 1, 2), (0, 2, 1)), 3)
    assert "DUPLICATE_FACE_SAME_WINDING" in codes(report)
    assert "DUPLICATE_FACE_REVERSED_WINDING" in codes(report)


def test_isolated_vertex_and_isolated_face_are_reported() -> None:
    _, _, report = analyze(((0, 1, 2), (3, 4, 5)), 7)
    assert "UNREFERENCED_VERTEX" in codes(report)
    assert "ISOLATED_FACE" in codes(report)
    assert report.component_face_indices == ((0,), (1,))


def test_three_face_edge_is_nonmanifold() -> None:
    _, _, report = analyze(((0, 1, 2), (1, 0, 3), (0, 1, 4)), 5)
    assert report.nonmanifold_edge_count == 1
    assert "NONMANIFOLD_EDGE" in codes(report)
    assert report.orientable is None


def test_bow_tie_vertex_is_detected_without_merging_components() -> None:
    _, _, report = analyze(((0, 1, 2), (0, 3, 4)), 5)
    assert report.component_face_indices == ((0,), (1,))
    assert "NONMANIFOLD_VERTEX_LINK" in codes(report)


def test_local_reversed_tetra_face_reports_winding_mismatch() -> None:
    _, _, report = analyze(((0, 2, 1), (0, 1, 3), (1, 3, 2), (2, 0, 3)), 4)
    assert "WINDING_MISMATCH" in codes(report)
    assert report.orientable


def test_mobius_strip_parity_contradiction_is_nonorientable() -> None:
    faces = (
        (0, 1, 2),
        (1, 3, 2),
        (2, 3, 4),
        (3, 5, 4),
        (4, 5, 1),
        (5, 0, 1),
    )
    _, _, report = analyze(faces, 6)
    assert report.nonmanifold_edge_count == 0
    assert len(report.boundary_loops) == 1
    assert report.orientable is False


@pytest.mark.parametrize(
    ("faces", "vertices"),
    [(((0, 1, 2), (1, 3, 4)), 5), (((0, 1, 2), (0, 3, 4), (0, 5, 6)), 7)],
)
def test_boundary_chain_or_branch_does_not_fabricate_loops(
    faces: tuple[tuple[int, int, int], ...], vertices: int
) -> None:
    _, _, report = analyze(faces, vertices)
    assert "BOUNDARY_DEGREE" in codes(report)
    assert report.boundary_loops == ()


def test_changed_decoded_record_and_changed_source_fail_without_report() -> None:
    raw, decoded, _ = analyze(((0, 1, 2),), 3)
    changed = replace(decoded, parser_version="tampered")
    kwargs = {
        "media_type": MESH_MEDIA_TYPE,
        "expected_coordinate_frame_id": FRAME,
        "max_bytes": 100_000,
        "max_vertices": 100,
        "max_faces": 100,
    }
    with pytest.raises(MeshTopologyError, match="decoded_source_mismatch"):
        diagnose_indexed_triangle_mesh(raw, changed, **kwargs)
    with pytest.raises(MeshTopologyError, match="source_invalid"):
        diagnose_indexed_triangle_mesh(raw + b"x", decoded, **kwargs)


def test_repeated_runs_are_deterministic_and_budget_is_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw, decoded, first = analyze(((0, 1, 2),), 3)
    second = diagnose_indexed_triangle_mesh(
        raw,
        decoded,
        media_type=MESH_MEDIA_TYPE,
        expected_coordinate_frame_id=FRAME,
        max_bytes=100_000,
        max_vertices=100,
        max_faces=100,
    )
    assert first == second
    report_payload = {
        "algorithm_version": target_mesh_topology.TOPOLOGY_VERSION,
        "status": first.status,
        "source_sha256": first.source_sha256,
        "parser_name": first.parser_name,
        "parser_version": first.parser_version,
        "vertex_count": first.vertex_count,
        "face_count": first.face_count,
        "edge_count": first.edge_count,
        "boundary_edge_count": first.boundary_edge_count,
        "nonmanifold_edge_count": first.nonmanifold_edge_count,
        "component_face_indices": [list(item) for item in first.component_face_indices],
        "boundary_loops": [list(item) for item in first.boundary_loops],
        "issues": [
            {"code": item.code, "vertices": list(item.vertices), "faces": list(item.faces)}
            for item in first.issues
        ],
        "orientable": first.orientable,
    }
    expected_hash = sha256(
        b"EXACT_TOPOLOGY_DIAGNOSTIC_V1\0" + jcs_bytes(report_payload)
    ).hexdigest()
    assert first.diagnostic_sha256 == expected_hash
    monkeypatch.setattr(target_mesh_topology, "TOPOLOGY_VERSION", "test-version")
    changed_version_report = target_mesh_topology.diagnose_indexed_triangle_mesh(
        raw,
        decoded,
        media_type=MESH_MEDIA_TYPE,
        expected_coordinate_frame_id=FRAME,
        max_bytes=100_000,
        max_vertices=100,
        max_faces=100,
    )
    assert changed_version_report.diagnostic_sha256 != first.diagnostic_sha256
    with pytest.raises(MeshTopologyError, match=r"topology.source_invalid"):
        diagnose_indexed_triangle_mesh(
            raw,
            decoded,
            media_type=MESH_MEDIA_TYPE,
            expected_coordinate_frame_id=FRAME,
            max_bytes=5,
            max_vertices=100,
            max_faces=100,
        )
