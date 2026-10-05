"""Experimental target-free signed-dihedral bending for the admitted quad strip.

One hinge is placed on each canonical first-to-third quad diagonal. This is a
HYPOTHESIS energy term only; it is not calibrated, optimized, or V6 evidence.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import cast

from .canonical import jcs_bytes
from .forward_cells import ForwardSurfaceCells
from .forward_initialization import PROFILE as INITIALIZATION_PROFILE
from .forward_initialization import ForwardInitialization
from .forward_inputs import ForwardInputs
from .forward_triangulation import ForwardTriangulationError, triangulate_forward_surface_cells
from .json_types import JSONValue

PROFILE = "FORWARD_BENDING_HYPOTHESIS_V2"
TERMS_PROFILE = "FORWARD_BENDING_TERMS_V2"

# Arithmetic-domain guards, not physical clearances: 1e-12 mm excludes diagonals
# too small for stable normalization; 1e-24 mm^2 excludes similarly unstable face
# area vectors. The angular guards are 1e-12 rad to make the wrap branch explicit.
# These prototype guards are owned by this module and require scale studies before
# calibration or production use.
MIN_EDGE_LENGTH_MM = 1e-12
MIN_AREA_VECTOR_MM2 = 1e-24
MIN_TRIANGLE_QUALITY = 1e-10
ANGLE_BRANCH_TOLERANCE_RAD = 1e-12
Vec3 = tuple[float, float, float]


class ForwardBendingError(ValueError):
    """Invalid, unsupported, or numerically undefined bending input."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class BendingParameters:
    status: str
    provenance_id: str
    rest_dihedral_rad: float
    stiffness_n_mm: float
    canonical_bytes: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class BendingTerm:
    attachment_location_ids: tuple[str, str, str, str]
    rest_dihedral_rad: float
    stiffness_n_mm: float


@dataclass(frozen=True, slots=True)
class ForwardBendingTerms:
    status: str
    projection_sha256: str
    material_sha256: str
    forward_inputs_sha256: str
    cells_sha256: str
    initialization_sha256: str
    parameters_sha256: str
    terms: tuple[BendingTerm, ...]
    canonical_bytes: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class BendingEvaluation:
    energy_n_mm: float
    forces_n: tuple[tuple[str, tuple[float, float, float]], ...]
    maximum_force_n: float


def admit_bending_parameters(
    provenance_id: str, rest_dihedral_rad: float, stiffness_n_mm: float
) -> BendingParameters:
    """Admit declared rest angle and positive effective stiffness in N*mm."""
    if not isinstance(provenance_id, str) or not provenance_id.strip():
        raise ForwardBendingError("bending.provenance_invalid")
    rest_angle = _finite(rest_dihedral_rad, "rest_dihedral_invalid")
    stiffness = _finite(stiffness_n_mm, "stiffness_invalid")
    if not -math.pi <= rest_angle <= math.pi:
        raise ForwardBendingError("bending.rest_dihedral_invalid")
    if stiffness <= 0.0:
        raise ForwardBendingError("bending.stiffness_invalid")
    payload: dict[str, JSONValue] = {
        "profile": PROFILE,
        "status": "HYPOTHESIS",
        "provenance_id": provenance_id,
        "rest_dihedral_rad": rest_angle,
        "rest_dihedral_unit": "rad",
        "stiffness_n_mm": stiffness,
        "stiffness_unit": "N*mm",
    }
    encoded = jcs_bytes(payload)
    digest = _hash(PROFILE, encoded)
    return BendingParameters("HYPOTHESIS", provenance_id, rest_angle, stiffness, encoded, digest)


