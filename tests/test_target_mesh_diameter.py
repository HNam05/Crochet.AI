from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from crochet_ai import target_mesh_diameter as diameter
from crochet_ai.canonical import jcs_bytes
from crochet_ai.json_types import JSONValue
from crochet_ai.target_mesh_decode import (
    MESH_MEDIA_TYPE,
    DecodedIndexedTriangleMesh,
    decode_indexed_triangle_mesh,
)

FRAME = "frame_diameter_test"


def encode(vertices: list[tuple[float, float, float]]) -> bytes:
    value = {
        "representation_version": "INDEXED_TRIANGLE_MESH_V1",
        "coordinate_system": {
            "length_unit": "MILLIMETER",
            "handedness": "RIGHT_HANDED",
            "coordinate_frame_id": FRAME,
        },
        "vertices": [{"position_mm": list(position)} for position in vertices],
        "faces": [{"vertex_indices": [0, 1, 2]}],
    }
    return json.dumps(value, separators=(",", ":")).encode()


def analyze(
    vertices: list[tuple[float, float, float]], *, budget: int = 100
) -> tuple[bytes, DecodedIndexedTriangleMesh, diameter.VertexDiameterDiagnostic]:
    raw = encode(vertices)
    decoded = decode_indexed_triangle_mesh(
        raw,
        media_type=MESH_MEDIA_TYPE,
        expected_coordinate_frame_id=FRAME,
        max_bytes=100_000,
        max_vertices=100,
        max_faces=100,
    )
    report = diameter.diagnose_indexed_triangle_mesh_diameter(
        raw,
        decoded,
        media_type=MESH_MEDIA_TYPE,
        expected_coordinate_frame_id=FRAME,
        max_bytes=100_000,
        max_vertices=100,
        max_faces=100,
        max_vertex_pairs_evaluated=budget,
    )
    return raw, decoded, report


def test_exact_squared_diameter_and_stable_tied_pairs() -> None:
    _, _, report = analyze(
        [(0.0, 0.0, 0.0), (3.0, 0.0, 0.0), (0.0, 4.0, 0.0), (3.0, 4.0, 0.0)]
    )
    assert report.status == "DIAMETER_DIAGNOSTIC_ONLY"
    assert report.squared_diameter_numerator_mm2 == "25"
    assert report.squared_diameter_denominator_mm2 == "1"
    assert report.maximizing_vertex_pairs == ((0, 3), (1, 2))
    assert report.required_vertex_pairs == report.vertex_pairs_evaluated == 6


def test_all_coincident_identities_return_zero_and_all_tied_pairs() -> None:
    _, _, report = analyze([(2.5, -1.0, 7.0)] * 4)
    assert report.squared_diameter_numerator_mm2 == "0"
    assert report.squared_diameter_denominator_mm2 == "1"
    assert report.maximizing_vertex_pairs == (
        (0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)
    )


def test_exact_rational_handles_subnormal_and_extreme_exponents() -> None:
    _, _, tiny = analyze([(0.0, 0.0, 0.0), (5e-324, 0.0, 0.0), (0.0, 0.0, 0.0)])
    assert tiny.squared_diameter_numerator_mm2 == "1"
    assert tiny.squared_diameter_denominator_mm2 == str(1 << 2148)

    _, _, large = analyze(
        [(-1e308, 0.0, 0.0), (1e308, 0.0, 0.0), (-1e308, 0.0, 0.0)]
    )
    assert int(large.squared_diameter_numerator_mm2) > 10**600
    assert large.squared_diameter_denominator_mm2 == "1"


def test_translation_uses_exact_coordinate_differences() -> None:
    _, _, origin = analyze(
        [(0.0, 0.0, 0.0), (1.25, -2.5, 3.0), (0.0, 0.0, 0.0)]
    )
    _, _, translated = analyze(
        [(1024.0, -1024.0, 2048.0), (1025.25, -1026.5, 2051.0), (1024.0, -1024.0, 2048.0)]
    )
    assert (
        origin.squared_diameter_numerator_mm2,
        origin.squared_diameter_denominator_mm2,
    ) == (
        translated.squared_diameter_numerator_mm2,
        translated.squared_diameter_denominator_mm2,
    )


