"""Exact self-intersection diagnostic for experimental optimizer coordinates.

This target-free report reuses the initial-coordinate exact intersection
predicate. It is diagnostic evidence only and never establishes V6 validity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from typing import Any

from .canonical import jcs_bytes, parse_json
from .forward_aabb_broadphase import _validate_forward_inputs
from .forward_cells import ForwardSurfaceCells
from .forward_exact_distances import _pair_distance_squared
from .forward_exact_intersections import (
    Point,
    Triangle,
    _exact_zero_area,
    _in_shared_simplex,
    _triangle_intersections,
)
from .forward_inputs import ForwardInputs
from .forward_optimize import PROFILE as OPTIMIZE_PROFILE
from .forward_optimize import ForwardOptimizeResult
from .forward_shear import ARMIJO_C as SHEAR_ARMIJO_C
from .forward_shear import (
    BACKTRACK_FACTOR,
    INITIAL_ALPHA_MM_PER_N,
    ShearBendingOptimizeResult,
    ShearOptimizeResult,
)
from .forward_triangulation import ForwardSurfaceTriangulation, triangulate_forward_surface_cells

PROFILE = "FORWARD_FINAL_EXACT_SELF_CONTACT_V1"


class ForwardFinalExactContactError(ValueError):
    """Malformed provenance, optimizer result, or deterministic pair budget."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class FinalExactContactPair:
    first_face_index: int
    second_face_index: int
    shared_location_count: int
    intersection_point_count: int
    forbidden_intersection: bool


@dataclass(frozen=True, slots=True)
class ForwardFinalExactContactDiagnostic:
    status: str
    source_triangulation_sha256: str
    optimization_sha256: str
    projection_sha256: str
    material_sha256: str
    forward_inputs_sha256: str
    all_pair_count: int
    intersecting_pair_count: int
    forbidden_pair_count: int
    minimum_squared_distance_numerator: str | None
    minimum_squared_distance_denominator: str | None
    minimizing_face_pairs: tuple[tuple[int, int], ...]
    pairs: tuple[FinalExactContactPair, ...]
    canonical_bytes: bytes
    sha256: str


