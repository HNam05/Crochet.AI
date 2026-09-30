from fractions import Fraction

import pytest

from crochet_ai.exact_triangle_distance import triangle_distance_squared
from crochet_ai.exact_triangle_relation import ExactTriangleRelationError

F = Fraction


def p(x: int | Fraction, y: int | Fraction, z: int | Fraction):
    return (F(x), F(y), F(z))


def test_parallel_offset_and_coplanar_separation() -> None:
    first = (p(0, 0, 0), p(2, 0, 0), p(0, 2, 0))
    elevated = (p(0, 0, 2), p(2, 0, 2), p(0, 2, 2))
    separated = (p(3, 3, 0), p(4, 3, 0), p(3, 4, 0))
    assert triangle_distance_squared(first, elevated) == F(4)
    assert triangle_distance_squared(first, separated) == F(8)


def test_vertex_to_face_interior_and_vertex_to_edge_boundary() -> None:
    face = (p(0, 0, 0), p(4, 0, 0), p(0, 4, 0))
    above = (p(1, 1, 2), p(F(11, 10), 1, 2), p(1, F(11, 10), 2))
    assert triangle_distance_squared(face, above) == F(4)

    edge_triangle = (p(0, 0, 0), p(2, 0, 0), p(0, 2, 0))
    nearby = (p(1, -1, 1), p(F(11, 10), F(-11, 10), 1), p(F(9, 10), F(-11, 10), 1))
    assert triangle_distance_squared(edge_triangle, nearby) == F(2)


def test_skew_edge_pair_with_interior_minimizers() -> None:
    first = (p(0, 0, 0), p(2, 0, 0), p(1, 1, 0))
    second = (p(1, -1, 1), p(1, 1, 1), p(2, 0, 2))
    assert triangle_distance_squared(first, second) == F(1)


def test_intersection_returns_zero_and_symmetry_is_invariant() -> None:
    first = (p(0, 0, 0), p(2, 0, 0), p(0, 2, 0))
    crossing = (p(1, -1, -1), p(1, 2, -1), p(1, 0, 2))
    assert triangle_distance_squared(first, crossing) == F(0)

    parallel = tuple(p(x, y, 1) for x, y, _ in first)
    expected = triangle_distance_squared(first, parallel)
    assert triangle_distance_squared(parallel, first) == expected
    assert triangle_distance_squared(first[1:] + first[:1], parallel[2:] + parallel[:2]) == expected
    assert triangle_distance_squared(tuple(reversed(first)), tuple(reversed(parallel))) == expected


def test_finite_binary64_extremes_and_rejects_bad_inputs() -> None:
    tiny = float.fromhex("0x0.0000000000001p-1022")
    first = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    second = ((0.0, 0.0, tiny), (1.0, 0.0, tiny), (0.0, 1.0, tiny))
    assert triangle_distance_squared(first, second) == F.from_float(tiny) ** 2

    degenerate = (p(0, 0, 0), p(1, 1, 1), p(2, 2, 2))
    with pytest.raises(ExactTriangleRelationError, match=r"triangle\.degenerate"):
        triangle_distance_squared(
            degenerate,
            (p(0, 0, 0), p(1, 0, 0), p(0, 1, 0)),
        )
    nonfinite = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, float("inf"), 0.0))
    with pytest.raises(ExactTriangleRelationError, match=r"coordinate\.must_be_fraction"):
        triangle_distance_squared(first, nonfinite)
