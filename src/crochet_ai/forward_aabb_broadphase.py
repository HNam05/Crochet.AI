"""Target-free AABB candidate enumeration for experimental initial coordinates.

This diagnostic exhaustively compares every unordered pair of source-ordered
triangles. ``max_contact_pairs_evaluated`` is interpreted here as the maximum
total unordered AABB comparisons, whether or not boxes overlap. The module
reports candidates only; it does not test triangle intersection or contact.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from .canonical import jcs_bytes, parse_json
from .forward_cells import ForwardSurfaceCells
from .forward_initialization import ForwardInitialization
from .forward_inputs import ForwardInputError, ForwardInputs, admit_forward_inputs
from .forward_triangle_geometry import (
    ForwardTriangleGeometryError,
    validate_initial_geometry_inputs,
)
from .forward_triangulation import ForwardSurfaceTriangulation

PROFILE = "FORWARD_INITIAL_AABB_BROADPHASE_V1"


class ForwardAABBBroadphaseError(ValueError):
    """Input integrity, binding, or deterministic budget failure."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class TriangleAABB:
    """Axis-aligned bounds of one represented triangle, in millimetres."""

    face_index: int
    minimum_mm: tuple[float, float, float]
    maximum_mm: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class AABBCandidatePair:
    """One inclusive AABB-overlap pair in stable global face order."""

    first_face_index: int
    second_face_index: int
    shared_location_count: int
    shared_location_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ForwardAABBBroadphaseDiagnostic:
    """Immutable exhaustive AABB candidate result bound to all inputs."""

    status: str
    source_triangulation_sha256: str
    initialization_sha256: str
    projection_sha256: str
    material_sha256: str
    forward_inputs_sha256: str
    max_contact_pairs_evaluated: int
    unordered_aabb_comparisons: int
    face_aabbs: tuple[TriangleAABB, ...]
    candidate_pairs: tuple[AABBCandidatePair, ...]
    canonical_bytes: bytes
    sha256: str


