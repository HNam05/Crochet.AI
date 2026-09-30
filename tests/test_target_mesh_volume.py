from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from fractions import Fraction

import pytest

from crochet_ai import target_mesh_volume as volume
from crochet_ai.canonical import jcs_bytes
from crochet_ai.json_types import JSONValue
from crochet_ai.target_mesh_decode import (
    MESH_MEDIA_TYPE,
    DecodedIndexedTriangleMesh,
    decode_indexed_triangle_mesh,
)
from crochet_ai.target_mesh_topology import diagnose_indexed_triangle_mesh
from crochet_ai.v0_numeric_profile import PROFILE_ID, resolve_v0_numeric_profile

FRAME = "frame_volume_test"
TETRA_FACES = [(1, 2, 3), (0, 2, 1), (0, 1, 3), (0, 3, 2)]
TETRA_VERTICES = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]


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
        "vertices": [{"position_mm": list(position)} for position in vertices],
        "faces": [{"vertex_indices": list(face)} for face in faces],
    }
    return json.dumps(value, separators=(",", ":")).encode()


def analyze(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
    *,
    pair_budget: int = 100,
) -> tuple[bytes, DecodedIndexedTriangleMesh, volume.SignedSixVolumeDiagnostic]:
    raw = encode(vertices, faces)
    decoded = decode_indexed_triangle_mesh(
        raw,
        media_type=MESH_MEDIA_TYPE,
        expected_coordinate_frame_id=FRAME,
        max_bytes=100_000,
        max_vertices=100,
        max_faces=100,
    )
    topology = diagnose_indexed_triangle_mesh(
        raw,
        decoded,
        media_type=MESH_MEDIA_TYPE,
        expected_coordinate_frame_id=FRAME,
        max_bytes=100_000,
        max_vertices=100,
        max_faces=100,
    )
    report = volume.diagnose_indexed_triangle_mesh_signed_six_volume(
        raw,
        decoded,
        topology,
        resolve_v0_numeric_profile(PROFILE_ID),
        media_type=MESH_MEDIA_TYPE,
        expected_coordinate_frame_id=FRAME,
        max_bytes=100_000,
        max_vertices=100,
        max_faces=100,
        max_vertex_pairs_evaluated=pair_budget,
    )
    return raw, decoded, report


def test_outward_and_inward_tetrahedra_report_exact_signed_volume() -> None:
    _, _, outward = analyze(TETRA_VERTICES, TETRA_FACES)
    _, _, inward = analyze(TETRA_VERTICES, [tuple(reversed(face)) for face in TETRA_FACES])
    assert outward.status == volume.VOLUME_STATUS
    assert outward.components[0].signed_six_volume_numerator_mm3 == "1"
    assert outward.components[0].signed_six_volume_denominator_mm3 == "1"
    assert outward.components[0].decision.startswith("ALGEBRAIC_POSITIVE_SIGN")
    assert inward.components[0].signed_six_volume_numerator_mm3 == "-1"
    assert inward.components[0].decision.startswith("ALGEBRAIC_NEGATIVE_SIGN")
    assert outward.self_intersection_state == "UNRESOLVED"


def test_translation_and_power_of_two_scaling_preserve_exact_algebraic_result() -> None:
    _, _, baseline = analyze(TETRA_VERTICES, TETRA_FACES)
    transformed = [(x * 8 + 1024, y * 8 - 2048, z * 8 + 4096) for x, y, z in TETRA_VERTICES]
    _, _, scaled = analyze(transformed, TETRA_FACES)
    assert scaled.components[0].signed_six_volume_numerator_mm3 == "512"
    assert scaled.components[0].signed_six_volume_denominator_mm3 == "1"
    assert baseline.components[0].reference_vertex_index == 0
    assert scaled.components[0].reference_vertex_index == 0


def test_disconnected_closed_components_are_reported_independently() -> None:
    vertices = TETRA_VERTICES + [(x + 4, y, z) for x, y, z in TETRA_VERTICES]
    faces = TETRA_FACES + [tuple(index + 4 for index in face) for face in TETRA_FACES]
    _, _, report = analyze(vertices, faces)
    assert len(report.components) == 2
    assert [part.signed_six_volume_numerator_mm3 for part in report.components] == ["1", "1"]
    assert [part.reference_vertex_index for part in report.components] == [0, 4]


