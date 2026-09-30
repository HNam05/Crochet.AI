"""Experimental exact distance outside a face-relative adjacent-triangle zone.

This kernel is exploratory and is not part of V0 or any passing profile.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction

from .exact_triangle_distance import triangle_distance_squared
from .exact_triangle_relation import (
    InputTriangle,
    Point,
    Triangle,
    TriangleRelationKind,
    triangle_relation,
)

EXPERIMENTAL_ZONE_VERSION = "adjacent_face_relative_zone_v1"


@dataclass(frozen=True, slots=True)
class AdjacentResidualDiagnostic:
    status: str
    zone_version: str
    shared_entity: str
    lambda_value: Fraction
    evaluated_piece_pairs: int


@dataclass(frozen=True, slots=True)
class AdjacentTriangleResidual:
    distance_squared: Fraction
    diagnostic: AdjacentResidualDiagnostic


class AdjacentTriangleResidualError(ValueError):
    """Invalid adjacency, unexpected contact, or exhausted explicit budget."""


def adjacent_triangle_residual_squared(
    first: InputTriangle,
    second: InputTriangle,
    *,
    shared_identity_indices: tuple[tuple[int, int], ...],
    lambda_value: Fraction,
    max_piece_pairs: int,
) -> AdjacentTriangleResidual:
    """Return exact distance where at least one face point is retained.

    ``shared_identity_indices`` maps each shared vertex index in ``first`` to
    its corresponding index in ``second``. Coordinates must be exactly equal.
    The lambda zone is dimensionless and relative to each face's barycentric
    coordinates. The compared set is ``(R_A x B) union (A x R_B)`` where
    ``R`` is the closed complement of the open local exclusion zone. No
    physical clearance is implied.
    """
    if not isinstance(lambda_value, Fraction) or not 0 < lambda_value < 1:
        raise AdjacentTriangleResidualError("lambda.must_be_fraction_strictly_between_zero_and_one")
    if (
        isinstance(max_piece_pairs, bool)
        or not isinstance(max_piece_pairs, int)
        or max_piece_pairs <= 0
    ):
        raise AdjacentTriangleResidualError("max_piece_pairs.must_be_positive_integer")
    a = _exact_triangle(first)
    b = _exact_triangle(second)
    if not isinstance(shared_identity_indices, tuple) or len(shared_identity_indices) not in (1, 2):
        raise AdjacentTriangleResidualError("shared_entity.requires_one_or_two_index_pairs")
    pairs = shared_identity_indices
    if any(
        not isinstance(pair, tuple) or len(pair) != 2
        or any(isinstance(i, bool) or not isinstance(i, int) or i not in range(3) for i in pair)
        for pair in pairs
    ):
        raise AdjacentTriangleResidualError("shared_entity.indices_must_be_triangle_indices")
    if len({i for i, _ in pairs}) != len(pairs) or len({j for _, j in pairs}) != len(pairs):
        raise AdjacentTriangleResidualError("shared_entity.indices_must_be_unique")
    if any(a[i] != b[j] for i, j in pairs):
        raise AdjacentTriangleResidualError("shared_entity.coordinates_must_match_exactly")

    relation = triangle_relation(a, b)
    allowed = _shared_simplex(a, pairs)
    if any(not _in_simplex(point, allowed) for point in relation.witnesses):
        raise AdjacentTriangleResidualError(
            "triangle_relation.has_contact_beyond_declared_shared_entity"
        )
    if relation.kind is TriangleRelationKind.COPLANAR_AREA:
        raise AdjacentTriangleResidualError("triangle_relation.has_positive_area_overlap")

    keep_a = _retained_pieces(a, tuple(i for i, _ in pairs), lambda_value)
    keep_b = _retained_pieces(b, tuple(j for _, j in pairs), lambda_value)
    pair_count = len(keep_a) * 1 + 1 * len(keep_b)
    if pair_count > max_piece_pairs:
        raise AdjacentTriangleResidualError("piece_pair_budget_exceeded")
    distances = [
        triangle_distance_squared(piece_a, piece_b)
        for piece_a in keep_a
        for piece_b in (b,)
    ]
    distances.extend(
        triangle_distance_squared(piece_a, piece_b)
        for piece_a in (a,)
        for piece_b in keep_b
    )
    distance = min(distances)
    return AdjacentTriangleResidual(
        distance,
        AdjacentResidualDiagnostic(
            "EXPERIMENTAL", EXPERIMENTAL_ZONE_VERSION,
            "shared_edge" if len(pairs) == 2 else "shared_vertex",
            lambda_value, pair_count,
        ),
    )


def _exact_triangle(value: InputTriangle) -> Triangle:
    # The public exact relation API performs canonical exact input validation.
    triangle_relation(value, value)
    return (_exact_point(value[0]), _exact_point(value[1]), _exact_point(value[2]))


def _exact_point(point: tuple[Fraction | float, ...]) -> Point:
    return (
        point[0] if isinstance(point[0], Fraction) else Fraction.from_float(point[0]),
        point[1] if isinstance(point[1], Fraction) else Fraction.from_float(point[1]),
        point[2] if isinstance(point[2], Fraction) else Fraction.from_float(point[2]),
    )


def _shared_simplex(triangle: Triangle, pairs: tuple[tuple[int, int], ...]) -> tuple[Point, ...]:
    return tuple(triangle[i] for i, _ in pairs)


def _in_simplex(point: Point, simplex: tuple[Point, ...]) -> bool:
    if len(simplex) == 1:
        return point == simplex[0]
    direction = tuple(simplex[1][i] - simplex[0][i] for i in range(3))
    delta = tuple(point[i] - simplex[0][i] for i in range(3))
    axis = next((i for i, value in enumerate(direction) if value), None)
    if axis is None:
        return point == simplex[0]
    t = delta[axis] / direction[axis]
    return 0 <= t <= 1 and all(delta[i] == t * direction[i] for i in range(3))


def _retained_pieces(
    triangle: Triangle, shared_indices: tuple[int, ...], threshold: Fraction,
) -> tuple[Triangle, ...]:
    bary = [(Fraction(i == 0), Fraction(i == 1), Fraction(i == 2)) for i in range(3)]
    if len(shared_indices) == 2:
        opposite = next(i for i in range(3) if i not in shared_indices)
        polygon = _clip(bary, lambda p: p[opposite] - threshold)
    else:
        shared = shared_indices[0]
        polygon = _clip(bary, lambda p: 1 - p[shared] - threshold)
    world = tuple(_from_bary(triangle, p) for p in polygon)
    return tuple((world[0], world[i], world[i + 1]) for i in range(1, len(world) - 1))


def _clip(
    polygon: list[tuple[Fraction, Fraction, Fraction]],
    signed: Callable[[tuple[Fraction, Fraction, Fraction]], Fraction],
) -> list[tuple[Fraction, Fraction, Fraction]]:
    result: list[tuple[Fraction, Fraction, Fraction]] = []
    previous = polygon[-1]
    prev_value = signed(previous)
    for current in polygon:
        curr_value = signed(current)
        if (curr_value >= 0) != (prev_value >= 0):
            ratio = prev_value / (prev_value - curr_value)
            result.append((
                previous[0] + ratio * (current[0] - previous[0]),
                previous[1] + ratio * (current[1] - previous[1]),
                previous[2] + ratio * (current[2] - previous[2]),
            ))
        if curr_value >= 0:
            result.append(current)
        previous, prev_value = current, curr_value
    return result


def _from_bary(triangle: Triangle, bary: tuple[Fraction, Fraction, Fraction]) -> Point:
    return (
        sum((bary[j] * triangle[j][0] for j in range(3)), Fraction(0)),
        sum((bary[j] * triangle[j][1] for j in range(3)), Fraction(0)),
        sum((bary[j] * triangle[j][2] for j in range(3)), Fraction(0)),
    )