def diagnose_initial_aabb_candidates(
    source: ForwardSurfaceCells,
    triangulation: ForwardSurfaceTriangulation,
    initialization: ForwardInitialization,
    inputs: ForwardInputs,
) -> ForwardAABBBroadphaseDiagnostic:
    """Enumerate all inclusive triangle-AABB overlaps without target geometry.

    A successful result has status ``CANDIDATES_ONLY`` even when there are no
    overlapping boxes. Budget exhaustion is rejected before any partial result
    is constructed. No tolerance or material-derived threshold is used.
    """

    if not isinstance(inputs, ForwardInputs):
        raise ForwardAABBBroadphaseError("aabb.forward_inputs_type")
    _validate_forward_inputs(inputs)
    try:
        # Validate provenance and finite coordinates without requiring the
        # separate binary64 area metric to be representable at this scale.
        coordinates = validate_initial_geometry_inputs(source, triangulation, initialization)
    except ForwardTriangleGeometryError as error:
        raise ForwardAABBBroadphaseError("aabb.initial_geometry_invalid") from error

    if source.projection_sha256 != initialization.projection_sha256:
        raise ForwardAABBBroadphaseError("aabb.projection_binding_mismatch")
    if source.material_sha256 != initialization.material_sha256:
        raise ForwardAABBBroadphaseError("aabb.material_binding_mismatch")
    if initialization.forward_inputs_sha256 != inputs.sha256:
        raise ForwardAABBBroadphaseError("aabb.forward_inputs_binding_mismatch")

    face_count = len(triangulation.triangles)
    comparisons = face_count * (face_count - 1) // 2
    budget = inputs.max_contact_pairs_evaluated
    if comparisons > budget:
        raise ForwardAABBBroadphaseError("aabb.comparison_budget_exhausted")

    face_aabbs: list[TriangleAABB] = []
    for face_index, triangle in enumerate(triangulation.triangles):
        try:
            points = tuple(
                coordinates[identifier] for identifier in triangle.attachment_location_ids
            )
        except KeyError as error:
            raise ForwardAABBBroadphaseError("aabb.coordinate_missing") from error
        minimum = tuple(min(point[axis] for point in points) for axis in range(3))
        maximum = tuple(max(point[axis] for point in points) for axis in range(3))
        face_aabbs.append(
            TriangleAABB(
                face_index,
                (minimum[0], minimum[1], minimum[2]),
                (maximum[0], maximum[1], maximum[2]),
            )
        )

    candidates: list[AABBCandidatePair] = []
    triangles = triangulation.triangles
    for first_index, first in enumerate(face_aabbs):
        for second_index in range(first_index + 1, face_count):
            second = face_aabbs[second_index]
            if _overlaps_inclusive(first, second):
                first_locations = set(triangles[first_index].attachment_location_ids)
                second_locations = set(triangles[second_index].attachment_location_ids)
                shared = tuple(sorted(first_locations & second_locations))
                candidates.append(
                    AABBCandidatePair(
                        first.face_index,
                        second.face_index,
                        len(shared),
                        shared,
                    )
                )

    payload: dict[str, Any] = {
        "profile": PROFILE,
        "status": "CANDIDATES_ONLY",
        "source_triangulation_sha256": triangulation.sha256,
        "initialization_sha256": initialization.sha256,
        "projection_sha256": source.projection_sha256,
        "material_sha256": source.material_sha256,
        "forward_inputs_sha256": inputs.sha256,
        "max_contact_pairs_evaluated": budget,
        "unordered_aabb_comparisons": comparisons,
        "limitations": [
            "aabb_overlap_is_only_a_candidate_and_not_triangle_intersection_or_contact",
            "zero_candidates_does_not_establish_collision_free_geometry",
            "initial_coordinates_are_not_a_converged_forward_simulation_or_v6_result",
        ],
        "face_aabbs": [
            {
                "face_index": box.face_index,
                "minimum_mm": list(box.minimum_mm),
                "maximum_mm": list(box.maximum_mm),
            }
            for box in face_aabbs
        ],
        "candidate_pairs": [
            {
                "first_face_index": pair.first_face_index,
                "second_face_index": pair.second_face_index,
                "shared_location_count": pair.shared_location_count,
                "shared_location_ids": list(pair.shared_location_ids),
            }
            for pair in candidates
        ],
    }
    encoded = jcs_bytes(payload)
    digest = sha256(b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + encoded).hexdigest()
    return ForwardAABBBroadphaseDiagnostic(
        "CANDIDATES_ONLY",
        triangulation.sha256,
        initialization.sha256,
        source.projection_sha256,
        source.material_sha256,
        inputs.sha256,
        budget,
        comparisons,
        tuple(face_aabbs),
        tuple(candidates),
        encoded,
        digest,
    )


def _overlaps_inclusive(first: TriangleAABB, second: TriangleAABB) -> bool:
    return all(
        first.minimum_mm[axis] <= second.maximum_mm[axis]
        and second.minimum_mm[axis] <= first.maximum_mm[axis]
        for axis in range(3)
    )


def _validate_forward_inputs(inputs: ForwardInputs) -> None:
    canonical_bytes = inputs.canonical_bytes
    if not isinstance(canonical_bytes, bytes):
        raise ForwardAABBBroadphaseError("aabb.forward_inputs_integrity")
    try:
        payload = parse_json(canonical_bytes)
        if not isinstance(payload, dict):
            raise ValueError("forward input payload is not an object")
        loading = payload.get("loading")
        model_profile = payload.get("model_profile")
        config = payload.get("config")
        if not isinstance(loading, dict) or not isinstance(model_profile, dict) or not isinstance(
            config, dict
        ):
            raise ValueError("forward input sections are not objects")
        rebuilt = admit_forward_inputs(
            loading,
            model_profile,
            config,
        )
    except (ForwardInputError, TypeError, ValueError) as error:
        raise ForwardAABBBroadphaseError("aabb.forward_inputs_integrity") from error
    if rebuilt != inputs or rebuilt.canonical_bytes != canonical_bytes:
        raise ForwardAABBBroadphaseError("aabb.forward_inputs_integrity")