def test_open_inconsistent_and_nonmanifold_components_are_ineligible() -> None:
    with pytest.raises(volume.MeshVolumeError, match=r"volume\.topology_ineligible"):
        analyze(TETRA_VERTICES, TETRA_FACES[:-1])

    inconsistent = TETRA_FACES.copy()
    inconsistent[0] = tuple(reversed(inconsistent[0]))
    with pytest.raises(volume.MeshVolumeError, match=r"volume\.topology_ineligible"):
        analyze(TETRA_VERTICES, inconsistent)

    nonmanifold = [*TETRA_FACES, (1, 2, 0)]
    with pytest.raises(volume.MeshVolumeError, match=r"volume\.topology_ineligible"):
        analyze(TETRA_VERTICES, nonmanifold)

    unreferenced = [*TETRA_VERTICES, (12.0, 12.0, 12.0)]
    with pytest.raises(volume.MeshVolumeError, match=r"volume\.topology_ineligible"):
        analyze(unreferenced, TETRA_FACES)


def test_flat_closed_topology_is_exact_zero_and_indeterminate() -> None:
    vertices = [(x, y, 0.0) for x, y, _ in TETRA_VERTICES]
    _, _, report = analyze(vertices, TETRA_FACES)
    assert report.components[0].signed_six_volume_numerator_mm3 == "0"
    assert report.components[0].status == "INDETERMINATE"
    assert report.components[0].decision == "NO_REVERSAL"


def test_exact_threshold_equality_is_indeterminate() -> None:
    # The mesh diameter squared is 1 and the exact determinant is 2^-36.
    vertices = [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, 0.0),
        (0.5, 0.5, 0.0),
        (0.5, 0.5, 2.0**-35),
    ]
    _, _, report = analyze(vertices, TETRA_FACES)
    component = report.components[0]
    six_volume = Fraction(
        int(component.signed_six_volume_numerator_mm3),
        int(component.signed_six_volume_denominator_mm3),
    )
    diameter_squared = Fraction(
        int(report.squared_diameter_numerator_mm2),
        int(report.squared_diameter_denominator_mm2),
    )
    assert diameter_squared == 1
    assert six_volume * six_volume == Fraction(1, 1 << 72) * diameter_squared**3
    assert component.status == "INDETERMINATE"


def test_extreme_binary64_coordinates_remain_finite_exact_rationals() -> None:
    tiny = [(x * 2.0**-500, y * 2.0**-500, z * 2.0**-500) for x, y, z in TETRA_VERTICES]
    huge = [(x * 2.0**500, y * 2.0**500, z * 2.0**500) for x, y, z in TETRA_VERTICES]
    assert analyze(tiny, TETRA_FACES)[2].components[0].signed_six_volume_numerator_mm3 != "0"
    assert analyze(huge, TETRA_FACES)[2].components[0].signed_six_volume_numerator_mm3 != "0"


