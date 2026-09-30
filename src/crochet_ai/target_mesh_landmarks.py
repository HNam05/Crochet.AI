"""Exact boundary-landmark eligibility diagnostic; not an opening matcher."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256

from .canonical import jcs_bytes
from .json_types import JSONValue
from .target_mesh_boundaries import (
    DirectedBoundaryDiagnostic,
    MeshBoundaryError,
    diagnose_indexed_triangle_mesh_boundaries,
)
from .target_mesh_canonical_order import (
    CanonicalOrderDiagnostic,
    MeshCanonicalOrderError,
    diagnose_indexed_triangle_mesh_canonical_order,
)
from .target_mesh_decode import (
    DecodedIndexedTriangleMesh,
    MeshDecodeError,
    decode_indexed_triangle_mesh,
)
from .target_mesh_diameter import (
    MeshDiameterError,
    diagnose_indexed_triangle_mesh_diameter,
)
from .v0_numeric_profile import (
    PROFILE_ID,
    NumericalGeometryProfileError,
    V0NumericProfile,
    resolve_v0_numeric_profile,
)

STATUS = "BOUNDARY_LANDMARK_ELIGIBILITY_DIAGNOSTIC_ONLY"
VERSION = "1.0.0"
_HASH_DOMAIN = b"TARGET_MESH_BOUNDARY_LANDMARK_ELIGIBILITY_V1\0"
_SLACK = Fraction(1, 1 << 40)


class BoundaryLandmarkError(ValueError):
    """Input, provenance, or a declared work budget cannot support analysis."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class BoundaryLandmark:
    landmark_id: str
    target_frame_id: str
    position_mm: tuple[float, float, float]
    tolerance_mm: float


@dataclass(frozen=True, slots=True)
class LandmarkLoopDistance:
    loop_index: int
    squared_distance_numerator_mm2: str
    squared_distance_denominator_mm2: str
    eligible: bool


@dataclass(frozen=True, slots=True)
class LandmarkEligibility:
    landmark_id: str
    candidate_loop_indices: tuple[int, ...]
    classification: str
    loop_distances: tuple[LandmarkLoopDistance, ...]


@dataclass(frozen=True, slots=True)
class BoundaryLandmarkDiagnostic:
    status: str
    algorithm_version: str
    source_sha256: str
    coordinate_frame_id: str
    profile_id: str
    profile_version: str
    profile_sha256: str
    ordering_diagnostic_sha256: str
    boundary_diagnostic_sha256: str
    diameter_numerator_mm2: str
    diameter_denominator_mm2: str
    landmark_count: int
    max_landmarks: int
    required_vertex_pairs: int
    vertex_pairs_evaluated: int
    max_vertex_pairs: int
    required_landmark_edge_tests: int
    landmark_edge_tests: int
    max_landmark_edge_tests: int
    results: tuple[LandmarkEligibility, ...]
    diagnostic_sha256: str


def _point_segment_distance_squared(
    point: tuple[Fraction, Fraction, Fraction],
    start: tuple[Fraction, Fraction, Fraction],
    end: tuple[Fraction, Fraction, Fraction],
) -> Fraction:
    direction = tuple(end[i] - start[i] for i in range(3))
    offset = tuple(point[i] - start[i] for i in range(3))
    length2 = sum((v * v for v in direction), Fraction(0))
    if length2 == 0:
        return sum((v * v for v in offset), Fraction(0))
    projection = sum((offset[i] * direction[i] for i in range(3)), Fraction(0))
    if projection <= 0:
        closest: tuple[Fraction, Fraction, Fraction] = start
    elif projection >= length2:
        closest = end
    else:
        amount = projection / length2
        closest = (
            start[0] + direction[0] * amount,
            start[1] + direction[1] * amount,
            start[2] + direction[2] * amount,
        )
    return sum(((point[i] - closest[i]) ** 2 for i in range(3)), Fraction(0))


def _within_threshold(q: Fraction, tolerance: Fraction, diameter2: Fraction) -> bool:
    # Compare q <= (t + s*sqrt(D))^2 without evaluating or rounding sqrt(D).
    s2d = _SLACK * _SLACK * diameter2
    a = q - tolerance * tolerance - s2d
    return a <= 0 or a * a <= 4 * tolerance * tolerance * s2d


def diagnose_boundary_landmark_eligibility(
    raw_bytes: bytes,
    decoded: DecodedIndexedTriangleMesh,
    ordering: CanonicalOrderDiagnostic,
    boundaries: DirectedBoundaryDiagnostic,
    landmarks: Sequence[BoundaryLandmark],
    *,
    profile: V0NumericProfile,
    media_type: str,
    expected_coordinate_frame_id: str,
    max_bytes: int,
    max_vertices: int,
    max_faces: int,
    max_landmarks: int,
    max_vertex_pairs: int,
    max_landmark_edge_tests: int,
) -> BoundaryLandmarkDiagnostic:
    """Recompute source evidence and report exact candidate loops per landmark."""
    try:
        fresh = decode_indexed_triangle_mesh(
            raw_bytes, media_type=media_type,
            expected_coordinate_frame_id=expected_coordinate_frame_id,
            max_bytes=max_bytes, max_vertices=max_vertices, max_faces=max_faces,
        )
    except (MeshDecodeError, ValueError) as error:
        raise BoundaryLandmarkError("landmarks.source_invalid") from error
    if fresh != decoded:
        raise BoundaryLandmarkError("landmarks.decoded_source_mismatch")
    try:
        fresh_order = diagnose_indexed_triangle_mesh_canonical_order(
            raw_bytes, fresh, media_type=media_type,
            expected_coordinate_frame_id=expected_coordinate_frame_id,
            max_bytes=max_bytes, max_vertices=max_vertices, max_faces=max_faces,
        )
    except MeshCanonicalOrderError as error:
        raise BoundaryLandmarkError("landmarks.ordering_invalid") from error
    if fresh_order != ordering:
        raise BoundaryLandmarkError("landmarks.ordering_mismatch")
    try:
        fresh_boundaries = diagnose_indexed_triangle_mesh_boundaries(
            raw_bytes, fresh, fresh_order, media_type=media_type,
            expected_coordinate_frame_id=expected_coordinate_frame_id,
            max_bytes=max_bytes, max_vertices=max_vertices, max_faces=max_faces,
        )
    except MeshBoundaryError as error:
        raise BoundaryLandmarkError("landmarks.boundary_invalid") from error
    if fresh_boundaries != boundaries:
        raise BoundaryLandmarkError("landmarks.boundary_mismatch")
    if not isinstance(profile, V0NumericProfile):
        raise BoundaryLandmarkError("landmarks.profile_invalid")
    try:
        builtin = resolve_v0_numeric_profile(PROFILE_ID)
    except NumericalGeometryProfileError as error:
        raise BoundaryLandmarkError("landmarks.profile_unresolved") from error
    if profile != builtin:
        raise BoundaryLandmarkError("landmarks.profile_mismatch")

    for name, budget in (("max_landmarks", max_landmarks),
                         ("max_vertex_pairs", max_vertex_pairs),
                         ("max_landmark_edge_tests", max_landmark_edge_tests)):
        if isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0:
            raise BoundaryLandmarkError(f"landmarks.{name}_invalid")
    if not isinstance(landmarks, (tuple, list)):
        raise BoundaryLandmarkError("landmarks.request_invalid")
    if len(landmarks) > max_landmarks:
        raise BoundaryLandmarkError("landmarks.landmark_budget_exhausted")
    landmarks = tuple(landmarks)
    seen: set[str] = set()
    for landmark in landmarks:
        if not isinstance(landmark, BoundaryLandmark):
            raise BoundaryLandmarkError("landmarks.request_type_invalid")
        if (not isinstance(landmark.landmark_id, str)
                or re.fullmatch(r"landmark_[A-Za-z0-9][A-Za-z0-9._-]{0,112}",
                                landmark.landmark_id) is None
                or landmark.landmark_id in seen):
            raise BoundaryLandmarkError("landmarks.id_invalid_or_duplicate")
        seen.add(landmark.landmark_id)
        if landmark.target_frame_id != expected_coordinate_frame_id:
            raise BoundaryLandmarkError("landmarks.frame_mismatch")
        if (not isinstance(landmark.position_mm, tuple) or len(landmark.position_mm) != 3
                or any(isinstance(v, bool) or not isinstance(v, float)
                       for v in landmark.position_mm)
                or any(not math.isfinite(v) for v in landmark.position_mm)):
            raise BoundaryLandmarkError("landmarks.position_invalid")
        if (isinstance(landmark.tolerance_mm, bool)
                or not isinstance(landmark.tolerance_mm, float)
                or not math.isfinite(landmark.tolerance_mm)
                or landmark.tolerance_mm < 0):
            raise BoundaryLandmarkError("landmarks.tolerance_invalid")
    landmarks = tuple(sorted(landmarks, key=lambda landmark: landmark.landmark_id))

    vertex_count = len(fresh.vertices_mm)
    required_pairs = vertex_count * (vertex_count - 1) // 2
    edge_count = sum(len(loop) for loop in fresh_boundaries.boundary_loops)
    required_tests = len(landmarks) * edge_count
    if required_pairs > max_vertex_pairs:
        raise BoundaryLandmarkError("landmarks.vertex_pair_budget_exhausted")
    if required_tests > max_landmark_edge_tests:
        raise BoundaryLandmarkError("landmarks.edge_test_budget_exhausted")
    try:
        diameter = diagnose_indexed_triangle_mesh_diameter(
            raw_bytes, fresh, media_type=media_type,
            expected_coordinate_frame_id=expected_coordinate_frame_id,
            max_bytes=max_bytes, max_vertices=max_vertices, max_faces=max_faces,
            max_vertex_pairs_evaluated=max_vertex_pairs,
        )
    except MeshDiameterError as error:
        raise BoundaryLandmarkError("landmarks.diameter_invalid") from error
    diameter2 = Fraction(int(diameter.squared_diameter_numerator_mm2),
                         int(diameter.squared_diameter_denominator_mm2))
    if diameter2 <= 0:
        raise BoundaryLandmarkError("landmarks.zero_mesh_diameter")
    positions: tuple[tuple[Fraction, Fraction, Fraction], ...] = tuple(
        (Fraction.from_float(p[0]), Fraction.from_float(p[1]), Fraction.from_float(p[2]))
        for p in fresh_order.derived_vertices_mm
    )
    results: list[LandmarkEligibility] = []
    for landmark in landmarks:
        point = (
            Fraction.from_float(landmark.position_mm[0]),
            Fraction.from_float(landmark.position_mm[1]),
            Fraction.from_float(landmark.position_mm[2]),
        )
        tolerance = Fraction.from_float(landmark.tolerance_mm)
        candidates: list[int] = []
        loop_distances: list[LandmarkLoopDistance] = []
        for loop_index, loop in enumerate(fresh_boundaries.boundary_loops):
            distance = min(
                _point_segment_distance_squared(
                    point, positions[loop[i]], positions[loop[(i + 1) % len(loop)]]
                ) for i in range(len(loop))
            )
            eligible = _within_threshold(distance, tolerance, diameter2)
            loop_distances.append(LandmarkLoopDistance(
                loop_index, str(distance.numerator), str(distance.denominator), eligible,
            ))
            if eligible:
                candidates.append(loop_index)
        candidate_tuple = tuple(candidates)
        if not candidates:
            classification = "UNMATCHED"
        elif len(candidates) == 1:
            classification = "UNIQUE"
        else:
            classification = "AMBIGUOUS"
        results.append(LandmarkEligibility(
            landmark.landmark_id, candidate_tuple, classification, tuple(loop_distances),
        ))

    request_payload: JSONValue = {"landmarks": [
        {"id": lm.landmark_id, "target_frame_id": lm.target_frame_id,
         "position_mm": [lm.position_mm[0], lm.position_mm[1], lm.position_mm[2]],
         "tolerance_mm": lm.tolerance_mm} for lm in landmarks
    ]}
    payload: JSONValue = {
        "status": STATUS, "algorithm_version": VERSION,
        "source_sha256": fresh.source_sha256,
        "parser": {
            "name": fresh.parser_name, "version": fresh.parser_version,
            "media_type": fresh.media_type,
            "coordinate_frame_id": fresh.coordinate_frame_id,
        },
        "request": request_payload,
        "profile": {"id": profile.profile_id, "version": profile.profile_version,
                    "sha256": profile.record_sha256,
                    "slack": {"numerator": "1", "denominator": str(1 << 40)}},
        "ordering_diagnostic_sha256": fresh_order.diagnostic_sha256,
        "boundary_diagnostic_sha256": fresh_boundaries.diagnostic_sha256,
        "diameter_squared_mm2": {"numerator": str(diameter2.numerator),
                                 "denominator": str(diameter2.denominator)},
        "budget": {"landmark_count": len(landmarks), "max_landmarks": max_landmarks,
                   "required_vertex_pairs": required_pairs,
                   "vertex_pairs_evaluated": required_pairs, "max_vertex_pairs": max_vertex_pairs,
                   "required_landmark_edge_tests": required_tests,
                   "landmark_edge_tests": required_tests,
                   "max_landmark_edge_tests": max_landmark_edge_tests},
        "results": [{"landmark_id": r.landmark_id,
                     "candidate_loop_indices": list(r.candidate_loop_indices),
                     "classification": r.classification,
                     "loop_distances": [
                         {"loop_index": d.loop_index,
                          "squared_distance_mm2": {
                              "numerator": d.squared_distance_numerator_mm2,
                              "denominator": d.squared_distance_denominator_mm2},
                          "eligible": d.eligible} for d in r.loop_distances],
                     } for r in results],
    }
    digest = sha256(_HASH_DOMAIN + jcs_bytes(payload)).hexdigest()
    return BoundaryLandmarkDiagnostic(
        STATUS, VERSION, fresh.source_sha256, fresh.coordinate_frame_id,
        profile.profile_id, profile.profile_version, profile.record_sha256,
        fresh_order.diagnostic_sha256, fresh_boundaries.diagnostic_sha256,
        str(diameter2.numerator), str(diameter2.denominator), len(landmarks), max_landmarks,
        required_pairs, required_pairs, max_vertex_pairs, required_tests,
        required_tests, max_landmark_edge_tests, tuple(results), digest,
    )
