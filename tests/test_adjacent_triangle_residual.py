from fractions import Fraction
from itertools import permutations
from math import nextafter

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from crochet_ai.adjacent_triangle_residual import (
    AdjacentTriangleResidualError,
    adjacent_triangle_residual_squared,
)

F = Fraction


def p(x: int | Fraction, y: int | Fraction, z: int | Fraction):
    return (F(x), F(y), F(z))


def edge_pair():
    return (
        (p(0, 0, 0), p(2, 0, 0), p(0, 2, 0)),
        (p(0, 0, 0), p(2, 0, 0), p(0, 0, 2)),
    )


def compute(a, b, shared=((0, 0), (1, 1)), lam=F(1, 2), cap=4):  # noqa: B008
    return adjacent_triangle_residual_squared(
        a, b, shared_identity_indices=shared, lambda_value=lam, max_piece_pairs=cap,
    )


def test_shared_edge_zone_distance_and_diagnostic():
    a, b = edge_pair()
    result = compute(a, b)
    assert result.distance_squared == F(1)
    assert result.diagnostic.status == "EXPERIMENTAL"
    assert result.diagnostic.zone_version == "adjacent_face_relative_zone_v1"
    assert result.diagnostic.evaluated_piece_pairs == 2


def test_shared_vertex_zone_is_exact_and_reports_pair_count():
    a = (p(0, 0, 0), p(2, 0, 0), p(0, 2, 0))
    b = (p(0, 0, 0), p(0, 0, 2), p(-2, 0, 0))
    result = compute(a, b, ((0, 0),), F(1, 2), 4)
    assert result.diagnostic.shared_entity == "shared_vertex"
    assert result.diagnostic.evaluated_piece_pairs == 4
    assert result.distance_squared == F(1, 2)


def test_extra_overlap_is_rejected_before_zone_distance():
    a = (p(0, 0, 0), p(2, 0, 0), p(0, 2, 0))
    b = (p(0, 0, 0), p(2, 0, 0), p(0, 1, 0))
    with pytest.raises(AdjacentTriangleResidualError, match="contact_beyond"):
        compute(a, b)


def test_extra_edge_contact_is_rejected_for_declared_shared_vertex():
    a = (p(0, 0, 0), p(2, 0, 0), p(0, 2, 0))
    b = (p(0, 0, 0), p(1, 0, 0), p(0, 0, 2))
    with pytest.raises(AdjacentTriangleResidualError, match="contact_beyond"):
        compute(a, b, ((0, 0),), F(1, 2), 4)


@pytest.mark.parametrize("lam", [F(0), F(1), F(1, 2)])
def test_lambda_contract(lam):
    a, b = edge_pair()
    if lam == F(1, 2):
        assert compute(a, b, lam=lam).distance_squared == 1
    else:
        with pytest.raises(AdjacentTriangleResidualError, match="lambda"):
            compute(a, b, lam=lam)


@pytest.mark.parametrize("lam", [0.5, True])
def test_lambda_requires_explicit_fraction(lam):
    a, b = edge_pair()
    with pytest.raises(AdjacentTriangleResidualError, match="lambda"):
        compute(a, b, lam=lam)


def test_smallest_positive_binary64_rational_lambda_is_accepted():
    a, b = edge_pair()
    lam = F.from_float(nextafter(0.0, 1.0))
    result = compute(a, b, lam=lam)
    assert result.distance_squared == 4 * lam**2


def test_identity_and_budget_validation():
    a, b = edge_pair()
    with pytest.raises(AdjacentTriangleResidualError, match="coordinates_must_match"):
        compute(a, b, ((0, 1), (1, 0)))
    with pytest.raises(AdjacentTriangleResidualError, match="positive_integer"):
        compute(a, b, cap=True)
    for invalid_pairs, code in [
        (((0, 0), (0, 1)), "unique"),
        (((0, 0), (1, 1), (2, 2)), "one_or_two"),
        (((0, 0), (3, 1)), "triangle_indices"),
    ]:
        with pytest.raises(AdjacentTriangleResidualError, match=code):
            compute(a, b, invalid_pairs)
    vertex_b = (p(0, 0, 0), p(0, 0, 2), p(-2, 0, 0))
    with pytest.raises(AdjacentTriangleResidualError, match="budget_exceeded"):
        compute(a, vertex_b, ((0, 0),), F(1, 2), 3)
    with pytest.raises(AdjacentTriangleResidualError, match="budget_exceeded"):
        compute(a, edge_pair()[1], cap=1)