def test_pair_budget_is_prechecked_and_tampered_inputs_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw, decoded, _ = analyze(TETRA_VERTICES, TETRA_FACES)
    topology = diagnose_indexed_triangle_mesh(
        raw, decoded, media_type=MESH_MEDIA_TYPE, expected_coordinate_frame_id=FRAME,
        max_bytes=100_000, max_vertices=100, max_faces=100,
    )
    monkeypatch.setattr(
        volume, "_squared_distance", lambda *_: pytest.fail("budget not prechecked")
    )
    with pytest.raises(volume.MeshVolumeError, match=r"volume\.vertex_pair_budget_exhausted"):
        volume.diagnose_indexed_triangle_mesh_signed_six_volume(
            raw, decoded, topology, resolve_v0_numeric_profile(PROFILE_ID),
            media_type=MESH_MEDIA_TYPE, expected_coordinate_frame_id=FRAME,
            max_bytes=100_000, max_vertices=100, max_faces=100,
            max_vertex_pairs_evaluated=5,
        )
    with pytest.raises(volume.MeshVolumeError, match=r"volume\.topology_mismatch"):
        volume.diagnose_indexed_triangle_mesh_signed_six_volume(
            raw, decoded, replace(topology, orientable=False),
            resolve_v0_numeric_profile(PROFILE_ID),
            media_type=MESH_MEDIA_TYPE, expected_coordinate_frame_id=FRAME,
            max_bytes=100_000, max_vertices=100, max_faces=100,
            max_vertex_pairs_evaluated=10,
        )
    with pytest.raises(volume.MeshVolumeError, match=r"volume\.decoded_source_mismatch"):
        volume.diagnose_indexed_triangle_mesh_signed_six_volume(
            raw, replace(decoded, source_sha256="0" * 64), topology,
            resolve_v0_numeric_profile(PROFILE_ID), media_type=MESH_MEDIA_TYPE,
            expected_coordinate_frame_id=FRAME, max_bytes=100_000,
            max_vertices=100, max_faces=100, max_vertex_pairs_evaluated=10,
        )


def test_diagnostic_hash_covers_full_jcs_payload_and_profile_tampering_fails() -> None:
    raw, decoded, report = analyze(TETRA_VERTICES, TETRA_FACES)
    payload: JSONValue = {
        "status": report.status,
        "algorithm_version": report.algorithm_version,
        "predicate_backend": report.predicate_backend,
        "predicate_backend_version": report.predicate_backend_version,
        "source_sha256": report.source_sha256,
        "parser_name": report.parser_name,
        "parser_version": report.parser_version,
        "media_type": report.media_type,
        "coordinate_frame_id": report.coordinate_frame_id,
        "numerical_profile": {
            "profile_id": report.numerical_profile_id,
            "profile_version": report.numerical_profile_version,
            "record_sha256": report.numerical_profile_record_sha256,
        },
        "topology_diagnostic_sha256": report.topology_diagnostic_sha256,
        "vertex_count": report.vertex_count,
        "face_count": report.face_count,
        "max_bytes": report.max_bytes,
        "max_vertices": report.max_vertices,
        "max_faces": report.max_faces,
        "max_vertex_pairs_evaluated": report.max_vertex_pairs_evaluated,
        "required_vertex_pairs": report.required_vertex_pairs,
        "vertex_pairs_evaluated": report.vertex_pairs_evaluated,
        "squared_diameter_mm2": {
            "numerator": report.squared_diameter_numerator_mm2,
            "denominator": report.squared_diameter_denominator_mm2,
        },
        "components": [
            {
                "face_indices": list(component.face_indices),
                "reference_vertex_index": component.reference_vertex_index,
                "signed_six_volume_mm3": {
                    "numerator": component.signed_six_volume_numerator_mm3,
                    "denominator": component.signed_six_volume_denominator_mm3,
                },
                "status": component.status,
                "decision": component.decision,
                "ineligibility_reasons": list(component.ineligibility_reasons),
            }
            for component in report.components
        ],
        "self_intersection_state": report.self_intersection_state,
    }
    assert report.diagnostic_sha256 == hashlib.sha256(
        b"TARGET_MESH_SIGNED_SIX_VOLUME_DIAGNOSTIC_V1\0" + jcs_bytes(payload)
    ).hexdigest()
    topology = diagnose_indexed_triangle_mesh(
        raw, decoded, media_type=MESH_MEDIA_TYPE, expected_coordinate_frame_id=FRAME,
        max_bytes=100_000, max_vertices=100, max_faces=100,
    )
    with pytest.raises(volume.MeshVolumeError, match=r"volume\.profile_mismatch"):
        volume.diagnose_indexed_triangle_mesh_signed_six_volume(
            raw, decoded, topology,
            replace(resolve_v0_numeric_profile(PROFILE_ID), profile_version="changed"),
            media_type=MESH_MEDIA_TYPE, expected_coordinate_frame_id=FRAME,
            max_bytes=100_000, max_vertices=100, max_faces=100,
            max_vertex_pairs_evaluated=10,
        )