def diagnose_final_exact_self_contact(
    source: ForwardSurfaceCells,
    triangulation: ForwardSurfaceTriangulation,
    optimization: ForwardOptimizeResult | ShearOptimizeResult | ShearBendingOptimizeResult,
    inputs: ForwardInputs,
) -> ForwardFinalExactContactDiagnostic:
    """Check all final-coordinate triangle pairs with exact binary-rational predicates."""
    try:
        _validate_forward_inputs(inputs)
        if not isinstance(source, ForwardSurfaceCells):
            raise ValueError("source_type")
        if triangulation != triangulate_forward_surface_cells(source):
            raise ValueError("triangulation_mismatch")
        _validate_optimization(optimization, source, inputs)
    except (TypeError, ValueError) as error:
        reason = (
            error.args[0]
            if error.args and isinstance(error.args[0], str)
            else "input_integrity"
        )
        raise ForwardFinalExactContactError(f"final_contact.{reason}") from error

    faces = triangulation.triangles
    all_pair_count = len(faces) * (len(faces) - 1) // 2
    if all_pair_count > inputs.max_contact_pairs_evaluated:
        raise ForwardFinalExactContactError("final_contact.pair_budget_exhausted")

    coordinates: dict[str, Point] = {
        identifier: (
            Fraction.from_float(point[0]),
            Fraction.from_float(point[1]),
            Fraction.from_float(point[2]),
        )
        for identifier, point in optimization.coordinates_mm or ()
    }
    triangles: list[Triangle] = []
    for face in faces:
        try:
            ids = face.attachment_location_ids
            triangle: Triangle = (coordinates[ids[0]], coordinates[ids[1]], coordinates[ids[2]])
        except KeyError as error:
            raise ForwardFinalExactContactError("final_contact.coordinate_missing") from error
        if _exact_zero_area(triangle):
            raise ForwardFinalExactContactError("final_contact.exact_zero_area_triangle")
        triangles.append(triangle)

    pairs: list[FinalExactContactPair] = []
    minimum_squared_distance: Fraction | None = None
    minimizing_face_pairs: list[tuple[int, int]] = []
    for first_index, first_face in enumerate(faces):
        first_ids = set(first_face.attachment_location_ids)
        for second_index in range(first_index + 1, len(faces)):
            second_face = faces[second_index]
            shared = first_ids & set(second_face.attachment_location_ids)
            if len(shared) > 2:
                raise ForwardFinalExactContactError("final_contact.shared_simplex_invalid")
            points = _triangle_intersections(triangles[first_index], triangles[second_index])
            forbidden = any(not _in_shared_simplex(point, shared, coordinates) for point in points)
            if not shared:
                try:
                    distance_squared = _pair_distance_squared(
                        triangles[first_index], triangles[second_index]
                    )
                except (ArithmeticError, ValueError) as error:
                    raise ForwardFinalExactContactError(
                        "final_contact.exact_distance_failed"
                    ) from error
                face_pair = (first_index, second_index)
                if minimum_squared_distance is None or distance_squared < minimum_squared_distance:
                    minimum_squared_distance = distance_squared
                    minimizing_face_pairs = [face_pair]
                elif distance_squared == minimum_squared_distance:
                    minimizing_face_pairs.append(face_pair)
            pairs.append(FinalExactContactPair(
                first_index, second_index, len(shared), len(points), forbidden
            ))

    intersecting = sum(pair.intersection_point_count > 0 for pair in pairs)
    forbidden_count = sum(pair.forbidden_intersection for pair in pairs)
    minimum_numerator = (
        None if minimum_squared_distance is None else str(minimum_squared_distance.numerator)
    )
    minimum_denominator = (
        None if minimum_squared_distance is None else str(minimum_squared_distance.denominator)
    )
    payload: dict[str, Any] = {
        "profile": PROFILE,
        "status": "FINAL_COORDINATE_SELF_CONTACT_DIAGNOSTIC_ONLY",
        "source_triangulation_sha256": triangulation.sha256,
        "optimization_sha256": optimization.sha256,
        "projection_sha256": source.projection_sha256,
        "material_sha256": source.material_sha256,
        "forward_inputs_sha256": inputs.sha256,
        "max_contact_pairs_evaluated": inputs.max_contact_pairs_evaluated,
        "all_pair_count": all_pair_count,
        "intersecting_pair_count": intersecting,
        "forbidden_pair_count": forbidden_count,
        "minimum_squared_distance_mm2": (
            None if minimum_squared_distance is None else {
                "numerator": minimum_numerator,
                "denominator": minimum_denominator,
            }
        ),
        "minimizing_face_pairs": [list(pair) for pair in minimizing_face_pairs],
        "limitations": [
            "exact_binary_rational_intersection_and_nonadjacent_distance_only_no_penetration",
            "diagnostic_only_does_not_establish_collision_free_geometry_or_physical_contact",
            "does_not_establish_f0_convergence_or_v6",
        ],
        "pairs": [
            {
                "first_face_index": pair.first_face_index,
                "second_face_index": pair.second_face_index,
                "shared_location_count": pair.shared_location_count,
                "intersection_point_count": pair.intersection_point_count,
                "forbidden_intersection": pair.forbidden_intersection,
            }
            for pair in pairs
        ],
    }
    encoded = jcs_bytes(payload)
    digest = sha256(b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + encoded).hexdigest()
    return ForwardFinalExactContactDiagnostic(
        "FINAL_COORDINATE_SELF_CONTACT_DIAGNOSTIC_ONLY", triangulation.sha256,
        optimization.sha256, source.projection_sha256, source.material_sha256,
        inputs.sha256, all_pair_count, intersecting, forbidden_count,
        minimum_numerator, minimum_denominator, tuple(minimizing_face_pairs),
        tuple(pairs), encoded, digest,
    )