def prepare_bending_terms(
    cells: ForwardSurfaceCells,
    initialization: ForwardInitialization,
    parameters: BendingParameters,
    inputs: ForwardInputs,
) -> ForwardBendingTerms:
    """Create one declared-parameter hinge per validated source quad."""
    if not isinstance(cells, ForwardSurfaceCells):
        raise ForwardBendingError("bending.cells_invalid")
    if not isinstance(initialization, ForwardInitialization):
        raise ForwardBendingError("bending.initialization_invalid")
    if not isinstance(inputs, ForwardInputs):
        raise ForwardBendingError("bending.inputs_invalid")
    try:
        triangulate_forward_surface_cells(cells)
    except ForwardTriangulationError as error:
        raise ForwardBendingError(f"bending.{error.reason}") from error
    _validate_initialization(initialization)
    _validate_parameters(parameters)
    if (
        initialization.projection_sha256 != cells.projection_sha256
        or initialization.material_sha256 != cells.material_sha256
        or initialization.forward_inputs_sha256 != inputs.sha256
    ):
        raise ForwardBendingError("bending.source_binding_mismatch")
    coordinates = dict(initialization.coordinates_mm)
    if len(coordinates) > inputs.max_initialization_vertices:
        raise ForwardBendingError("bending.vertex_budget_exhausted")
    if len(cells.cells) > inputs.max_initialization_vertices:
        raise ForwardBendingError("bending.hinge_budget_exhausted")
    terms: list[BendingTerm] = []
    for cell in cells.cells:
        a, b, c, d = cell.attachment_location_ids
        if any(key not in coordinates for key in (a, b, c, d)):
            raise ForwardBendingError("bending.initialization_coordinate_missing")
        terms.append(
            BendingTerm((a, b, c, d), parameters.rest_dihedral_rad, parameters.stiffness_n_mm)
        )
    term_tuple = tuple(terms)
    payload = _terms_payload(cells, initialization, inputs, parameters, term_tuple)
    encoded = jcs_bytes(cast(JSONValue, payload))
    digest = _hash(TERMS_PROFILE, encoded)
    return ForwardBendingTerms(
        "EXPERIMENTAL_BENDING_TERMS",
        cells.projection_sha256,
        cells.material_sha256,
        inputs.sha256,
        cells.sha256,
        initialization.sha256,
        parameters.sha256,
        term_tuple,
        encoded,
        digest,
    )


def evaluate_bending_terms(
    terms: ForwardBendingTerms, coordinates_mm: Mapping[str, tuple[float, float, float]]
) -> BendingEvaluation:
    """Return E=K_eff*wrapped(delta_theta)^2 and negative-gradient forces."""
    _validate_terms(terms)
    if not isinstance(coordinates_mm, Mapping):
        raise ForwardBendingError("bending.coordinates_invalid")
    forces: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    energy_terms: list[float] = []
    for term in terms.terms:
        try:
            points = tuple(coordinates_mm[key] for key in term.attachment_location_ids)
        except (KeyError, TypeError) as error:
            raise ForwardBendingError("bending.coordinate_missing") from error
        _validate_points(points)
        angle = _dihedral(cast(tuple[Vec3, Vec3, Vec3, Vec3], points))
        delta = math.remainder(angle - term.rest_dihedral_rad, math.tau)
        if abs(abs(delta) - math.pi) <= ANGLE_BRANCH_TOLERANCE_RAD:
            raise ForwardBendingError("bending.angle_branch_ambiguous")
        coefficient = term.stiffness_n_mm
        energy_terms.append(coefficient * delta * delta)
        derivatives = _dihedral_gradient(cast(tuple[Vec3, Vec3, Vec3, Vec3], points))
        scale = -2.0 * coefficient * delta
        for key, gradient in zip(term.attachment_location_ids, derivatives, strict=True):
            for axis in range(3):
                forces[key][axis] += scale * gradient[axis]
    try:
        energy = math.fsum(energy_terms)
    except OverflowError as error:
        raise ForwardBendingError("bending.energy_non_finite") from error
    rows = tuple((key, tuple(values)) for key, values in sorted(forces.items()))
    if not math.isfinite(energy) or any(not math.isfinite(x) for _, row in rows for x in row):
        raise ForwardBendingError("bending.result_non_finite")
    maximum = max((math.hypot(*row) for _, row in rows), default=0.0)
    if not math.isfinite(maximum):
        raise ForwardBendingError("bending.result_non_finite")
    return BendingEvaluation(
        energy, cast(tuple[tuple[str, tuple[float, float, float]], ...], rows), maximum
    )


