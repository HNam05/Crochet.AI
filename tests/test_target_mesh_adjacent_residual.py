from __future__ import annotations

import json
from fractions import Fraction

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from crochet_ai import target_mesh_adjacent_residual as residual
from crochet_ai.target_mesh_decode import MESH_MEDIA_TYPE

FRAME = "frame_adjacent_residual_test"
LIMITS = {
    "media_type": MESH_MEDIA_TYPE,
    "expected_coordinate_frame_id": FRAME,
    "max_bytes": 100_000,
    "max_vertices": 100,
    "max_faces": 100,
    "max_face_pairs": 100,
    "max_distance_piece_pairs": 100,
    "max_lambda_bits": 32,
}


def mesh_bytes(
    vertices: list[tuple[float, float, float]], faces: list[tuple[int, int, int]],
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


def analyze(raw: bytes, *, lam: Fraction = Fraction(1, 2), **limits: object):
    return residual.diagnose_indexed_triangle_mesh_adjacent_residual(
        raw, lambda_value=lam, **(LIMITS | limits),
    )


def edge_mesh() -> bytes:
    return mesh_bytes(
        [(0, 0, 0), (2, 0, 0), (0, 2, 0), (0, 0, 2)],
        [(0, 1, 2), (1, 0, 3)],
    )


def vertex_fan_mesh() -> bytes:
    return mesh_bytes(
        [(0, 0, 0), (2, 0, 0), (0, 2, 0), (0, 0, 2), (-2, 0, 0), (0, -2, 0)],
        [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 5), (0, 5, 1)],
    )


def tetrahedron() -> bytes:
    return mesh_bytes(
        [(0, 0, 0), (2, 0, 0), (0, 2, 0), (0, 0, 2)],
        [(0, 2, 1), (0, 1, 3), (1, 2, 3), (2, 0, 3)],
    )


def octahedron() -> bytes:
    return mesh_bytes(
        [(0, 0, 1), (0, 0, -1), (1, 0, 0), (0, 1, 0),
         (-1, 0, 0), (0, -1, 0)],
        [(0, 2, 3), (0, 3, 4), (0, 4, 5), (0, 5, 2),
         (1, 3, 2), (1, 4, 3), (1, 5, 4), (1, 2, 5)],
    )


def test_two_face_shared_edge_matches_exact_kernel_oracle() -> None:
    report = analyze(edge_mesh())
    assert report.status == "EXPERIMENTAL_MESH_ADJACENT_RESIDUAL_ONLY"
    assert report.required_face_pairs == 1
    assert report.adjacent_face_pair_count == 1
    assert report.nonadjacent_face_pairs_skipped == 0
    assert report.pairs[0].shared_entity == "shared_edge"
    assert Fraction(
        f"{report.pairs[0].squared_distance_numerator_mm2}/"
        f"{report.pairs[0].squared_distance_denominator_mm2}"
    ) == 1
    assert (report.minimum_squared_distance_numerator_mm2,
            report.minimum_squared_distance_denominator_mm2) == ("1", "1")
    assert report.pairs[0].evaluated_piece_pairs == 2


def test_valid_vertex_fan_includes_vertex_only_pairs_with_exact_oracles() -> None:
    report = analyze(vertex_fan_mesh())
    vertex_pairs = [pair for pair in report.pairs if pair.shared_entity == "shared_vertex"]
    assert len(vertex_pairs) == 5
    assert all(pair.evaluated_piece_pairs == 4 for pair in vertex_pairs)
    assert report.adjacent_face_pair_count == 10
    assert report.nonadjacent_face_pairs_skipped == 0
    direct_fixture_pair = next(
        pair for pair in vertex_pairs if pair.shared_source_vertex_indices == (0,)
        and set(pair.source_face_indices) == {0, 2}
    )
    assert Fraction(
        f"{direct_fixture_pair.squared_distance_numerator_mm2}/"
        f"{direct_fixture_pair.squared_distance_denominator_mm2}"
    ) == Fraction(1, 2)


def test_tetrahedron_has_exact_all_pair_budget_and_minimum() -> None:
    report = analyze(tetrahedron(), max_face_pairs=6)
    assert report.required_face_pairs == report.adjacent_face_pair_count == 6
    assert Fraction(
        f"{report.minimum_squared_distance_numerator_mm2}/"
        f"{report.minimum_squared_distance_denominator_mm2}"
    ) == Fraction(1, 3)


def test_nonadjacent_pairs_are_reported_and_still_consume_full_pair_budget() -> None:
    report = analyze(octahedron(), max_face_pairs=28)
    assert report.required_face_pairs == 28
    assert report.adjacent_face_pair_count == 24
    assert report.nonadjacent_face_pairs_skipped == 4

    with pytest.raises(residual.MeshAdjacentResidualError, match="face_pair_budget_exhausted"):
        analyze(octahedron(), max_face_pairs=27)


def test_valid_topology_folded_overlap_fails_with_source_pair_context() -> None:
    raw = mesh_bytes(
        [(0, 0, 0), (2, 0, 0), (0, 2, 0), (0, 1, 0)],
        [(0, 1, 2), (1, 0, 3)],
    )
    with pytest.raises(
        residual.MeshAdjacentResidualError,
        match=r"pair_0_1:.*contact_beyond|pair_0_1:.*positive_area",
    ):
        analyze(raw)


