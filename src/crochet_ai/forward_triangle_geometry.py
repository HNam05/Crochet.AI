"""Target-free area and shape diagnostics for an experimental initial embedding.

This module reports arithmetic measurements only. It is not a simulation,
convergence check, collision check, or verification gate.
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from typing import Any

from .canonical import jcs_bytes
from .forward_cells import ForwardSurfaceCells
from .forward_initialization import PROFILE as INITIALIZATION_PROFILE
from .forward_initialization import ForwardInitialization
from .forward_triangulation import (
    ForwardSurfaceTriangulation,
    ForwardTriangulationError,
    triangulate_forward_surface_cells,
)

PROFILE = "FORWARD_INITIAL_TRIANGLE_GEOMETRY_V1"


class ForwardTriangleGeometryError(ValueError):
    """An artifact binding or coordinate calculation is invalid/undefined."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class TriangleGeometryMetric:
    """Area and scale-free shape metric for one source-ordered face."""

    source_lower_course_id: str
    source_upper_course_id: str
    source_cell_ordinal: int
    triangle_index: int
    attachment_location_ids: tuple[str, str, str]
    area_mm2: float
    shape_quality: float


@dataclass(frozen=True, slots=True)
class ForwardTriangleGeometryDiagnostic:
    """Immutable initial-coordinate diagnostic with exact input provenance."""

    status: str
    source_triangulation_sha256: str
    initialization_sha256: str
    projection_sha256: str
    material_sha256: str
    triangles: tuple[TriangleGeometryMetric, ...]
    canonical_bytes: bytes
    sha256: str


def diagnose_initial_triangle_geometry(
    source: ForwardSurfaceCells,
    triangulation: ForwardSurfaceTriangulation,
    initialization: ForwardInitialization,
) -> ForwardTriangleGeometryDiagnostic:
    """Measure every triangulated face at the supplied experimental coordinates.

    The function accepts no target geometry. It rejects malformed/tampered
    artifacts and does not apply any physical near-degeneracy threshold.
    """

    if not isinstance(source, ForwardSurfaceCells):
        raise ForwardTriangleGeometryError("triangle_geometry.source_type")
    if not isinstance(triangulation, ForwardSurfaceTriangulation):
        raise ForwardTriangleGeometryError("triangle_geometry.triangulation_type")
    if not isinstance(initialization, ForwardInitialization):
        raise ForwardTriangleGeometryError("triangle_geometry.initialization_type")
    if source.status != "EXPERIMENTAL_TOPOLOGY":
        raise ForwardTriangleGeometryError("triangle_geometry.source_status")
    if triangulation.status != "EXPERIMENTAL_TOPOLOGY":
        raise ForwardTriangleGeometryError("triangle_geometry.triangulation_status")
    if initialization.status != "EXPERIMENTAL_INITIALIZATION":
        raise ForwardTriangleGeometryError("triangle_geometry.initialization_status")

    try:
        expected_triangulation = triangulate_forward_surface_cells(source)
    except (ForwardTriangulationError, TypeError, ValueError) as error:
        raise ForwardTriangleGeometryError("triangle_geometry.source_integrity") from error
    if triangulation != expected_triangulation:
        raise ForwardTriangleGeometryError("triangle_geometry.triangulation_mismatch")
    if triangulation.source_cells_sha256 != source.sha256:
        raise ForwardTriangleGeometryError("triangle_geometry.source_hash_mismatch")

    if not _is_sha256(initialization.projection_sha256):
        raise ForwardTriangleGeometryError("triangle_geometry.provenance_hash_invalid")
    if initialization.projection_sha256 != source.projection_sha256:
        raise ForwardTriangleGeometryError("triangle_geometry.projection_mismatch")
    if initialization.material_sha256 != source.material_sha256:
        raise ForwardTriangleGeometryError("triangle_geometry.material_mismatch")
    if not _is_sha256(initialization.material_sha256) or not _is_sha256(
        initialization.forward_inputs_sha256
    ):
        raise ForwardTriangleGeometryError("triangle_geometry.provenance_hash_invalid")

    _validate_initialization_integrity(initialization)
    coordinates = _coordinates(initialization)
    metrics: list[TriangleGeometryMetric] = []
    for triangle in triangulation.triangles:
        try:
            points = tuple(
                coordinates[identifier] for identifier in triangle.attachment_location_ids
            )
        except KeyError as error:
            raise ForwardTriangleGeometryError("triangle_geometry.coordinate_missing") from error
        area, quality = _triangle_metrics(points)
        metrics.append(
            TriangleGeometryMetric(
                triangle.source_lower_course_id,
                triangle.source_upper_course_id,
                triangle.source_cell_ordinal,
                triangle.triangle_index,
                triangle.attachment_location_ids,
                area,
                quality,
            )
        )

    payload: dict[str, Any] = {
        "profile": PROFILE,
        "status": "INITIAL_COORDINATE_DIAGNOSTIC_ONLY",
        "source_triangulation_sha256": triangulation.sha256,
        "initialization_sha256": initialization.sha256,
        "projection_sha256": source.projection_sha256,
        "material_sha256": source.material_sha256,
        "limitations": [
            "positive_area_does_not_certify_robust_geometric_nondegeneracy",
            "does_not_claim_convergence_contact_collision_volume_or_outward_orientation",
        ],
        "triangles": [
            {
                "source_lower_course_id": metric.source_lower_course_id,
                "source_upper_course_id": metric.source_upper_course_id,
                "source_cell_ordinal": metric.source_cell_ordinal,
                "triangle_index": metric.triangle_index,
                "attachment_location_ids": list(metric.attachment_location_ids),
                "area_mm2": metric.area_mm2,
                "shape_quality": metric.shape_quality,
            }
            for metric in metrics
        ],
    }
    encoded = jcs_bytes(payload)
    digest = sha256(b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + encoded).hexdigest()
    return ForwardTriangleGeometryDiagnostic(
        "INITIAL_COORDINATE_DIAGNOSTIC_ONLY",
        triangulation.sha256,
        initialization.sha256,
        source.projection_sha256,
        source.material_sha256,
        tuple(metrics),
        encoded,
        digest,
    )


