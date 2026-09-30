from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

import crochet_ai.target_mesh_exact_geometry as exact_geometry
from crochet_ai.canonical import jcs_bytes
from crochet_ai.target_mesh_decode import (
    MESH_MEDIA_TYPE,
    DecodedIndexedTriangleMesh,
    decode_indexed_triangle_mesh,
)
from crochet_ai.target_mesh_exact_geometry import (
    ExactGeometryDiagnostic,
    MeshGeometryError,
    diagnose_indexed_triangle_mesh_exact_geometry,
)

FRAME = "frame_exact_geometry_test"


def mesh_value(
    vertices: list[tuple[float, float, float]], faces: list[tuple[int, int, int]]
) -> dict[str, object]:
    return {
        "representation_version": "INDEXED_TRIANGLE_MESH_V1",
        "coordinate_system": {
            "length_unit": "MILLIMETER",
            "handedness": "RIGHT_HANDED",
            "coordinate_frame_id": FRAME,
        },
        "vertices": [{"position_mm": list(point)} for point in vertices],
        "faces": [{"vertex_indices": list(face)} for face in faces],
    }


def encode(
    vertices: list[tuple[float, float, float]], faces: list[tuple[int, int, int]]
) -> bytes:
    return json.dumps(mesh_value(vertices, faces), separators=(",", ":")).encode()


def analyze(raw: bytes) -> tuple[DecodedIndexedTriangleMesh, ExactGeometryDiagnostic]:
    decoded = decode_indexed_triangle_mesh(
        raw,
        media_type=MESH_MEDIA_TYPE,
        expected_coordinate_frame_id=FRAME,
        max_bytes=100_000,
        max_vertices=100,
        max_faces=100,
    )
    report = diagnose_indexed_triangle_mesh_exact_geometry(
        raw,
        decoded,
        media_type=MESH_MEDIA_TYPE,
        expected_coordinate_frame_id=FRAME,
        max_bytes=100_000,
        max_vertices=100,
        max_faces=100,
    )
    return decoded, report


def test_reports_exact_duplicate_coordinate_groups_and_zero_area_faces() -> None:
    raw = encode(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 0.0, 0.0)],
        [(0, 1, 2), (0, 1, 3)],
    )
    _, report = analyze(raw)
    assert report.status == "EXACT_GEOMETRY_DIAGNOSTIC_ONLY"
    assert report.coincident_vertex_groups[0].vertex_indices == (0, 3)
    assert tuple(item.face_index for item in report.zero_area_faces) == (0, 1)
    assert report.coincident_vertex_group_count == 1
    assert report.zero_area_face_count == 2


def test_reports_disjoint_collinear_and_nonzero_area_faces_exactly() -> None:
    raw = encode(
        [(0.0, 0.0, 0.0), (1e308, 0.0, 0.0), (0.0, 1e-308, 0.0),
         (0.0, 0.0, 1.0), (1.0, 1.0, 1.0), (2.0, 2.0, 1.0)],
        [(0, 1, 2), (3, 4, 5)],
    )
    _, report = analyze(raw)
    assert tuple(item.face_index for item in report.zero_area_faces) == (1,)


@pytest.mark.parametrize(
    "vertices",
    [
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        [(1e100, -1e100, 1e100), (1e100 + 1e85, -1e100, 1e100),
         (1e100, -1e100 + 1e85, 1e100)],
        [(0.0, 0.0, 0.0), (1e-300, 0.0, 0.0), (0.0, 1e-300, 0.0)],
    ],
)
def test_translation_and_scale_preserve_exact_nonzero_classification(
    vertices: list[tuple[float, float, float]],
) -> None:
    _, report = analyze(encode(vertices, [(0, 1, 2)]))
    assert report.zero_area_faces == ()


def test_source_and_complete_decoded_record_are_revalidated() -> None:
    raw = encode([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)], [(0, 1, 2)])
    decoded, _ = analyze(raw)
    kwargs = {
        "media_type": MESH_MEDIA_TYPE,
        "expected_coordinate_frame_id": FRAME,
        "max_bytes": 100_000,
        "max_vertices": 100,
        "max_faces": 100,
    }
    with pytest.raises(MeshGeometryError, match="decoded_source_mismatch"):
        diagnose_indexed_triangle_mesh_exact_geometry(
            raw, replace(decoded, parser_version="tampered"), **kwargs
        )
    with pytest.raises(MeshGeometryError, match="source_invalid"):
        diagnose_indexed_triangle_mesh_exact_geometry(raw + b"x", decoded, **kwargs)
    with pytest.raises(MeshGeometryError, match="source_invalid"):
        diagnose_indexed_triangle_mesh_exact_geometry(
            raw, decoded, **{**kwargs, "max_bytes": len(raw) - 1}
        )


def test_result_is_deterministic_and_hash_binds_full_payload() -> None:
    raw = encode(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 0.0, 0.0)],
        [(0, 1, 2)],
    )
    decoded, first = analyze(raw)
    second = diagnose_indexed_triangle_mesh_exact_geometry(
        raw,
        decoded,
        media_type=MESH_MEDIA_TYPE,
        expected_coordinate_frame_id=FRAME,
        max_bytes=100_000,
        max_vertices=100,
        max_faces=100,
    )
    assert first == second
    payload = {
        "algorithm_version": first.algorithm_version,
        "status": first.status,
        "source_sha256": first.source_sha256,
        "parser_name": first.parser_name,
        "parser_version": first.parser_version,
        "media_type": first.media_type,
        "vertex_count": first.vertex_count,
        "face_count": first.face_count,
        "coincident_vertex_groups": [
            {"vertex_indices": list(group.vertex_indices)}
            for group in first.coincident_vertex_groups
        ],
        "zero_area_faces": [{"face_index": issue.face_index} for issue in first.zero_area_faces],
    }
    assert first.diagnostic_sha256 == hashlib.sha256(
        b"EXACT_MESH_GEOMETRY_DIAGNOSTIC_V1\0" + jcs_bytes(payload)
    ).hexdigest()
    assert first.source_sha256 == hashlib.sha256(raw).hexdigest()

def test_algorithm_version_changes_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = encode([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)], [(0, 1, 2)])
    decoded, first = analyze(raw)
    monkeypatch.setattr(exact_geometry, "EXACT_GEOMETRY_VERSION", "test-version")
    changed = diagnose_indexed_triangle_mesh_exact_geometry(
        raw,
        decoded,
        media_type=MESH_MEDIA_TYPE,
        expected_coordinate_frame_id=FRAME,
        max_bytes=100_000,
        max_vertices=100,
        max_faces=100,
    )
    assert changed.diagnostic_sha256 != first.diagnostic_sha256