def _dihedral_gradient(points: tuple[Vec3, Vec3, Vec3, Vec3]) -> tuple[Vec3, Vec3, Vec3, Vec3]:
    """Forward-mode autodiff of atan2(edge dot (n1 x n2), n1 dot n2)."""
    # Each scalar carries its derivative in the twelve Cartesian input directions.
    variables = [
        _Dual(value, tuple(float(i == j) for i in range(12)))
        for j, value in enumerate(coordinate for point in points for coordinate in point)
    ]
    vectors = cast(
        list[tuple[_Dual, _Dual, _Dual]],
        [tuple(variables[3 * i : 3 * i + 3]) for i in range(4)],
    )
    a, b, c, d = vectors
    edge = _vsub(c, a)
    normal1 = _cross_dual(_vsub(b, a), edge)
    normal2 = _cross_dual(edge, _vsub(d, a))
    edge_length = _sqrt(_dot_dual(edge, edge))
    n1_length = _sqrt(_dot_dual(normal1, normal1))
    n2_length = _sqrt(_dot_dual(normal2, normal2))
    unit_edge = cast(tuple[_Dual, _Dual, _Dual], tuple(value / edge_length for value in edge))
    unit1 = cast(tuple[_Dual, _Dual, _Dual], tuple(value / n1_length for value in normal1))
    unit2 = cast(tuple[_Dual, _Dual, _Dual], tuple(value / n2_length for value in normal2))
    x = _dot_dual(unit1, unit2)
    y = _dot_dual(unit_edge, _cross_dual(unit1, unit2))
    denominator = x.value * x.value + y.value * y.value
    if denominator == 0.0 or not math.isfinite(denominator):
        raise ForwardBendingError("bending.angle_derivative_undefined")
    gradient = tuple(
        (x.value * y.gradient[i] - y.value * x.gradient[i]) / denominator for i in range(12)
    )
    if any(not math.isfinite(value) for value in gradient):
        raise ForwardBendingError("bending.gradient_non_finite")
    return cast(
        tuple[Vec3, Vec3, Vec3, Vec3],
        tuple(tuple(gradient[3 * i : 3 * i + 3]) for i in range(4)),
    )


@dataclass(frozen=True, slots=True)
class _Dual:
    value: float
    gradient: tuple[float, ...]

    def __add__(self, other: _Dual) -> _Dual:
        return _Dual(
            self.value + other.value,
            tuple(a + b for a, b in zip(self.gradient, other.gradient, strict=True)),
        )

    def __sub__(self, other: _Dual) -> _Dual:
        return _Dual(
            self.value - other.value,
            tuple(a - b for a, b in zip(self.gradient, other.gradient, strict=True)),
        )

    def __mul__(self, other: _Dual) -> _Dual:
        return _Dual(
            self.value * other.value,
            tuple(
                a * other.value + self.value * b
                for a, b in zip(self.gradient, other.gradient, strict=True)
            ),
        )

    def __truediv__(self, other: _Dual) -> _Dual:
        divisor = other.value * other.value
        return _Dual(
            self.value / other.value,
            tuple(
                (a * other.value - self.value * b) / divisor
                for a, b in zip(self.gradient, other.gradient, strict=True)
            ),
        )


def _dihedral(points: tuple[Vec3, Vec3, Vec3, Vec3]) -> float:
    a, b, c, d = points
    edge = _sub_float(c, a)
    length = _length(edge)
    normal1 = _cross_float(_sub_float(b, a), edge)
    normal2 = _cross_float(edge, _sub_float(d, a))
    area1, area2 = _length(normal1), _length(normal2)
    if length <= MIN_EDGE_LENGTH_MM:
        raise ForwardBendingError("bending.hinge_degenerate")
    if area1 <= MIN_AREA_VECTOR_MM2 or area2 <= MIN_AREA_VECTOR_MM2:
        raise ForwardBendingError("bending.face_degenerate")
    _validate_triangle_quality(area1, (a, b, c))
    _validate_triangle_quality(area2, (a, c, d))
    e = cast(Vec3, tuple(value / length for value in edge))
    n1 = cast(Vec3, tuple(value / area1 for value in normal1))
    n2 = cast(Vec3, tuple(value / area2 for value in normal2))
    x = math.fsum(n1[i] * n2[i] for i in range(3))
    y = math.fsum(e[i] * value for i, value in enumerate(_cross_float(n1, n2)))
    angle = math.atan2(y, x)
    if not math.isfinite(angle):
        raise ForwardBendingError("bending.angle_non_finite")
    return angle


def _validate_triangle_quality(
    area_vector_magnitude: float, points: tuple[Vec3, Vec3, Vec3]
) -> None:
    a, b, c = points
    maximum_edge = max(
        _length(_sub_float(b, a)),
        _length(_sub_float(c, b)),
        _length(_sub_float(a, c)),
    )
    if maximum_edge <= MIN_EDGE_LENGTH_MM:
        raise ForwardBendingError("bending.face_edge_degenerate")
    scale = maximum_edge * maximum_edge
    if not math.isfinite(scale) or scale <= 0.0:
        raise ForwardBendingError("bending.face_scale_non_finite")
    quality = area_vector_magnitude / scale
    if not math.isfinite(quality):
        raise ForwardBendingError("bending.face_quality_non_finite")
    if quality <= MIN_TRIANGLE_QUALITY:
        raise ForwardBendingError("bending.face_skinny")


