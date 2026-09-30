"""Exact set relation for two nondegenerate triangles in three dimensions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from math import isfinite
from typing import TypeAlias

Point: TypeAlias = tuple[Fraction, Fraction, Fraction]
Triangle: TypeAlias = tuple[Point, Point, Point]
InputPoint: TypeAlias = tuple[Fraction | float, Fraction | float, Fraction | float]
InputTriangle: TypeAlias = tuple[InputPoint, InputPoint, InputPoint]


class TriangleRelationKind(StrEnum):
    DISJOINT = "DISJOINT"
    POINT = "POINT"
    SEGMENT = "SEGMENT"
    COPLANAR_AREA = "COPLANAR_AREA"


@dataclass(frozen=True, slots=True)
class TriangleRelation:
    """Intersection dimension with lexicographically sorted witness points.

    Area witnesses are a point set, not a boundary-ordered polygon.
    """

    kind: TriangleRelationKind
    witnesses: tuple[Point, ...]
    coplanar: bool


class ExactTriangleRelationError(ValueError):
    """An input is malformed, non-finite, or geometrically degenerate."""


def triangle_relation(first: InputTriangle, second: InputTriangle) -> TriangleRelation:
    """Return the exact intersection set dimension and deterministic witnesses.

    Float coordinates are interpreted as their exact binary64 values. No
    tolerance, contact policy, adjacency rule, or mesh-verification result is
    applied. The operation count is constant per pair, but big-integer cost
    depends on coordinate bit length. V0 callers use decoded binary64 values.
    """
    a = _triangle(first)
    b = _triangle(second)
    normal_a = _cross(_sub(a[1], a[0]), _sub(a[2], a[0]))
    normal_b = _cross(_sub(b[1], b[0]), _sub(b[2], b[0]))
    if normal_a == _zero() or normal_b == _zero():
        raise ExactTriangleRelationError("triangle.degenerate")

    distances_a = tuple(_dot(normal_b, _sub(point, b[0])) for point in a)
    distances_b = tuple(_dot(normal_a, _sub(point, a[0])) for point in b)
    if all(value == 0 for value in distances_a):
        return _coplanar_relation(a, b, normal_a)
    if all(value > 0 for value in distances_a) or all(value < 0 for value in distances_a):
        return TriangleRelation(TriangleRelationKind.DISJOINT, (), False)
    if all(value > 0 for value in distances_b) or all(value < 0 for value in distances_b):
        return TriangleRelation(TriangleRelationKind.DISJOINT, (), False)

    points = set(_plane_triangle_candidates(a, b, distances_a))
    points.update(_plane_triangle_candidates(b, a, distances_b))
    points = {point for point in points if _inside(point, a) and _inside(point, b)}
    return _classify(points, coplanar=False)


def _triangle(value: InputTriangle) -> Triangle:
    try:
        if len(value) != 3:
            raise ExactTriangleRelationError("triangle.requires_three_vertices")
        return (_point(value[0]), _point(value[1]), _point(value[2]))
    except (TypeError, IndexError) as error:
        raise ExactTriangleRelationError("triangle.invalid_shape") from error


def _point(value: InputPoint) -> Point:
    try:
        if len(value) != 3:
            raise ExactTriangleRelationError("point.requires_three_coordinates")
        converted: list[Fraction] = []
        for coordinate in value:
            if isinstance(coordinate, Fraction):
                converted.append(coordinate)
            elif isinstance(coordinate, float) and isfinite(coordinate):
                converted.append(Fraction.from_float(coordinate))
            else:
                raise ExactTriangleRelationError("coordinate.must_be_fraction_or_finite_float")
        return (converted[0], converted[1], converted[2])
    except (TypeError, IndexError) as error:
        raise ExactTriangleRelationError("point.invalid_shape") from error


def _zero() -> Point:
    return (Fraction(0), Fraction(0), Fraction(0))


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add_scaled(a: Point, direction: Point, amount: Fraction) -> Point:
    return (
        a[0] + direction[0] * amount,
        a[1] + direction[1] * amount,
        a[2] + direction[2] * amount,
    )


def _cross(a: Point, b: Point) -> Point:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a: Point, b: Point) -> Fraction:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _plane_triangle_candidates(source: Triangle, target: Triangle,
                               distances: tuple[Fraction, ...]) -> set[Point]:
    result: set[Point] = set()
    for index in range(3):
        start, end = source[index], source[(index + 1) % 3]
        d_start, d_end = distances[index], distances[(index + 1) % 3]
        if d_start == d_end == 0:
            result.update(_coplanar_edge_triangle(start, end, target))
        elif d_start == 0:
            if _inside(start, target):
                result.add(start)
        elif d_end == 0:
            if _inside(end, target):
                result.add(end)
        elif (d_start < 0 < d_end) or (d_end < 0 < d_start):
            point = _add_scaled(start, _sub(end, start), d_start / (d_start - d_end))
            if _inside(point, target):
                result.add(point)
    return result


def _project(point: Point, drop: int) -> tuple[Fraction, Fraction]:
    axes = tuple(axis for axis in range(3) if axis != drop)
    return point[axes[0]], point[axes[1]]


def _orient2(a: tuple[Fraction, Fraction], b: tuple[Fraction, Fraction],
             p: tuple[Fraction, Fraction]) -> Fraction:
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def _drop_axis(normal: Point) -> int:
    return max(range(3), key=lambda axis: abs(normal[axis]))


def _inside(point: Point, triangle: Triangle) -> bool:
    normal = _cross(_sub(triangle[1], triangle[0]), _sub(triangle[2], triangle[0]))
    drop = _drop_axis(normal)
    p = _project(point, drop)
    vertices = tuple(_project(vertex, drop) for vertex in triangle)
    signs = tuple(_orient2(vertices[i], vertices[(i + 1) % 3], p) for i in range(3))
    return all(value >= 0 for value in signs) or all(value <= 0 for value in signs)


def _coplanar_edge_triangle(start: Point, end: Point, triangle: Triangle) -> set[Point]:
    normal = _cross(_sub(triangle[1], triangle[0]), _sub(triangle[2], triangle[0]))
    drop = _drop_axis(normal)
    a, b = _project(start, drop), _project(end, drop)
    vertices = tuple(_project(vertex, drop) for vertex in triangle)
    orientation = _orient2(vertices[0], vertices[1], vertices[2])
    sign = Fraction(1) if orientation > 0 else Fraction(-1)
    low, high = Fraction(0), Fraction(1)
    direction = _sub(end, start)
    for i in range(3):
        edge_a, edge_b = vertices[i], vertices[(i + 1) % 3]
        initial = sign * _orient2(edge_a, edge_b, a)
        terminal = sign * _orient2(edge_a, edge_b, b)
        delta = terminal - initial
        if delta == 0:
            if initial < 0:
                return set()
            continue
        crossing = -initial / delta
        if delta > 0:
            low = max(low, crossing)
        else:
            high = min(high, crossing)
        if low > high:
            return set()
    return {_add_scaled(start, direction, low), _add_scaled(start, direction, high)}


def _coplanar_relation(first: Triangle, second: Triangle,
                       normal: Point) -> TriangleRelation:
    drop = _drop_axis(normal)
    polygon = list(first)
    clip = tuple(_project(point, drop) for point in second)
    clip_area = _orient2(clip[0], clip[1], clip[2])
    sign = Fraction(1) if clip_area > 0 else Fraction(-1)
    for index in range(3):
        edge_a, edge_b = clip[index], clip[(index + 1) % 3]
        if not polygon:
            break
        result: list[Point] = []
        previous = polygon[-1]
        previous_side = sign * _orient2(edge_a, edge_b, _project(previous, drop))
        for current in polygon:
            current_side = sign * _orient2(edge_a, edge_b, _project(current, drop))
            if (current_side >= 0) != (previous_side >= 0):
                fraction = previous_side / (previous_side - current_side)
                result.append(_add_scaled(previous, _sub(current, previous), fraction))
            if current_side >= 0:
                result.append(current)
            previous, previous_side = current, current_side
        polygon = _unique_cycle(result)
    return _classify(set(polygon), coplanar=True, drop=drop)


def _unique_cycle(points: list[Point]) -> list[Point]:
    result: list[Point] = []
    for point in points:
        if not result or point != result[-1]:
            result.append(point)
    if len(result) > 1 and result[0] == result[-1]:
        result.pop()
    return result


def _classify(points: set[Point], coplanar: bool, drop: int = 0) -> TriangleRelation:
    ordered = tuple(sorted(points))
    if not ordered:
        return TriangleRelation(TriangleRelationKind.DISJOINT, (), coplanar)
    if coplanar:
        projected = tuple(_project(point, drop) for point in ordered)
        if len(ordered) >= 3 and any(
            _orient2(projected[0], projected[i], projected[i + 1]) != 0
            for i in range(1, len(ordered) - 1)
        ):
            return TriangleRelation(TriangleRelationKind.COPLANAR_AREA, ordered, True)
        if len(ordered) > 2:
            ordered = _extremes(ordered, drop)
    if len(ordered) == 1:
        return TriangleRelation(TriangleRelationKind.POINT, ordered, coplanar)
    if any(point != ordered[0] for point in ordered[1:]):
        return TriangleRelation(TriangleRelationKind.SEGMENT, _extremes(ordered, drop), coplanar)
    return TriangleRelation(TriangleRelationKind.POINT, (ordered[0],), coplanar)


def _extremes(points: tuple[Point, ...], axis: int) -> tuple[Point, Point]:
    axis_values = [point[axis] for point in points]
    low_value, high_value = min(axis_values), max(axis_values)
    low = min(point for point in points if point[axis] == low_value)
    high = max(point for point in points if point[axis] == high_value)
    if low == high:
        return (low, low)
    return (low, high)