def test_budget_is_checked_before_pair_evaluation(monkeypatch: pytest.MonkeyPatch) -> None:
    raw, decoded, _ = analyze([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)])
    monkeypatch.setattr(
        diameter,
        "_squared_distance",
        lambda *_: pytest.fail("quadratic work began before rejecting the budget"),
    )
    with pytest.raises(diameter.MeshDiameterError) as error:
        diameter.diagnose_indexed_triangle_mesh_diameter(
            raw,
            decoded,
            media_type=MESH_MEDIA_TYPE,
            expected_coordinate_frame_id=FRAME,
            max_bytes=100_000,
            max_vertices=100,
            max_faces=100,
            max_vertex_pairs_evaluated=2,
        )
    assert error.value.reason == "diameter.vertex_pair_budget_exhausted"


@pytest.mark.parametrize("invalid", [0, -1, True, 1.5])
def test_pair_budget_must_be_positive_integer(invalid: object) -> None:
    raw, decoded, _ = analyze([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 0.0)])
    with pytest.raises(diameter.MeshDiameterError) as error:
        diameter.diagnose_indexed_triangle_mesh_diameter(
            raw,
            decoded,
            media_type=MESH_MEDIA_TYPE,
            expected_coordinate_frame_id=FRAME,
            max_bytes=100_000,
            max_vertices=100,
            max_faces=100,
            max_vertex_pairs_evaluated=invalid,
        )
    assert error.value.reason == "diameter.max_vertex_pairs_evaluated_invalid"


def test_source_redecode_and_decoded_record_tampering_fail_closed() -> None:
    raw, decoded, _ = analyze([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 0.0)])
    changed = replace(decoded, vertices_mm=((0.0, 0.0, 0.0), (2.0, 0.0, 0.0)))
    with pytest.raises(diameter.MeshDiameterError) as error:
        diameter.diagnose_indexed_triangle_mesh_diameter(
            raw,
            changed,
            media_type=MESH_MEDIA_TYPE,
            expected_coordinate_frame_id=FRAME,
            max_bytes=100_000,
            max_vertices=100,
            max_faces=100,
            max_vertex_pairs_evaluated=10,
        )
    assert error.value.reason == "diameter.decoded_source_mismatch"

    with pytest.raises(diameter.MeshDiameterError) as invalid:
        diameter.diagnose_indexed_triangle_mesh_diameter(
            b"not json",
            decoded,
            media_type=MESH_MEDIA_TYPE,
            expected_coordinate_frame_id=FRAME,
            max_bytes=100_000,
            max_vertices=100,
            max_faces=100,
            max_vertex_pairs_evaluated=10,
        )
    assert invalid.value.reason == "diameter.source_invalid"


def test_hash_is_domain_separated_and_commits_to_algorithm_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw, decoded, first = analyze([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 0.0)])
    payload: JSONValue = {
        "algorithm_version": first.algorithm_version,
        "status": first.status,
        "source_sha256": first.source_sha256,
        "parser_name": first.parser_name,
        "parser_version": first.parser_version,
        "media_type": first.media_type,
        "vertex_count": first.vertex_count,
        "required_vertex_pairs": first.required_vertex_pairs,
        "vertex_pairs_evaluated": first.vertex_pairs_evaluated,
        "squared_diameter_mm2": {
            "numerator": first.squared_diameter_numerator_mm2,
            "denominator": first.squared_diameter_denominator_mm2,
        },
        "maximizing_vertex_pairs": [list(pair) for pair in first.maximizing_vertex_pairs],
    }
    assert first.diagnostic_sha256 == hashlib.sha256(
        b"TARGET_MESH_VERTEX_DIAMETER_DIAGNOSTIC_V1\0" + jcs_bytes(payload)
    ).hexdigest()
    monkeypatch.setattr(diameter, "DIAMETER_VERSION", "test-version")
    changed = diameter.diagnose_indexed_triangle_mesh_diameter(
        raw,
        decoded,
        media_type=MESH_MEDIA_TYPE,
        expected_coordinate_frame_id=FRAME,
        max_bytes=100_000,
        max_vertices=100,
        max_faces=100,
        max_vertex_pairs_evaluated=10,
    )
    assert changed.diagnostic_sha256 != first.diagnostic_sha256