def _validate_initialization(source: ForwardInitialization) -> None:
    if source.status != "EXPERIMENTAL_INITIALIZATION" or not _digest(source.sha256):
        raise ForwardBendingError("bending.initialization_status_invalid")
    if not all(
        _digest(value)
        for value in (
            source.projection_sha256,
            source.material_sha256,
            source.forward_inputs_sha256,
        )
    ):
        raise ForwardBendingError("bending.initialization_hash_invalid")
    if not isinstance(source.canonical_bytes, bytes):
        raise ForwardBendingError("bending.initialization_bytes_invalid")
    rows = source.coordinates_mm
    if not isinstance(rows, tuple) or any(
        not isinstance(row, tuple) or len(row) != 2 for row in rows
    ):
        raise ForwardBendingError("bending.initialization_coordinates_invalid")
    if tuple(sorted(rows)) != rows or len({key for key, _ in rows}) != len(rows):
        raise ForwardBendingError("bending.initialization_coordinate_order_invalid")
    if not isinstance(source.anchor_location_groups, tuple) or any(
        not isinstance(group, tuple)
        or not group
        or any(not isinstance(location_id, str) or not location_id for location_id in group)
        for group in source.anchor_location_groups
    ):
        raise ForwardBendingError("bending.initialization_anchors_invalid")
    for key, point in rows:
        if not isinstance(key, str) or not key or not isinstance(point, tuple) or len(point) != 3:
            raise ForwardBendingError("bending.initialization_coordinates_invalid")
        if any(
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            for value in point
        ):
            raise ForwardBendingError("bending.initialization_coordinate_non_finite")
    payload: dict[str, JSONValue] = {
        "profile": INITIALIZATION_PROFILE,
        "status": source.status,
        "projection_sha256": source.projection_sha256,
        "material_sha256": source.material_sha256,
        "forward_inputs_sha256": source.forward_inputs_sha256,
        "anchor_location_groups": [list(group) for group in source.anchor_location_groups],
        "coordinates_mm": [
            {"attachment_location_id": key, "xyz_mm": list(point)} for key, point in rows
        ],
    }
    encoded = jcs_bytes(payload)
    if encoded != source.canonical_bytes or _hash(INITIALIZATION_PROFILE, encoded) != source.sha256:
        raise ForwardBendingError("bending.initialization_integrity")


def _validate_parameters(value: BendingParameters) -> None:
    if not isinstance(value, BendingParameters) or value.status != "HYPOTHESIS":
        raise ForwardBendingError("bending.parameters_invalid")
    expected = admit_bending_parameters(
        value.provenance_id, value.rest_dihedral_rad, value.stiffness_n_mm
    )
    if expected.canonical_bytes != value.canonical_bytes or expected.sha256 != value.sha256:
        raise ForwardBendingError("bending.parameters_integrity")


def _validate_terms(value: ForwardBendingTerms) -> None:
    if not isinstance(value, ForwardBendingTerms) or value.status != "EXPERIMENTAL_BENDING_TERMS":
        raise ForwardBendingError("bending.terms_invalid")
    if not isinstance(value.terms, tuple) or not value.terms:
        raise ForwardBendingError("bending.terms_empty")
    if not all(
        _digest(digest)
        for digest in (
            value.projection_sha256,
            value.material_sha256,
            value.forward_inputs_sha256,
            value.cells_sha256,
            value.initialization_sha256,
            value.parameters_sha256,
            value.sha256,
        )
    ):
        raise ForwardBendingError("bending.terms_hash_invalid")
    for term in value.terms:
        if (
            not isinstance(term, BendingTerm)
            or not isinstance(term.attachment_location_ids, tuple)
            or len(term.attachment_location_ids) != 4
            or any(
                not isinstance(location_id, str) or not location_id
                for location_id in term.attachment_location_ids
            )
            or len(set(term.attachment_location_ids)) != 4
            or isinstance(term.rest_dihedral_rad, bool)
            or not isinstance(term.rest_dihedral_rad, (int, float))
            or not math.isfinite(term.rest_dihedral_rad)
            or not -math.pi <= term.rest_dihedral_rad <= math.pi
            or isinstance(term.stiffness_n_mm, bool)
            or not isinstance(term.stiffness_n_mm, (int, float))
            or not math.isfinite(term.stiffness_n_mm)
            or term.stiffness_n_mm <= 0.0
        ):
            raise ForwardBendingError("bending.term_invalid")
    payload = {
        "profile": TERMS_PROFILE,
        "status": value.status,
        "projection_sha256": value.projection_sha256,
        "material_sha256": value.material_sha256,
        "forward_inputs_sha256": value.forward_inputs_sha256,
        "cells_sha256": value.cells_sha256,
        "initialization_sha256": value.initialization_sha256,
        "parameters_sha256": value.parameters_sha256,
        "tolerances": _tolerance_payload(),
        "terms": [_term_payload(term) for term in value.terms],
    }
    encoded = jcs_bytes(cast(JSONValue, payload))
    if encoded != value.canonical_bytes or _hash(TERMS_PROFILE, encoded) != value.sha256:
        raise ForwardBendingError("bending.terms_integrity")