def _validate_optimization(
    result: ForwardOptimizeResult | ShearOptimizeResult | ShearBendingOptimizeResult,
    source: ForwardSurfaceCells,
    inputs: ForwardInputs,
) -> None:
    if not isinstance(
        result, (ForwardOptimizeResult, ShearOptimizeResult, ShearBendingOptimizeResult)
    ):
        raise ValueError("optimization_type")
    if result.status != "EXPERIMENTAL_FORCE_BALANCED" or result.coordinates_mm is None:
        raise ValueError("optimization_coordinates_unavailable")
    if (result.projection_sha256, result.material_sha256, result.forward_inputs_sha256) != (
        source.projection_sha256, source.material_sha256, inputs.sha256
    ):
        raise ValueError("optimization_provenance_mismatch")
    if not _is_hash(result.initialization_sha256):
        raise ValueError("optimization_provenance_invalid")
    rows = result.coordinates_mm
    if not isinstance(rows, tuple) or tuple(sorted(rows)) != rows:
        raise ValueError("optimization_coordinates_invalid")
    coordinates: dict[str, tuple[float, float, float]] = {}
    for row in rows:
        if not isinstance(row, tuple) or len(row) != 2:
            raise ValueError("optimization_coordinates_invalid")
        key, point = row
        if not isinstance(key, str) or not key or key in coordinates:
            raise ValueError("optimization_coordinates_invalid")
        if not isinstance(point, tuple) or len(point) != 3:
            raise ValueError("optimization_coordinates_invalid")
        if any(isinstance(value, bool) or not isinstance(value, float) for value in point):
            raise ValueError("optimization_coordinates_invalid")
        if any(not math.isfinite(value) for value in point):
            raise ValueError("optimization_coordinates_invalid")
        coordinates[key] = point
    expected_ids = {
        identifier for cell in source.cells for identifier in cell.attachment_location_ids
    }
    if set(coordinates) != expected_ids:
        raise ValueError("optimization_coordinate_domain_mismatch")
    if isinstance(result, (ShearOptimizeResult, ShearBendingOptimizeResult)):
        _validate_shear_optimization(result, rows)
        return
    payload: dict[str, Any] = {
        "profile": OPTIMIZE_PROFILE,
        "status": result.status,
        "projection_sha256": result.projection_sha256,
        "material_sha256": result.material_sha256,
        "forward_inputs_sha256": result.forward_inputs_sha256,
        "initialization_sha256": result.initialization_sha256,
        "coordinates_mm": [
            {"attachment_location_id": key, "xyz_mm": list(point)} for key, point in rows
        ],
        "maximum_force_n": result.maximum_force_n,
        "iterations": [
            {
                "status": item.status,
                "baseline_energy_n_mm": item.baseline_energy_n_mm,
                "trial_energies_n_mm": list(item.trial_energies_n_mm),
                "baseline_maximum_force_n": item.baseline_maximum_force_n,
                "trial_maximum_force_n": item.trial_maximum_force_n,
                "accepted_alpha_mm_per_n": item.accepted_alpha_mm_per_n,
                "alpha_trace_mm_per_n": list(item.alpha_trace_mm_per_n),
                "energy_evaluations": item.energy_evaluations,
                "line_search_trials": item.line_search_trials,
            }
            for item in result.iterations
        ],
        "optimizer_iterations": result.optimizer_iterations,
        "energy_evaluations": result.energy_evaluations,
        "line_search_trials": result.line_search_trials,
    }
    try:
        encoded = jcs_bytes(payload)
    except (TypeError, ValueError) as error:
        raise ValueError("optimization_integrity") from error
    digest = sha256(
        b"Crochet.AI\0" + OPTIMIZE_PROFILE.encode("ascii") + b"\0" + encoded
    ).hexdigest()
    if encoded != result.canonical_bytes or digest != result.sha256:
        raise ValueError("optimization_integrity")


def _validate_shear_optimization(
    result: ShearOptimizeResult | ShearBendingOptimizeResult,
    rows: tuple[tuple[str, tuple[float, float, float]], ...],
) -> None:
    if not _is_hash(result.stretch_terms_sha256) or not _is_hash(result.shear_terms_sha256):
        raise ValueError("optimization_provenance_invalid")
    is_bending = isinstance(result, ShearBendingOptimizeResult)
    if isinstance(result, ShearBendingOptimizeResult) and not _is_hash(result.bending_terms_sha256):
        raise ValueError("optimization_provenance_invalid")
    try:
        payload = parse_json(result.canonical_bytes)
        if not isinstance(payload, dict) or jcs_bytes(payload) != result.canonical_bytes:
            raise ValueError("optimization_integrity")
    except (TypeError, ValueError) as error:
        raise ValueError("optimization_integrity") from error
    expected_fields: dict[str, Any] = {
        "profile": (
            "FORWARD_STRETCH_SHEAR_BENDING_OPTIMIZATION_V1"
            if is_bending else "FORWARD_STRETCH_SHEAR_OPTIMIZATION_V1"
        ),
        "status": result.status,
        "projection_sha256": result.projection_sha256,
        "material_sha256": result.material_sha256,
        "forward_inputs_sha256": result.forward_inputs_sha256,
        "stretch_terms_sha256": result.stretch_terms_sha256,
        "shear_terms_sha256": result.shear_terms_sha256,
        "initialization_sha256": result.initialization_sha256,
        "coordinates_mm": [
            {"attachment_location_id": key, "xyz_mm": list(point)} for key, point in rows
        ],
        "maximum_force_n": result.maximum_force_n,
        "optimizer_iterations": result.optimizer_iterations,
        "energy_evaluations": result.energy_evaluations,
        "line_search_trials": result.line_search_trials,
        "initial_alpha_mm_per_n": INITIAL_ALPHA_MM_PER_N,
        "armijo_c": SHEAR_ARMIJO_C,
    }
    if isinstance(result, ShearBendingOptimizeResult):
        expected_fields["bending_terms_sha256"] = result.bending_terms_sha256
        expected_fields["backtracking_factor"] = BACKTRACK_FACTOR
    if (
        set(payload) != set(expected_fields) | {"trace"}
        or not isinstance(payload.get("trace"), list)
        or any(payload.get(key) != value for key, value in expected_fields.items())
    ):
        raise ValueError("optimization_integrity")
    digest = sha256(
        b"Crochet.AI\0" + expected_fields["profile"].encode("ascii")
        + b"\0" + result.canonical_bytes
    ).hexdigest()
    if digest != result.sha256:
        raise ValueError("optimization_integrity")


def _is_hash(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )
