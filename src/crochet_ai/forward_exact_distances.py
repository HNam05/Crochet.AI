"""Exact pairwise distances for experimental initial triangle coordinates.

This diagnostic exhaustively evaluates nonadjacent face pairs using the exact
rational values represented by the input binary64 coordinates. It makes no
collision, clearance, convergence, or V6 claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from typing import Any

from .canonical import jcs_bytes
from .forward_aabb_broadphase import (
    ForwardAABBBroadphaseError,
    _validate_forward_inputs,
)
from .forward_cells import ForwardSurfaceCells
from .forward_exact_intersections import (
    ForwardExactIntersectionError,
    Point,
    Triangle,
    _exact_zero_area,
    _triangle_intersections,
)
from .forward_initialization import ForwardInitialization
from .forward_inputs import ForwardInputs
from .forward_triangle_geometry import (
    ForwardTriangleGeometryError,
    validate_initial_geometry_inputs,
)
from .forward_triangulation import ForwardSurfaceTriangulation

PROFILE = "FORWARD_INITIAL_EXACT_DISTANCES_V1"


class ForwardExactDistanceError(ValueError):
    """Malformed provenance, unsupported geometry, or deterministic budget failure."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ForwardExactDistanceDiagnostic:
    status: str
    source_triangulation_sha256: str
    initialization_sha256: str
    projection_sha256: str
    material_sha256: str
    forward_inputs_sha256: str
    all_pair_count: int
    nonadjacent_pair_count: int
    minimum_squared_distance_numerator: str | None
    minimum_squared_distance_denominator: str | None
    minimizing_face_pairs: tuple[tuple[int, int], ...]
    canonical_bytes: bytes
    sha256: str


def diagnose_initial_exact_distances(
    source: ForwardSurfaceCells,
    triangulation: ForwardSurfaceTriangulation,
    initialization: ForwardInitialization,
    inputs: ForwardInputs,
) -> ForwardExactDistanceDiagnostic:
    """Compute the exact minimum squared distance over all nonadjacent pairs.

    Pair work is admitted upfront as ``n * (n - 1) // 2`` against the existing
    ``max_contact_pairs_evaluated`` input budget. The algorithm has no geometric
    tolerance; every returned squared distance is in exact mm².
    """
    if not isinstance(inputs, ForwardInputs):
        raise ForwardExactDistanceError("distance.forward_inputs_type")
    try:
        _validate_forward_inputs(inputs)
        coordinates_float = validate_initial_geometry_inputs(source, triangulation, initialization)
    except (
        ForwardAABBBroadphaseError,
        ForwardTriangleGeometryError,
        TypeError,
        ValueError,
    ) as error:
        raise ForwardExactDistanceError("distance.input_integrity") from error
    if source.projection_sha256 != initialization.projection_sha256:
        raise ForwardExactDistanceError("distance.projection_binding_mismatch")
    if source.material_sha256 != initialization.material_sha256:
        raise ForwardExactDistanceError("distance.material_binding_mismatch")
    if initialization.forward_inputs_sha256 != inputs.sha256:
        raise ForwardExactDistanceError("distance.forward_inputs_binding_mismatch")

    face_count = len(triangulation.triangles)
    all_pair_count = face_count * (face_count - 1) // 2
    if all_pair_count > inputs.max_contact_pairs_evaluated:
        raise ForwardExactDistanceError("distance.pair_budget_exhausted")

    coordinates: dict[str, Point] = {
        identifier: (
            Fraction.from_float(point[0]),
            Fraction.from_float(point[1]),
            Fraction.from_float(point[2]),
        )
        for identifier, point in coordinates_float.items()
    }
    triangles: list[Triangle] = []
    for face in triangulation.triangles:
        try:
            ids = face.attachment_location_ids
            triangle: Triangle = (coordinates[ids[0]], coordinates[ids[1]], coordinates[ids[2]])
        except KeyError as error:
            raise ForwardExactDistanceError("distance.coordinate_missing") from error
        if _exact_zero_area(triangle):
            raise ForwardExactDistanceError("distance.exact_zero_area_triangle")
        triangles.append(triangle)

    nonadjacent_count = 0
    minimum: Fraction | None = None
    minimizing: list[tuple[int, int]] = []
    for first_index, first in enumerate(triangulation.triangles):
        first_ids = set(first.attachment_location_ids)
        for second_index in range(first_index + 1, face_count):
            second = triangulation.triangles[second_index]
            shared_count = len(first_ids & set(second.attachment_location_ids))
            if shared_count > 2:
                raise ForwardExactDistanceError("distance.shared_simplex_invalid")
            if shared_count in (1, 2):
                continue
            nonadjacent_count += 1
            first_triangle, second_triangle = triangles[first_index], triangles[second_index]
            try:
                distance = _pair_distance_squared(first_triangle, second_triangle)
            except (ArithmeticError, ForwardExactIntersectionError) as error:
                raise ForwardExactDistanceError("distance.exact_intersection_failed") from error
            pair = (first_index, second_index)
            if minimum is None or distance < minimum:
                minimum = distance
                minimizing = [pair]
            elif distance == minimum:
                minimizing.append(pair)

    numerator = None if minimum is None else str(minimum.numerator)
    denominator = None if minimum is None else str(minimum.denominator)
    minimizing_pairs = tuple(minimizing)
    payload: dict[str, Any] = {
        "profile": PROFILE,
        "status": "DISTANCE_DIAGNOSTIC_ONLY",
        "source_triangulation_sha256": triangulation.sha256,
        "initialization_sha256": initialization.sha256,
        "projection_sha256": source.projection_sha256,
        "material_sha256": source.material_sha256,
        "forward_inputs_sha256": inputs.sha256,
        "max_contact_pairs_evaluated": inputs.max_contact_pairs_evaluated,
        "all_pair_count": all_pair_count,
        "nonadjacent_pair_count": nonadjacent_count,
        "minimum_squared_distance_mm2": (
            None if minimum is None else {"numerator": numerator, "denominator": denominator}
        ),
        "minimizing_face_pairs": [list(pair) for pair in minimizing_pairs],
        "limitations": [
            "exact_initial_coordinate_distance_only_no_clearance_or_contact_threshold",
            "initial_coordinates_are_not_converged_and_do_not_establish_collision_free_geometry",
            "diagnostic_is_not_f0_converged_or_v6",
        ],
    }
    encoded = jcs_bytes(payload)
    digest = sha256(b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + encoded).hexdigest()
    return ForwardExactDistanceDiagnostic(
        "DISTANCE_DIAGNOSTIC_ONLY",
        triangulation.sha256,
        initialization.sha256,
        source.projection_sha256,
        source.material_sha256,
        inputs.sha256,
        all_pair_count,
        nonadjacent_count,
        numerator,
        denominator,
        minimizing_pairs,
        encoded,
        digest,
    )


