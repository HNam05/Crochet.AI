from __future__ import annotations

import json
import math
from dataclasses import replace

import pytest

import crochet_ai.target_mesh_relative_thresholds as relative
from crochet_ai.target_mesh_decode import (
    MESH_MEDIA_TYPE,
    DecodedIndexedTriangleMesh,
    decode_indexed_triangle_mesh,
)
from crochet_ai.v0_numeric_profile import PROFILE_ID, resolve_v0_numeric_profile

FRAME = "frame_relative_thresholds_test"
THRESHOLD = 2.0**-40


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


def analyze(
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
    *,
    budget: int = 1000,
) -> tuple[bytes, DecodedIndexedTriangleMesh, relative.RelativeThresholdDiagnostic]:
    raw = encode(vertices, faces)
    decoded = decode_indexed_triangle_mesh(
        raw,
        media_type=MESH_MEDIA_TYPE,
        expected_coordinate_frame_id=FRAME,
        max_bytes=100_000,
        max_vertices=100,
        max_faces=100,
    )
    report = relative.diagnose_indexed_triangle_mesh_relative_thresholds(
        raw,
        decoded,
        profile=resolve_v0_numeric_profile(PROFILE_ID),
        media_type=MESH_MEDIA_TYPE,
        expected_coordinate_frame_id=FRAME,
        max_bytes=100_000,
        max_vertices=100,
        max_faces=100,
        max_pair_evaluations=budget,
    )
    return raw, decoded, report


@pytest.mark.parametrize(
    ("offset", "near"),
    [
        (math.nextafter(THRESHOLD, 0.0), True),
        (THRESHOLD, True),
        (math.nextafter(THRESHOLD, math.inf), False),
    ],
)
def test_coordinate_distance_boundary_is_inclusive(
    offset: float, near: bool
) -> None:
    _, _, report = analyze(
        [(0.0, 0.0, 0.0), (offset, 0.0, 0.0), (1.0, 0.0, 0.0)], [(0, 1, 2)]
    )
    assert ((0, 1) in report.near_coincident_vertex_pairs) is near
    assert report.squared_diameter_numerator_mm2 == "1"


@pytest.mark.parametrize(
    ("height", "near"),
    [
        (math.nextafter(THRESHOLD, 0.0), True),
        (THRESHOLD, True),
        (math.nextafter(THRESHOLD, math.inf), False),
    ],
)
def test_area2_boundary_is_inclusive(height: float, near: bool) -> None:
    _, _, report = analyze(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.5, height, 0.0)], [(0, 1, 2)]
    )
    assert (0 in report.near_zero_area_faces) is near
    assert report.exact_zero_area_faces == ()
    assert report.squared_diameter_numerator_mm2 == "1"
    assert report.squared_diameter_denominator_mm2 == "1"


def test_exact_zero_area_and_coordinate_equal_are_separately_reported() -> None:
    _, _, report = analyze(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        [(0, 1, 2), (0, 1, 3)],
    )
    assert report.exact_coincident_vertex_groups == ((0, 2),)
    assert report.near_coincident_vertex_pairs == ()
    assert report.exact_zero_area_faces == (0,)
    assert report.near_zero_area_faces == (0,)


def test_exact_rationals_handle_overflow_and_underflow_scales() -> None:
    _, _, huge = analyze(
        [(-1e308, 0.0, 0.0), (1e308, 0.0, 0.0), (0.0, 1e308, 0.0)], [(0, 1, 2)]
    )
    _, _, tiny = analyze(
        [(0.0, 0.0, 0.0), (5e-324, 0.0, 0.0), (0.0, 5e-324, 0.0)], [(0, 1, 2)]
    )
    assert int(huge.squared_diameter_numerator_mm2) > 10**600
    assert int(tiny.squared_diameter_denominator_mm2) > 10**600


