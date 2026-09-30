"""Exact intersection-only diagnostics for experimental initial coordinates.

All predicates use the exact rational values represented by input binary64
coordinates. This is not a contact, penetration, collision-free, or V6 result.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from typing import Any

from .canonical import jcs_bytes
from .forward_aabb_broadphase import (
    ForwardAABBBroadphaseDiagnostic,
    ForwardAABBBroadphaseError,
    diagnose_initial_aabb_candidates,
)
from .forward_cells import ForwardSurfaceCells
from .forward_initialization import ForwardInitialization
from .forward_inputs import ForwardInputs
from .forward_triangulation import ForwardSurfaceTriangulation

PROFILE = "FORWARD_INITIAL_EXACT_INTERSECTIONS_V1"
Point = tuple[Fraction, Fraction, Fraction]
Triangle = tuple[Point, Point, Point]


class ForwardExactIntersectionError(ValueError):
    """Malformed provenance or unsupported exact input."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ExactIntersectionPair:
    first_face_index: int
    second_face_index: int
    shared_location_count: int
    intersection_point_count: int
    forbidden_intersection: bool


@dataclass(frozen=True, slots=True)
class ForwardExactIntersectionDiagnostic:
    status: str
    source_triangulation_sha256: str
    initialization_sha256: str
    projection_sha256: str
    material_sha256: str
    forward_inputs_sha256: str
    broadphase_sha256: str
    candidate_pair_count: int
    forbidden_pair_count: int
    pairs: tuple[ExactIntersectionPair, ...]
    canonical_bytes: bytes
    sha256: str


def diagnose_initial_exact_intersections(
    source: ForwardSurfaceCells,
    triangulation: ForwardSurfaceTriangulation,
    initialization: ForwardInitialization,
    inputs: ForwardInputs,
    broadphase: ForwardAABBBroadphaseDiagnostic | None = None,
) -> ForwardExactIntersectionDiagnostic:
    """Test every source-ordered inclusive AABB candidate with exact predicates."""
    try:
        recomputed = diagnose_initial_aabb_candidates(source, triangulation, initialization, inputs)
    except (
        ForwardAABBBroadphaseError,
        TypeError,
        ValueError,
    ) as error:
        raise ForwardExactIntersectionError("intersection.input_integrity") from error
    if broadphase is not None and broadphase != recomputed:
        raise ForwardExactIntersectionError("intersection.broadphase_mismatch")

    coordinates: dict[str, Point] = {}
    for identifier, xyz in initialization.coordinates_mm:
        coordinates[identifier] = (
            Fraction.from_float(float(xyz[0])),
            Fraction.from_float(float(xyz[1])),
            Fraction.from_float(float(xyz[2])),
        )
    triangles: list[Triangle] = []
    for row in triangulation.triangles:
        try:
            triangle: Triangle = (
                coordinates[row.attachment_location_ids[0]],
                coordinates[row.attachment_location_ids[1]],
                coordinates[row.attachment_location_ids[2]],
            )
        except KeyError as error:
            raise ForwardExactIntersectionError("intersection.coordinate_missing") from error
        if _exact_zero_area(triangle):
            raise ForwardExactIntersectionError("intersection.exact_zero_area_triangle")
        triangles.append(triangle)

    rows: list[ExactIntersectionPair] = []
    for candidate in recomputed.candidate_pairs:
        first_index, second_index = candidate.first_face_index, candidate.second_face_index
        first_ids = triangulation.triangles[first_index].attachment_location_ids
        second_ids = triangulation.triangles[second_index].attachment_location_ids
        shared = set(first_ids) & set(second_ids)
        if len(shared) > 2:
            raise ForwardExactIntersectionError("intersection.shared_simplex_invalid")
        intersection_points = _triangle_intersections(
            triangles[first_index], triangles[second_index]
        )
        forbidden = any(
            not _in_shared_simplex(point, shared, coordinates) for point in intersection_points
        )
        rows.append(ExactIntersectionPair(
            first_index, second_index, len(shared), len(intersection_points), forbidden
        ))

    payload: dict[str, Any] = {
        "profile": PROFILE,
        "status": "EXACT_INTERSECTION_DIAGNOSTIC_ONLY",
        "source_triangulation_sha256": triangulation.sha256,
        "initialization_sha256": initialization.sha256,
        "projection_sha256": source.projection_sha256,
        "material_sha256": source.material_sha256,
        "forward_inputs_sha256": inputs.sha256,
        "broadphase_sha256": recomputed.sha256,
        "candidate_pair_count": len(rows),
        "forbidden_pair_count": sum(row.forbidden_intersection for row in rows),
        "limitations": [
            "exact_binary_rational_intersection_only_no_distance_or_penetration",
            "initial_coordinates_are_not_converged_and_do_not_establish_collision_free_geometry",
            "diagnostic_is_not_f0_converged_or_v6",
        ],
        "pairs": [
            {
                "first_face_index": row.first_face_index,
                "second_face_index": row.second_face_index,
                "shared_location_count": row.shared_location_count,
                "intersection_point_count": row.intersection_point_count,
                "forbidden_intersection": row.forbidden_intersection,
            }
            for row in rows
        ],
    }
    encoded = jcs_bytes(payload)
    digest = sha256(b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + encoded).hexdigest()
    return ForwardExactIntersectionDiagnostic(
        "EXACT_INTERSECTION_DIAGNOSTIC_ONLY", triangulation.sha256, initialization.sha256,
        source.projection_sha256, source.material_sha256, inputs.sha256, recomputed.sha256,
        len(rows), sum(row.forbidden_intersection for row in rows), tuple(rows), encoded, digest,
    )