def _terms_payload(
    cells: ForwardSurfaceCells,
    initialization: ForwardInitialization,
    inputs: ForwardInputs,
    parameters: BendingParameters,
    terms: tuple[BendingTerm, ...],
) -> dict[str, JSONValue]:
    return {
        "profile": TERMS_PROFILE,
        "status": "EXPERIMENTAL_BENDING_TERMS",
        "projection_sha256": cells.projection_sha256,
        "material_sha256": cells.material_sha256,
        "forward_inputs_sha256": inputs.sha256,
        "cells_sha256": cells.sha256,
        "initialization_sha256": initialization.sha256,
        "parameters_sha256": parameters.sha256,
        "tolerances": _tolerance_payload(),
        "terms": [_term_payload(term) for term in terms],
    }


def _term_payload(term: BendingTerm) -> dict[str, JSONValue]:
    return {
        "attachment_location_ids": list(term.attachment_location_ids),
        "rest_dihedral_rad": term.rest_dihedral_rad,
        "stiffness_n_mm": term.stiffness_n_mm,
    }


def _tolerance_payload() -> dict[str, JSONValue]:
    return {
        "minimum_edge_length": {
            "value": MIN_EDGE_LENGTH_MM,
            "unit": "mm",
            "rationale": "arithmetic normalization guard",
            "owner": "forward_bending.py",
        },
        "minimum_area_vector": {
            "value": MIN_AREA_VECTOR_MM2,
            "unit": "mm^2",
            "rationale": "arithmetic normal guard",
            "owner": "forward_bending.py",
        },
        "minimum_triangle_quality": {
            "value": MIN_TRIANGLE_QUALITY,
            "unit": "dimensionless",
            "rationale": "scale-aware lower bound on doubled area divided by longest edge squared",
            "owner": "forward_bending.py",
            "version": "FORWARD_BENDING_HYPOTHESIS_V2",
        },
        "angle_branch": {
            "value": ANGLE_BRANCH_TOLERANCE_RAD,
            "unit": "rad",
            "rationale": "wrap branch ambiguity guard",
            "owner": "forward_bending.py",
        },
    }


def _validate_points(points: tuple[tuple[float, float, float], ...]) -> None:
    if len(points) != 4 or any(not isinstance(point, tuple) or len(point) != 3 for point in points):
        raise ForwardBendingError("bending.coordinate_invalid")
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
        for point in points
        for value in point
    ):
        raise ForwardBendingError("bending.coordinate_non_finite")


def _finite(value: float, reason: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ForwardBendingError(f"bending.{reason}")
    return float(value)


def _hash(profile: str, encoded: bytes) -> str:
    return sha256(b"Crochet.AI\0" + profile.encode("ascii") + b"\0" + encoded).hexdigest()


def _digest(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def _sub_float(a: Vec3, b: Vec3) -> Vec3:
    return cast(Vec3, tuple(a[i] - b[i] for i in range(3)))


def _length(value: Vec3) -> float:
    result = math.hypot(*value)
    if not math.isfinite(result):
        raise ForwardBendingError("bending.geometry_non_finite")
    return result


def _cross_float(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _vsub(
    a: tuple[_Dual, _Dual, _Dual], b: tuple[_Dual, _Dual, _Dual]
) -> tuple[_Dual, _Dual, _Dual]:
    return cast(tuple[_Dual, _Dual, _Dual], tuple(a[i] - b[i] for i in range(3)))


def _dot_dual(a: tuple[_Dual, _Dual, _Dual], b: tuple[_Dual, _Dual, _Dual]) -> _Dual:
    return sum((a[i] * b[i] for i in range(3)), _Dual(0.0, (0.0,) * 12))


def _cross_dual(
    a: tuple[_Dual, _Dual, _Dual], b: tuple[_Dual, _Dual, _Dual]
) -> tuple[_Dual, _Dual, _Dual]:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _sqrt(value: _Dual) -> _Dual:
    root = math.sqrt(value.value)
    return _Dual(root, tuple(component / (2.0 * root) for component in value.gradient))
