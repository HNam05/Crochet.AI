from __future__ import annotations

import json
from dataclasses import replace
from math import nextafter

import pytest

from crochet_ai.target_mesh_decode import (
    MESH_MEDIA_TYPE,
    DecodedIndexedTriangleMesh,
    decode_indexed_triangle_mesh,
)
from crochet_ai.target_mesh_near_contact import (
    MeshNearContactError,
    NearContactDiagnostic,
    diagnose_indexed_triangle_mesh_near_contact,
)
from crochet_ai.target_mesh_topology import TopologyDiagnostic, diagnose_indexed_triangle_mesh
from crochet_ai.v0_numeric_profile import (
    PROFILE_ID,
    V0NumericProfile,
    resolve_v0_numeric_profile,
)

FRAME = "frame_near_contact_test"
def mesh_bytes(
    vertices: list[tuple[float, float, float]], faces: list[tuple[int, int, int]]
) -> bytes:
    return json.dumps(
        {
            "representation_version": "INDEXED_TRIANGLE_MESH_V1",
            "coordinate_system": {
                "length_unit": "MILLIMETER",
                "handedness": "RIGHT_HANDED",
                "coordinate_frame_id": FRAME,
            },
            "vertices": [{"position_mm": list(point)} for point in vertices],
            "faces": [{"vertex_indices": list(face)} for face in faces],
        },
        separators=(",", ":"),
    ).encode()


def analyze(
    raw: bytes,
    *,
    decoded_override: DecodedIndexedTriangleMesh | None = None,
    topology_override: TopologyDiagnostic | None = None,
    profile_override: V0NumericProfile | None = None,
    max_vertex_pairs: int = 100,
    max_face_pairs: int = 100,
) -> tuple[DecodedIndexedTriangleMesh, TopologyDiagnostic, NearContactDiagnostic]:
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
    if decoded_override is not None:
        decoded = decoded_override
    if topology_override is not None:
        topology = topology_override
    report = diagnose_indexed_triangle_mesh_near_contact(
        raw,
        decoded,
        topology,
        profile=profile_override or resolve_v0_numeric_profile(PROFILE_ID),
        media_type=MESH_MEDIA_TYPE,
        expected_coordinate_frame_id=FRAME,
        max_bytes=100_000,
        max_vertices=100,
        max_faces=100,
        max_vertex_pairs=max_vertex_pairs,
        max_face_pairs=max_face_pairs,
    )
    return decoded, topology, report


def separated_faces(gap: float) -> bytes:
    return mesh_bytes(
        [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, gap), (1, 0, gap), (0, 1, gap)],
        [(0, 1, 2), (3, 4, 5)],
    )


def controlled_threshold_faces(gap: float) -> bytes:
    return mesh_bytes(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.5, 0.1, 0.0),
         (0.49, 0.01, gap), (0.51, 0.01, gap), (0.5, 0.03, gap)],
        [(0, 1, 2), (3, 4, 5)],
    )


def test_nonadjacent_exact_touch_and_component_relation_are_reported() -> None:
    raw = separated_faces(0.0)
    _, _, report = analyze(raw)
    repeated = analyze(raw)[2]
    assert report.status == "NEAR_CONTACT_DIAGNOSTIC_ONLY"
    assert [(pair.face_indices, pair.component_relation) for pair in report.exact_zero_pairs] == [
        ((0, 1), "DIFFERENT_FACE_COMPONENTS")
    ]
    assert report.near_contact_pairs == ()
    assert report.minimum_nonadjacent_squared_distance_numerator_mm2 == "0"
    assert report.diagnostic_sha256 == repeated.diagnostic_sha256
    assert report.diagnostic_sha256 != analyze(raw, max_face_pairs=99)[2].diagnostic_sha256


def test_threshold_is_inclusive_and_uses_exact_rational_comparison() -> None:
    threshold = 2.0**-40
    below = analyze(controlled_threshold_faces(nextafter(threshold, 0.0)))[2]
    at = analyze(controlled_threshold_faces(threshold))[2]
    above = analyze(controlled_threshold_faces(nextafter(threshold, 1.0)))[2]
    assert at.squared_diameter_numerator_mm2 == "1"
    assert at.squared_diameter_denominator_mm2 == "1"
    assert len(below.near_contact_pairs) == 1
    assert len(at.near_contact_pairs) == 1
    assert above.near_contact_pairs == ()