def _triangle_distance_squared(first: Triangle, second: Triangle) -> Fraction:
    candidates = [_point_triangle_distance_squared(point, second) for point in first] + [
        _point_triangle_distance_squared(point, first) for point in second
    ]
    for first_index in range(3):
        first_edge = (first[first_index], first[(first_index + 1) % 3])
        for second_index in range(3):
            second_edge = (second[second_index], second[(second_index + 1) % 3])
            candidates.append(_segment_segment_distance_squared(first_edge, second_edge))
    return min(candidates)


def _pair_distance_squared(first: Triangle, second: Triangle) -> Fraction:
    """Return zero on exact intersection, otherwise the exact surface distance."""
    if _triangle_intersections(first, second):
        return Fraction(0)
    return _triangle_distance_squared(first, second)


def _point_triangle_distance_squared(point: Point, triangle: Triangle) -> Fraction:
    a, b, c = triangle
    ab, ac, ap = _sub(b, a), _sub(c, a), _sub(point, a)
    d00, d01, d11 = _dot(ab, ab), _dot(ab, ac), _dot(ac, ac)
    d20, d21 = _dot(ap, ab), _dot(ap, ac)
    denominator = d00 * d11 - d01 * d01
    if denominator <= 0:
        raise ForwardExactDistanceError("distance.triangle_projection_undefined")
    v = (d11 * d20 - d01 * d21) / denominator
    w = (d00 * d21 - d01 * d20) / denominator
    if v >= 0 and w >= 0 and v + w <= 1:
        projected = _add_scaled(_add_scaled(a, ab, v), ac, w)
        return _distance_squared(point, projected)
    edges = tuple((triangle[i], triangle[(i + 1) % 3]) for i in range(3))
    return min(_point_segment_distance_squared(point, edge) for edge in edges)


def _point_segment_distance_squared(point: Point, segment: tuple[Point, Point]) -> Fraction:
    start, end = segment
    direction = _sub(end, start)
    length_squared = _dot(direction, direction)
    if length_squared == 0:
        return _distance_squared(point, start)
    parameter = min(
        Fraction(1),
        max(Fraction(0), _dot(_sub(point, start), direction) / length_squared),
    )
    return _distance_squared(point, _add_scaled(start, direction, parameter))


def _segment_segment_distance_squared(
    first: tuple[Point, Point], second: tuple[Point, Point]
) -> Fraction:
    p0, p1 = first
    q0, q1 = second
    u, v, w = _sub(p1, p0), _sub(q1, q0), _sub(p0, q0)
    a, b, c = _dot(u, u), _dot(u, v), _dot(v, v)
    d, e = _dot(u, w), _dot(v, w)
    candidates = [
        _point_segment_distance_squared(p0, second),
        _point_segment_distance_squared(p1, second),
        _point_segment_distance_squared(q0, first),
        _point_segment_distance_squared(q1, first),
    ]
    determinant = a * c - b * b
    if determinant > 0:
        s = (b * e - c * d) / determinant
        t = (a * e - b * d) / determinant
        if 0 <= s <= 1 and 0 <= t <= 1:
            candidates.append(_distance_squared(_add_scaled(p0, u, s), _add_scaled(q0, v, t)))
    return min(candidates)


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add_scaled(a: Point, b: Point, scale: Fraction) -> Point:
    return (a[0] + scale * b[0], a[1] + scale * b[1], a[2] + scale * b[2])


def _dot(a: Point, b: Point) -> Fraction:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _distance_squared(a: Point, b: Point) -> Fraction:
    delta = _sub(a, b)
    return _dot(delta, delta)
