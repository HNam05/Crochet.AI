from fractions import Fraction

import pytest

from crochet_ai.exact_triangle_relation import (
    ExactTriangleRelationError,
    triangle_relation,
)
from crochet_ai.exact_triangle_relation import TriangleRelationKind as Kind

F = Fraction


def p(x: int | Fraction, y: int | Fraction, z: int | Fraction) -> tuple[Fraction, ...]:
    return (F(x), F(y), F(z))


def relation(a, b):
    return triangle_relation(a, b)


def test_separated_and_coplanar_disjoint_triangles() -> None:
    base = (p(0, 0, 0), p(2, 0, 0), p(0, 2, 0))
    assert relation(base, tuple(p(x, y, 1) for x, y, _ in base)).kind is Kind.DISJOINT
    assert relation(base, (p(3, 3, 0), p(4, 3, 0), p(3, 4, 0))).kind is Kind.DISJOINT


def test_non_coplanar_point_and_segment_intersections() -> None:
    first = (p(0, 0, 0), p(2, 0, 0), p(0, 2, 0))
    point_triangle = (p(1, 1, 0), p(1, 0, 1), p(0, 1, 1))
    point_result = relation(first, point_triangle)
    assert (point_result.kind, point_result.witnesses, point_result.coplanar) == (
        Kind.POINT, (p(1, 1, 0),), False
    )

    crossing = (p(1, -1, -1), p(1, 2, -1), p(1, 0, 2))
    segment_result = relation(first, crossing)
    assert segment_result.kind is Kind.SEGMENT
    assert segment_result.witnesses == (p(1, 0, 0), p(1, 1, 0))
    assert not segment_result.coplanar


def test_coplanar_area_containment_partial_coincident_and_reversed() -> None:
    outer = (p(0, 0, 0), p(4, 0, 0), p(0, 4, 0))
    inner = (p(1, 1, 0), p(2, 1, 0), p(1, 2, 0))
    contained = relation(outer, inner)
    assert contained.kind is Kind.COPLANAR_AREA
    assert set(contained.witnesses) == set(inner)
    assert contained.coplanar

    partial = (p(2, 0, 0), p(4, 0, 0), p(2, 2, 0))
    overlap = relation(outer, partial)
    assert overlap.kind is Kind.COPLANAR_AREA
    assert set(overlap.witnesses) == {p(2, 0, 0), p(4, 0, 0), p(2, 2, 0)}

    coincident = tuple(reversed(outer))
    assert relation(outer, coincident).kind is Kind.COPLANAR_AREA
    assert relation(outer, coincident).witnesses == relation(coincident, outer).witnesses


def test_coplanar_segment_touch_and_shared_vertex() -> None:
    tri = (p(0, 0, 0), p(2, 0, 0), p(0, 2, 0))
    shared_edge = (p(0, 0, 0), p(2, 0, 0), p(1, -1, 0))
    edge = relation(tri, shared_edge)
    assert edge.kind is Kind.SEGMENT
    assert edge.witnesses == (p(0, 0, 0), p(2, 0, 0))
    assert edge.coplanar

    partial_edge = (p(F(1, 2), 0, 0), p(F(3, 2), 0, 0), p(1, -1, 0))
    partial = relation(tri, partial_edge)
    assert partial.kind is Kind.SEGMENT
    assert partial.witnesses == (p(F(1, 2), 0, 0), p(F(3, 2), 0, 0))

    edge_touch = (p(2, 0, 0), p(3, -1, 0), p(3, 1, 0))
    result = relation(tri, edge_touch)
    assert result.kind is Kind.POINT
    assert result.witnesses == (p(2, 0, 0),)
    assert result.coplanar

    vertex_touch = (p(2, 0, 0), p(3, 0, 1), p(3, 1, 1))
    vertex = relation(tri, vertex_touch)
    assert vertex.kind is Kind.POINT
    assert vertex.witnesses == (p(2, 0, 0),)


def test_noncoplanar_edge_in_other_plane_and_drop_axis_choices() -> None:
    base = (p(0, 0, 0), p(2, 0, 0), p(0, 2, 0))
    crossing_edge = (p(0, 0, 0), p(2, 0, 0), p(1, 0, 1))
    assert relation(base, crossing_edge).witnesses == (p(0, 0, 0), p(2, 0, 0))
    for permute in (
        lambda point: (point[1], point[2], point[0]),
        lambda point: (point[2], point[0], point[1]),
    ):
        left = tuple(permute(point) for point in base)
        right = tuple(permute(point) for point in crossing_edge)
        assert relation(left, right).kind is Kind.SEGMENT
        expected = tuple(sorted(permute(point) for point in (p(0, 0, 0), p(2, 0, 0))))
        assert relation(left, right).witnesses == expected


def test_symmetry_and_vertex_order_invariance() -> None:
    a = (p(0, 0, 0), p(3, 0, 0), p(0, 3, 0))
    b = (p(1, -1, -1), p(1, 3, -1), p(1, 0, 2))
    expected = relation(a, b)
    for left, right in ((b, a), (a[1:] + a[:1], b[2:] + b[:2]),
                        (tuple(reversed(a)), tuple(reversed(b)))):
        assert relation(left, right) == expected


def test_extreme_rationals_and_exact_float_boundary_conversion() -> None:
    tiny = F(1, 10**80)
    a = (p(0, 0, 0), p(tiny, 0, 0), p(0, tiny, 0))
    b = (p(0, 0, 0), p(tiny, 0, 1), p(0, tiny, 1))
    assert relation(a, b).kind is Kind.POINT
    floats = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))
    above = ((0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (0.0, 1.0, 1.0))
    assert relation(floats, above).kind is Kind.DISJOINT


def test_rejects_degenerate_and_non_finite_input() -> None:
    degenerate = (p(0, 0, 0), p(1, 1, 1), p(2, 2, 2))
    good = (p(0, 0, 0), p(1, 0, 0), p(0, 1, 0))
    with pytest.raises(ExactTriangleRelationError, match=r"triangle\.degenerate"):
        relation(degenerate, good)
    with pytest.raises(ExactTriangleRelationError, match=r"coordinate\.must_be_fraction"):
        relation(((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, float("inf"), 0.0)), good)