def _validate_initialization_integrity(initialization: ForwardInitialization) -> None:
    if not isinstance(initialization.anchor_location_groups, tuple) or any(
        not isinstance(group, tuple)
        or any(not isinstance(identifier, str) or not identifier for identifier in group)
        for group in initialization.anchor_location_groups
    ):
        raise ForwardTriangleGeometryError("triangle_geometry.initialization_integrity")
    if not isinstance(initialization.coordinates_mm, tuple):
        raise ForwardTriangleGeometryError("triangle_geometry.coordinates_invalid")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in initialization.coordinates_mm:
        if not isinstance(row, tuple) or len(row) != 2:
            raise ForwardTriangleGeometryError("triangle_geometry.coordinates_invalid")
        identifier, point = row
        if not isinstance(identifier, str) or not identifier:
            raise ForwardTriangleGeometryError("triangle_geometry.coordinates_invalid")
        if identifier in seen:
            raise ForwardTriangleGeometryError("triangle_geometry.coordinate_duplicate")
        if not isinstance(point, tuple) or len(point) != 3:
            raise ForwardTriangleGeometryError("triangle_geometry.coordinates_invalid")
        if any(not _finite_number(value) for value in point):
            raise ForwardTriangleGeometryError("triangle_geometry.coordinate_non_finite")
        seen.add(identifier)
        rows.append({"attachment_location_id": identifier, "xyz_mm": [float(v) for v in point]})
    payload: dict[str, Any] = {
        "profile": INITIALIZATION_PROFILE,
        "status": initialization.status,
        "projection_sha256": initialization.projection_sha256,
        "material_sha256": initialization.material_sha256,
        "forward_inputs_sha256": initialization.forward_inputs_sha256,
        "anchor_location_groups": [list(group) for group in initialization.anchor_location_groups],
        "coordinates_mm": rows,
    }
    try:
        encoded = jcs_bytes(payload)
    except (TypeError, ValueError) as error:
        raise ForwardTriangleGeometryError("triangle_geometry.initialization_integrity") from error
    expected_hash = sha256(
        b"Crochet.AI\0" + INITIALIZATION_PROFILE.encode("ascii") + b"\0" + encoded
    ).hexdigest()
    if (
        not isinstance(initialization.canonical_bytes, bytes)
        or encoded != initialization.canonical_bytes
        or expected_hash != initialization.sha256
    ):
        raise ForwardTriangleGeometryError("triangle_geometry.initialization_integrity")