@pytest.mark.parametrize(
    "raw,reason",
    [
        (mesh_bytes(
            [(0, 0, 0), (2, 0, 0), (0, 2, 0), (0, 0, 2)],
            [(0, 1, 2), (0, 1, 3)],
        ), "topology_invalid"),
        (mesh_bytes(
            [(0, 0, 0), (1, 0, 0), (2, 0, 0), (0, 0, 2)],
            [(0, 1, 2), (1, 0, 3)],
        ), "degenerate_faces"),
        (mesh_bytes(
            [(0, 0, 0), (2, 0, 0), (0, 2, 0), (0, 0, 2), (-2, 0, 0)],
            [(0, 1, 2), (0, 3, 4)],
        ), "topology_invalid"),
    ],
)
def test_invalid_topology_and_degeneracy_fail_closed(raw: bytes, reason: str) -> None:
    with pytest.raises(residual.MeshAdjacentResidualError, match=reason):
        analyze(raw)


def test_reordering_preserves_pair_distance_multiset_but_hash_is_source_specific() -> None:
    first = analyze(edge_mesh())
    reordered_raw = mesh_bytes(
        [(0, 2, 0), (0, 0, 2), (2, 0, 0), (0, 0, 0)],
        [(3, 2, 0), (2, 3, 1)],
    )
    second = analyze(reordered_raw)

    def values(report):
        return sorted(
            Fraction(
                f"{pair.squared_distance_numerator_mm2}/"
                f"{pair.squared_distance_denominator_mm2}"
            )
            for pair in report.pairs
        )
    assert values(first) == values(second) == [Fraction(1)]
    assert first.source_sha256 != second.source_sha256
    assert first.diagnostic_sha256 != second.diagnostic_sha256


def test_source_and_decoded_tampering_fail_closed() -> None:
    raw = edge_mesh()
    changed = raw.replace(b"2,0,0", b"3,0,0", 1)
    assert analyze(raw).source_sha256 != analyze(changed).source_sha256
    with pytest.raises(residual.MeshAdjacentResidualError, match="source_or_topology_invalid"):
        analyze(b"not an indexed mesh")


@pytest.mark.parametrize("lam", [Fraction(0), Fraction(1), 0.5, True])
def test_lambda_must_be_explicit_strict_fraction(lam: object) -> None:
    with pytest.raises(residual.MeshAdjacentResidualError, match="lambda_invalid"):
        analyze(edge_mesh(), lam=lam)


def test_lambda_bit_limit_is_explicit() -> None:
    with pytest.raises(residual.MeshAdjacentResidualError, match="lambda_bit_budget"):
        analyze(edge_mesh(), lam=Fraction(1, 257), max_lambda_bits=8)


@pytest.mark.parametrize("name", [
    "max_bytes", "max_vertices", "max_faces", "max_face_pairs",
    "max_distance_piece_pairs", "max_lambda_bits",
])
@pytest.mark.parametrize("invalid", [0, -1, True, 1.5])
def test_every_work_limit_must_be_positive_integer(name: str, invalid: object) -> None:
    with pytest.raises(residual.MeshAdjacentResidualError, match=f"{name}_invalid"):
        analyze(edge_mesh(), **{name: invalid})


def test_complete_face_pair_budget_checked_before_any_kernel_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        residual, "adjacent_triangle_residual_squared",
        lambda *_args, **_kwargs: pytest.fail("kernel called before full pair budget check"),
    )
    with pytest.raises(residual.MeshAdjacentResidualError, match="face_pair_budget_exhausted"):
        analyze(tetrahedron(), max_face_pairs=5)


def test_piece_pair_budget_checked_before_any_kernel_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        residual, "adjacent_triangle_residual_squared",
        lambda *_args, **_kwargs: pytest.fail("kernel called before full piece-pair budget check"),
    )
    with pytest.raises(
        residual.MeshAdjacentResidualError,
        match="distance_piece_pair_budget_exhausted",
    ):
        analyze(tetrahedron(), max_distance_piece_pairs=11)


def test_exact_piece_pair_limit_is_accepted() -> None:
    # Four tetrahedron faces have six shared edges: two primitive evaluations each.
    report = analyze(tetrahedron(), max_distance_piece_pairs=12)
    assert report.predicted_distance_piece_pairs == report.evaluated_distance_piece_pairs == 12


@settings(max_examples=100, derandomize=True, deadline=None)
@given(
    numerator=st.integers(min_value=1, max_value=9),
    x=st.integers(min_value=-20, max_value=20),
    y=st.integers(min_value=-20, max_value=20),
    z=st.integers(min_value=-20, max_value=20),
    scale=st.integers(min_value=1, max_value=8),
)
def test_edge_property_matches_exact_oracle_after_translation_and_scale(
    numerator: int, x: int, y: int, z: int, scale: int,
) -> None:
    """Independent edge oracle: q=4λ²; translation invariant and scale² covariant."""
    lam = Fraction(numerator, 10)
    base = analyze(edge_mesh(), lam=lam)
    expected = 4 * lam**2
    assert Fraction(
        f"{base.minimum_squared_distance_numerator_mm2}/"
        f"{base.minimum_squared_distance_denominator_mm2}"
    ) == expected

    original = [(0, 0, 0), (2, 0, 0), (0, 2, 0), (0, 0, 2)]
    transformed = [
        (scale * point[0] + x, scale * point[1] + y, scale * point[2] + z)
        for point in original
    ]
    moved = analyze(mesh_bytes(transformed, [(0, 1, 2), (1, 0, 3)]), lam=lam)
    assert Fraction(
        f"{moved.minimum_squared_distance_numerator_mm2}/"
        f"{moved.minimum_squared_distance_denominator_mm2}"
    ) == scale**2 * expected