def _zero() -> Point:
    return (Fraction(0), Fraction(0), Fraction(0))


def _exact_zero_area(triangle: Triangle) -> bool:
    return _cross(_sub(triangle[1], triangle[0]), _sub(triangle[2], triangle[0])) == _zero()


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add_scaled(a: Point, b: Point, scale: Fraction) -> Point:
    return (a[0] + scale * b[0], a[1] + scale * b[1], a[2] + scale * b[2])


def _cross(a: Point, b: Point) -> Point:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a: Point, b: Point) -> Fraction:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _triangle_intersections(first: Triangle, second: Triangle) -> set[Point]:
    result: set[Point] = set()
    for source, target in ((first, second), (second, first)):
        normal = _cross(_sub(target[1], target[0]), _sub(target[2], target[0]))
        plane = tuple(_dot(normal, _sub(point, target[0])) for point in source)
        for index in range(3):
            a, b = source[index], source[(index + 1) % 3]
            da, db = plane[index], plane[(index + 1) % 3]
            if da == db == 0:
                result.update(_coplanar_segment_triangle(a, b, target))
            elif da == 0:
                if _inside_triangle(a, target):
                    result.add(a)
            elif db == 0:
                if _inside_triangle(b, target):
                    result.add(b)
            elif (da < 0 < db) or (db < 0 < da):
                point = _add_scaled(a, _sub(b, a), da / (da - db))
                if _inside_triangle(point, target):
                    result.add(point)
    return result


def _inside_triangle(point: Point, triangle: Triangle) -> bool:
    normal = _cross(_sub(triangle[1], triangle[0]), _sub(triangle[2], triangle[0]))
    for index in range(3):
        edge = _sub(triangle[(index + 1) % 3], triangle[index])
        side = _dot(_cross(edge, _sub(point, triangle[index])), normal)
        if side < 0:
            return False
    return True


def _coplanar_segment_triangle(a: Point, b: Point, triangle: Triangle) -> set[Point]:
    normal = _cross(_sub(triangle[1], triangle[0]), _sub(triangle[2], triangle[0]))
    low, high = Fraction(0), Fraction(1)
    for index in range(3):
        edge = _sub(triangle[(index + 1) % 3], triangle[index])
        start = _dot(_cross(edge, _sub(a, triangle[index])), normal)
        end = _dot(_cross(edge, _sub(b, triangle[index])), normal)
        delta = end - start
        if delta == 0:
            if start < 0:
                return set()
            continue
        boundary = -start / delta
        if delta > 0:
            low = max(low, boundary)
        else:
            high = min(high, boundary)
        if low > high:
            return set()
    return {_add_scaled(a, _sub(b, a), low), _add_scaled(a, _sub(b, a), high)}


def _in_shared_simplex(point: Point, shared: set[str], coordinates: dict[str, Point]) -> bool:
    if len(shared) == 0:
        return False
    vertices = [coordinates[identifier] for identifier in sorted(shared)]
    if len(vertices) == 1:
        return point == vertices[0]
    a, b = vertices
    direction = _sub(b, a)
    delta = _sub(point, a)
    if _cross(direction, delta) != _zero():
        return False
    axis = next(index for index, value in enumerate(direction) if value != 0)
    return min(a[axis], b[axis]) <= point[axis] <= max(a[axis], b[axis])