def test_same_component_relation_is_preserved_even_when_topology_is_unusual() -> None:
    raw = mesh_bytes(
        [(0, 0, 0), (1, 0, 0), (0, 1, 0),
         (0, 0, 2.0**-41), (1, 0, 2.0**-41), (0, 1, 2.0**-41),
         (0, 0, 1), (0, 1, 1), (1, 1, 1)],
        [(0, 1, 2), (3, 4, 5), (0, 1, 3), (1, 3, 4), (3, 4, 6)],
    )
    _, _, report = analyze(raw)
    assert any(pair.face_indices == (0, 1) and pair.component_relation == "SAME_FACE_COMPONENT"
               for pair in report.near_contact_pairs)


def test_adjacent_pairs_are_skipped_and_all_adjacent_minimum_is_null() -> None:
    vertices = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
                (0.0, 0.0, 1.0)]
    _, _, report = analyze(mesh_bytes(vertices, [(0, 1, 2), (0, 1, 3)]))
    assert report.face_pairs_enumerated == 1
    assert report.adjacent_face_pairs_skipped == 1
    assert report.adjacent_residual_state == "UNRESOLVED"
    assert report.nonadjacent_face_pairs_evaluated == 0
    assert report.minimum_nonadjacent_squared_distance_numerator_mm2 is None
    assert report.minimum_nonadjacent_squared_distance_denominator_mm2 is None


@pytest.mark.parametrize(
    "budget,reason",
    [("max_vertex_pairs", "near_contact.vertex_pair_budget_exhausted"),
     ("max_face_pairs", "near_contact.face_pair_budget_exhausted")],
)
def test_pair_budget_precheck(budget: str, reason: str) -> None:
    raw = mesh_bytes(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
         (0.0, 0.0, 2.0), (1.0, 0.0, 2.0), (0.0, 1.0, 2.0),
         (0.0, 0.0, 4.0), (1.0, 0.0, 4.0), (0.0, 1.0, 4.0)],
        [(0, 1, 2), (3, 4, 5), (6, 7, 8)],
    )
    with pytest.raises(MeshNearContactError, match=reason):
        analyze(raw, max_vertex_pairs=1 if budget == "max_vertex_pairs" else 100,
                max_face_pairs=1 if budget == "max_face_pairs" else 100)


def test_rejects_tampered_decode_topology_or_profile() -> None:
    raw = separated_faces(1.0)
    decoded, topology, _ = analyze(raw)
    with pytest.raises(MeshNearContactError, match="decoded_source_mismatch"):
        analyze(raw, decoded_override=replace(decoded, source_sha256="0" * 64))
    with pytest.raises(MeshNearContactError, match="topology_mismatch"):
        analyze(raw, topology_override=replace(topology, orientable=False))
    with pytest.raises(MeshNearContactError, match="profile_mismatch"):
        profile = resolve_v0_numeric_profile(PROFILE_ID)
        analyze(raw, profile_override=replace(profile, record_sha256="0" * 64))


def test_exact_rationals_handle_extreme_scale_without_float_square_overflow() -> None:
    huge = analyze(separated_faces(1e308))[2]
    tiny = analyze(separated_faces(5e-324))[2]
    assert huge.minimum_nonadjacent_squared_distance_numerator_mm2 is not None
    assert tiny.minimum_nonadjacent_squared_distance_numerator_mm2 == "1"
    assert len(tiny.near_contact_pairs) == 1


def test_rejects_zero_area_before_distance_evaluation() -> None:
    raw = mesh_bytes(
        [(0, 0, 0), (1, 0, 0), (2, 0, 0), (0, 0, 1)],
        [(0, 1, 2), (0, 1, 3)],
    )
    with pytest.raises(MeshNearContactError, match="zero_area_face"):
        analyze(raw)