def test_zero_scale_fails_closed() -> None:
    raw = encode([(2.0, 3.0, 4.0)] * 3, [(0, 1, 2)])
    decoded = decode_indexed_triangle_mesh(
        raw,
        media_type=MESH_MEDIA_TYPE,
        expected_coordinate_frame_id=FRAME,
        max_bytes=100_000,
        max_vertices=10,
        max_faces=10,
    )
    with pytest.raises(relative.RelativeThresholdDiagnosticError) as error:
        relative.diagnose_indexed_triangle_mesh_relative_thresholds(
            raw,
            decoded,
            profile=resolve_v0_numeric_profile(PROFILE_ID),
            media_type=MESH_MEDIA_TYPE,
            expected_coordinate_frame_id=FRAME,
            max_bytes=100_000,
            max_vertices=10,
            max_faces=10,
            max_pair_evaluations=10,
        )
    assert error.value.reason == "relative_thresholds.zero_scale"


def test_profile_tampering_and_decoded_record_tampering_fail_closed() -> None:
    raw, decoded, _ = analyze(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)], [(0, 1, 2)]
    )
    profile = resolve_v0_numeric_profile(PROFILE_ID)
    forged = replace(
        profile,
        thresholds=replace(profile.thresholds, triangle_area2_normalized_max=0.0),
    )
    arguments = {
        "media_type": MESH_MEDIA_TYPE,
        "expected_coordinate_frame_id": FRAME,
        "max_bytes": 100_000,
        "max_vertices": 10,
        "max_faces": 10,
        "max_pair_evaluations": 10,
    }
    with pytest.raises(relative.RelativeThresholdDiagnosticError) as profile_error:
        relative.diagnose_indexed_triangle_mesh_relative_thresholds(
            raw, decoded, profile=forged, **arguments
        )
    assert profile_error.value.reason == "relative_thresholds.profile_mismatch"

    changed = replace(
        decoded,
        vertices_mm=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    )
    with pytest.raises(relative.RelativeThresholdDiagnosticError) as decoded_error:
        relative.diagnose_indexed_triangle_mesh_relative_thresholds(
            raw, changed, profile=profile, **arguments
        )
    assert decoded_error.value.reason == "relative_thresholds.decoded_source_mismatch"


def test_pair_budget_prechecked_before_quadratic_loops(monkeypatch: pytest.MonkeyPatch) -> None:
    raw, decoded, _ = analyze(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)], [(0, 1, 2)]
    )
    monkeypatch.setattr(
        relative,
        "_distance_squared",
        lambda *_: pytest.fail("pair loop ran before pair budget rejection"),
    )
    with pytest.raises(relative.RelativeThresholdDiagnosticError) as error:
        relative.diagnose_indexed_triangle_mesh_relative_thresholds(
            raw,
            decoded,
            profile=resolve_v0_numeric_profile(PROFILE_ID),
            media_type=MESH_MEDIA_TYPE,
            expected_coordinate_frame_id=FRAME,
            max_bytes=100_000,
            max_vertices=10,
            max_faces=10,
            max_pair_evaluations=5,
        )
    assert error.value.reason == "relative_thresholds.pair_budget_exhausted"


def test_translation_and_uniform_scale_preserve_classification() -> None:
    _, _, original = analyze(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, THRESHOLD, 0.0)], [(0, 1, 2)]
    )
    _, _, transformed = analyze(
        [(8.0, -4.0, 2.0), (10.0, -4.0, 2.0), (8.0, -4.0 + 2 * THRESHOLD, 2.0)],
        [(0, 1, 2)],
    )
    assert original.near_zero_area_faces == transformed.near_zero_area_faces == (0,)
    assert original.near_coincident_vertex_pairs == transformed.near_coincident_vertex_pairs


def test_diagnostic_hash_is_deterministic_and_commits_to_budget() -> None:
    vertices = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, THRESHOLD, 0.0)]
    _, _, first = analyze(vertices, [(0, 1, 2)])
    _, _, repeated = analyze(vertices, [(0, 1, 2)])
    _, _, different_budget = analyze(vertices, [(0, 1, 2)], budget=1001)
    assert first.diagnostic_sha256 == repeated.diagnostic_sha256
    assert first.diagnostic_sha256 != different_budget.diagnostic_sha256
    assert first.status == "DIAGNOSTIC_ONLY"
    assert first.predicate_backend == "EXACT_BINARY64_RATIONAL_V1"
