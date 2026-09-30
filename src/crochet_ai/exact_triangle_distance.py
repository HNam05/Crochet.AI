"""Exact minimum squared distance between two nondegenerate 3D triangles."""

from __future__ import annotations

from fractions import Fraction
from math import isfinite

from .exact_triangle_relation import (
    ExactTriangleRelationError,
    InputPoint,
    InputTriangle,
    Point,
    Triangle,
    triangle_relation,
)


def triangle_distance_squared(first: InputTriangle, second: InputTriangle) -> Fraction:
    """Return exact minimum squared distance in mm² for two triangles.

    Coordinates are exact Fractions or finite binary64 values, interpreted as
    their exact rational values. Intersections and contacts return zero.
    """
    a = _exact_triangle(first)
    b = _exact_triangle(second)
    relation = triangle_relation(a, b)
    if relation.witnesses:
        return Fraction(0)
    candidates = [_point_triangle(point, b) for point in a]
    candidates.extend(_point_triangle(point, a) for point in b)
    for i in range(3):
        edge_a = (a[i], a[(i + 1) % 3])
        for j in range(3):
            edge_b = (b[j], b[(j + 1) % 3])
            candidates.append(_segment_segment(edge_a, edge_b))
    return min(candidates)


def _exact_triangle(triangle: InputTriangle) -> Triangle:
    try:
        if len(triangle) != 3:
            raise ExactTriangleRelationError("triangle.requires_three_vertices")
        return (_exact_point(triangle[0]), _exact_point(triangle[1]), _exact_point(triangle[2]))
    except (IndexError, TypeError) as error:
        raise ExactTriangleRelationError("triangle.invalid_shape") from error


def _exact_point(point: InputPoint) -> Point:
    if len(point) != 3:
        raise ExactTriangleRelationError("point.requires_three_coordinates")
    values_list: list[Fraction] = []
    for value in point:
        if isinstance(value, Fraction):
            values_list.append(value)
        elif isinstance(value, float) and isfinite(value):
            values_list.append(Fraction.from_float(value))
        else:
            raise ExactTriangleRelationError("coordinate.must_be_fraction_or_finite_float")
    values = tuple(values_list)
    return (values[0], values[1], values[2])


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add_scaled(a: Point, direction: Point, amount: Fraction) -> Point:
    return (
        a[0] + direction[0] * amount,
        a[1] + direction[1] * amount,
        a[2] + direction[2] * amount,
    )


def _dot(a: Point, b: Point) -> Fraction:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _squared_distance(a: Point, b: Point) -> Fraction:
    return _dot(_sub(a, b), _sub(a, b))


def _point_segment(point: Point, segment: tuple[Point, Point]) -> Fraction:
    start, end = segment
    direction = _sub(end, start)
    length_squared = _dot(direction, direction)
    parameter = Fraction(0) if length_squared == 0 else min(
        Fraction(1), max(Fraction(0), _dot(_sub(point, start), direction) / length_squared)
    )
    return _squared_distance(point, _add_scaled(start, direction, parameter))


def _point_triangle(point: Point, triangle: Triangle) -> Fraction:
    a, b, c = triangle
    ab, ac, ap = _sub(b, a), _sub(c, a), _sub(point, a)
    d00, d01, d11 = _dot(ab, ab), _dot(ab, ac), _dot(ac, ac)
    d20, d21 = _dot(ap, ab), _dot(ap, ac)
    denominator = d00 * d11 - d01 * d01
    if denominator <= 0:
        raise ExactTriangleRelationError("triangle.projection_undefined")
    v = (d11 * d20 - d01 * d21) / denominator
    w = (d00 * d21 - d01 * d20) / denominator
    if v >= 0 and w >= 0 and v + w <= 1:
        projection = _add_scaled(_add_scaled(a, ab, v), ac, w)
        return _squared_distance(point, projection)
    return min(
        _point_segment(point, (triangle[i], triangle[(i + 1) % 3])) for i in range(3)
    )


def _segment_segment(first: tuple[Point, Point], second: tuple[Point, Point]) -> Fraction:
    p0, p1 = first
    q0, q1 = second
    u, v, w = _sub(p1, p0), _sub(q1, q0), _sub(p0, q0)
    a, b, c = _dot(u, u), _dot(u, v), _dot(v, v)
    d, e = _dot(u, w), _dot(v, w)
    candidates = [
        _point_segment(p0, second),
        _point_segment(p1, second),
        _point_segment(q0, first),
        _point_segment(q1, first),
    ]
    determinant = a * c - b * b
    if determinant > 0:
        s = (b * e - c * d) / determinant
        t = (a * e - b * d) / determinant
        if 0 <= s <= 1 and 0 <= t <= 1:
            candidates.append(_squared_distance(_add_scaled(p0, u, s), _add_scaled(q0, v, t)))
    return min(candidates)