def test_degenerate_and_nonfinite_triangles_are_rejected():
    _, b = edge_pair()
    degenerate = (p(0, 0, 0), p(1, 1, 1), p(2, 2, 2))
    with pytest.raises(ValueError, match=r"triangle\.degenerate"):
        compute(degenerate, b)
    nonfinite = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, float("inf"), 0.0))
    with pytest.raises(ValueError, match=r"coordinate\.must_be_fraction_or_finite_float"):
        compute(nonfinite, b)
    malformed = (p(0, 0, 0), p(1, 0, 0))
    with pytest.raises(ValueError, match=r"triangle\.requires_three_vertices"):
        compute(malformed, b)


@settings(max_examples=100, derandomize=True)
@given(
    st.integers(min_value=1, max_value=9),
    st.integers(min_value=-20, max_value=20),
    st.integers(min_value=-20, max_value=20),
    st.integers(min_value=-20, max_value=20),
    st.integers(min_value=1, max_value=8),
)
def test_edge_exact_oracle_translation_and_uniform_scale_invariance(
    numerator, x, y, z, scale,
):
    """Exact rational distance equals 4λ²; independent oracle, Hypothesis replay/shrink."""
    a, b = edge_pair()
    lam = F(numerator, 10)
    baseline = F(4) * lam**2
    assert compute(a, b, lam=lam).distance_squared == baseline
    def transform(q):
        return tuple(scale * q[i] + (x, y, z)[i] for i in range(3))

    moved_a = tuple(transform(q) for q in a)
    moved_b = tuple(transform(q) for q in b)
    assert compute(moved_a, moved_b, lam=lam).distance_squared == scale**2 * baseline


def test_triangle_permutations_preserve_distance():
    a, b = edge_pair()
    expected = compute(a, b).distance_squared
    assert adjacent_triangle_residual_squared(
        a[1:] + a[:1], b[2:] + b[:2],
        shared_identity_indices=((2, 1), (0, 2)),
        lambda_value=F(1, 2), max_piece_pairs=4,
    ).distance_squared == expected


def test_exact_quarter_turn_preserves_distance():
    a, b = edge_pair()
    def rotate(q):
        return (-q[1], q[0], q[2])

    turned_a = tuple(rotate(q) for q in a)
    turned_b = tuple(rotate(q) for q in b)
    assert compute(turned_a, turned_b).distance_squared == compute(a, b).distance_squared


def test_swapping_triangles_and_all_vertex_permutations_preserves_distance():
    a, b = edge_pair()
    expected = F(1)

    def matching_pairs(first, second):
        return tuple(
            (i, j)
            for i, point_a in enumerate(first)
            for j, point_b in enumerate(second)
            if point_a == point_b and point_a in (a[0], a[1])
        )

    for first in permutations(a):
        for second in permutations(b):
            pairs = matching_pairs(first, second)
            assert len(pairs) == 2
            result = adjacent_triangle_residual_squared(
                first, second, shared_identity_indices=pairs,
                lambda_value=F(1, 2), max_piece_pairs=4,
            )
            assert result.distance_squared == expected
            reverse = adjacent_triangle_residual_squared(
                second, first, shared_identity_indices=tuple((j, i) for i, j in pairs),
                lambda_value=F(1, 2), max_piece_pairs=4,
            )
            assert reverse.distance_squared == expected


def test_vertex_zone_distance_independent_of_polygon_fan_diagonal():
    a = (p(0, 0, 0), p(2, 0, 0), p(0, 2, 0))
    b = (p(0, 0, 0), p(0, 0, 2), p(-2, 0, 0))
    expected = F(1, 2)
    for first in permutations(a):
        for second in permutations(b):
            pairs = ((next(i for i, q in enumerate(first) if q == a[0]),
                      next(i for i, q in enumerate(second) if q == b[0])),)
            assert adjacent_triangle_residual_squared(
                first, second, shared_identity_indices=pairs,
                lambda_value=F(1, 2), max_piece_pairs=4,
            ).distance_squared == expected


def test_mixed_retained_excluded_region_is_included():
    # Different face heights make the mixed minimum unambiguous: the second
    # face's retained region is one unit from the full first face, while the
    # retained-retained regions are separated by squared distance five.
    a = (p(0, 0, 0), p(2, 0, 0), p(0, 4, 0))
    b = (p(0, 0, 0), p(2, 0, 0), p(0, 0, 2))
    result = compute(a, b)
    assert result.distance_squared == F(1)
