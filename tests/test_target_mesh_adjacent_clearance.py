from __future__ import annotations

import json
from dataclasses import replace
from fractions import Fraction

import pytest

from crochet_ai import target_mesh_adjacent_clearance as clearance
from crochet_ai.target_mesh_decode import MESH_MEDIA_TYPE
from crochet_ai.v0_adjacent_profile import (
    PROFILE_ID,
    resolve_v0_adjacent_numeric_profile,
)

FRAME = "frame_adjacent_clearance_test"
LIMITS = {
    "media_type": MESH_MEDIA_TYPE,
    "expected_coordinate_frame_id": FRAME,
    "max_bytes": 100_000,
    "max_vertices": 100,
    "max_faces": 100,
    "max_vertex_pairs": 100,
    "max_face_pairs": 100,
    "max_distance_piece_pairs": 100,
    "max_lambda_bits": 32,
}
ZONE = {"policy_id": "BARYCENTRIC_PAIR_LOCAL_V1",
        "lambda": {"numerator": "1", "denominator": "2"}}


def mesh_bytes(vertices: list[tuple[float, float, float]],
               faces: list[tuple[int, int, int]]) -> bytes:
    return json.dumps({
        "representation_version": "INDEXED_TRIANGLE_MESH_V1",
        "coordinate_system": {"length_unit": "MILLIMETER", "handedness": "RIGHT_HANDED",
                              "coordinate_frame_id": FRAME},
        "vertices": [{"position_mm": list(point)} for point in vertices],
        "faces": [{"vertex_indices": list(face)} for face in faces],
    }, separators=(",", ":")).encode()


def edge_mesh() -> bytes:
    return mesh_bytes([(0, 0, 0), (2, 0, 0), (0, 2, 0), (0, 0, 2)],
                      [(0, 1, 2), (1, 0, 3)])


def analyze(raw: bytes, **kwargs: object) -> clearance.AdjacentClearanceDiagnostic:
    return clearance.diagnose_indexed_triangle_mesh_adjacent_clearance(
        raw, profile=resolve_v0_adjacent_numeric_profile(PROFILE_ID),
        adjacent_exclusion_zone=ZONE, **(LIMITS | kwargs),
    )


def test_source_bound_diagnostic_covers_every_adjacent_pair() -> None:
    report = analyze(edge_mesh())
    repeated = analyze(edge_mesh())
    assert report.status == "ADJACENT_CLEARANCE_DIAGNOSTIC_ONLY"
    assert report.source_sha256 != report.residual_diagnostic_sha256
    assert report.adjacent_face_pair_count == len(report.pairs) == 1
    assert report.required_face_pairs == 1
    assert report.evaluated_distance_piece_pairs == 2
    assert report.pairs[0].source_face_indices == (0, 1)
    assert report.pairs[0].normalized_threshold_state == "ABOVE_THRESHOLD"
    assert report.diagnostic_sha256 == repeated.diagnostic_sha256


def test_exact_threshold_boundary_is_inclusive_without_float_rounding() -> None:
    pair = clearance.MeshAdjacentResidualPair(
        (0, 1), (0, 1), "shared_edge", (0, 1), "1", str(1 << 80), 2,
    )
    threshold = Fraction(1, 1 << 40)
    at = clearance._classify(pair, threshold**2)
    above = clearance._classify(replace(pair, squared_distance_numerator_mm2="1",
                                        squared_distance_denominator_mm2=str((1 << 80) - 1)),
                                threshold**2)
    assert at.normalized_threshold_state == "WITHIN_THRESHOLD"
    assert above.normalized_threshold_state == "ABOVE_THRESHOLD"


def test_original_contact_beyond_shared_entity_fails_closed() -> None:
    raw = mesh_bytes([(0, 0, 0), (2, 0, 0), (0, 2, 0), (0, 1, 0)],
                     [(0, 1, 2), (1, 0, 3)])
    with pytest.raises(clearance.MeshAdjacentClearanceError,
                       match=r"contact_beyond|positive_area"):
        analyze(raw)


def test_profile_zone_and_pair_budgets_are_mandatory() -> None:
    profile = resolve_v0_adjacent_numeric_profile(PROFILE_ID)
    with pytest.raises(clearance.MeshAdjacentClearanceError, match="profile_mismatch"):
        clearance.diagnose_indexed_triangle_mesh_adjacent_clearance(
            edge_mesh(), profile=replace(profile, record_sha256="0" * 64),
            adjacent_exclusion_zone=ZONE, **LIMITS,
        )
    with pytest.raises(clearance.MeshAdjacentClearanceError, match="profile_or_zone_invalid"):
        clearance.diagnose_indexed_triangle_mesh_adjacent_clearance(
            edge_mesh(), profile=profile,
            adjacent_exclusion_zone={"policy_id": "BARYCENTRIC_PAIR_LOCAL_V1",
                                     "lambda": {"numerator": "2", "denominator": "4"}},
            **LIMITS,
        )
    with pytest.raises(clearance.MeshAdjacentClearanceError, match="vertex_pair_budget_exhausted"):
        analyze(edge_mesh(), max_vertex_pairs=5)