def _coordinates(
    initialization: ForwardInitialization,
) -> dict[str, tuple[float, float, float]]:
    result: dict[str, tuple[float, float, float]] = {}
    for identifier, point in initialization.coordinates_mm:
        result[identifier] = (float(point[0]), float(point[1]), float(point[2]))
    return result


def _triangle_metrics(
    points: tuple[tuple[float, float, float], ...],
) -> tuple[float, float]:
    a, b, c = points
    ab = tuple(b[index] - a[index] for index in range(3))
    ac = tuple(c[index] - a[index] for index in range(3))
    bc = tuple(c[index] - b[index] for index in range(3))
    if any(not math.isfinite(value) for vector in (ab, ac, bc) for value in vector):
        raise ForwardTriangleGeometryError("triangle_geometry.arithmetic_overflow")
    edge = max(math.hypot(*ab), math.hypot(*ac), math.hypot(*bc))
    if not math.isfinite(edge):
        raise ForwardTriangleGeometryError("triangle_geometry.arithmetic_overflow")
    if edge == 0.0:
        raise ForwardTriangleGeometryError("triangle_geometry.zero_area")

    # Normalize before the cross product to avoid squaring large coordinates.
    u = tuple(value / edge for value in ab)
    v = tuple(value / edge for value in ac)
    cross = (
        u[1] * v[2] - u[2] * v[1],
        u[2] * v[0] - u[0] * v[2],
        u[0] * v[1] - u[1] * v[0],
    )
    quality = math.hypot(*cross)
    if not math.isfinite(quality):
        raise ForwardTriangleGeometryError("triangle_geometry.arithmetic_overflow")
    if quality == 0.0:
        if _exactly_collinear(a, b, c):
            raise ForwardTriangleGeometryError("triangle_geometry.zero_area")
        raise ForwardTriangleGeometryError("triangle_geometry.area_indeterminate")
    if quality > 1.0 + 16.0 * math.ulp(1.0):
        raise ForwardTriangleGeometryError("triangle_geometry.arithmetic_indeterminate")
    edge_mantissa, edge_exponent = math.frexp(edge)
    quality_mantissa, quality_exponent = math.frexp(quality)
    try:
        area = math.ldexp(
            0.5 * edge_mantissa * edge_mantissa * quality_mantissa,
            2 * edge_exponent + quality_exponent,
        )
    except OverflowError as error:
        raise ForwardTriangleGeometryError("triangle_geometry.arithmetic_overflow") from error
    if not math.isfinite(area):
        raise ForwardTriangleGeometryError("triangle_geometry.arithmetic_overflow")
    if area == 0.0 or area < sys.float_info.min:
        raise ForwardTriangleGeometryError("triangle_geometry.area_indeterminate")
    return area, quality


def _exactly_collinear(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    c: tuple[float, float, float],
) -> bool:
    ab = tuple(Fraction.from_float(b[i]) - Fraction.from_float(a[i]) for i in range(3))
    ac = tuple(Fraction.from_float(c[i]) - Fraction.from_float(a[i]) for i in range(3))
    return (
        ab[1] * ac[2] - ab[2] * ac[1] == 0
        and ab[2] * ac[0] - ab[0] * ac[2] == 0
        and ab[0] * ac[1] - ab[1] * ac[0] == 0
    )


def _finite_number(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
