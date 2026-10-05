"""Source-bound v2 adjacent residual threshold diagnostic; not V0 acceptance."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from itertools import combinations

from .canonical import jcs_bytes
from .json_types import JSONValue
from .target_mesh_adjacent_residual import (
    MeshAdjacentResidualError,
    MeshAdjacentResidualPair,
    diagnose_indexed_triangle_mesh_adjacent_residual,
)
from .target_mesh_decode import (
    MESH_MEDIA_TYPE,
    MeshDecodeError,
    decode_indexed_triangle_mesh,
)
from .v0_adjacent_profile import (
    PROFILE_ID,
    ZONE_POLICY_ID,
    AdjacentProfileError,
    V0AdjacentNumericProfile,
    parse_adjacent_exclusion_zone,
    resolve_v0_adjacent_numeric_profile,
)

STATUS = "ADJACENT_CLEARANCE_DIAGNOSTIC_ONLY"
VERSION = "1.0.0"
_HASH_DOMAIN = b"TARGET_MESH_ADJACENT_CLEARANCE_V1\0"


class MeshAdjacentClearanceError(ValueError):
    """Input profile, mesh, or explicit work budget is unsupported."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class AdjacentClearancePair:
    ordered_face_indices: tuple[int, int]
    source_face_indices: tuple[int, int]
    shared_entity: str
    shared_source_vertex_indices: tuple[int, ...]
    squared_distance_numerator_mm2: str
    squared_distance_denominator_mm2: str
    normalized_threshold_state: str
    evaluated_piece_pairs: int


@dataclass(frozen=True, slots=True)
class AdjacentClearanceDiagnostic:
    status: str
    algorithm_version: str
    source_sha256: str
    parser_name: str
    parser_version: str
    media_type: str
    coordinate_frame_id: str
    vertex_count: int
    face_count: int
    profile_id: str
    profile_version: str
    profile_sha256: str
    policy_id: str
    lambda_numerator: str
    lambda_denominator: str
    threshold_numerator: str
    threshold_denominator: str
    threshold_operator: str
    squared_diameter_numerator_mm2: str
    squared_diameter_denominator_mm2: str
    max_vertex_pairs: int
    vertex_pairs_evaluated: int
    residual_diagnostic_sha256: str
    required_face_pairs: int
    adjacent_face_pair_count: int
    nonadjacent_face_pairs_skipped: int
    predicted_distance_piece_pairs: int
    evaluated_distance_piece_pairs: int
    pairs: tuple[AdjacentClearancePair, ...]
    diagnostic_sha256: str


def diagnose_indexed_triangle_mesh_adjacent_clearance(
    raw_bytes: bytes,
    *,
    profile: V0AdjacentNumericProfile,
    adjacent_exclusion_zone: object,
    media_type: str,
    expected_coordinate_frame_id: str,
    max_bytes: int,
    max_vertices: int,
    max_faces: int,
    max_vertex_pairs: int,
    max_face_pairs: int,
    max_distance_piece_pairs: int,
    max_lambda_bits: int,
) -> AdjacentClearanceDiagnostic:
    """Classify exact adjacent residuals against the immutable v2 threshold.

    This diagnostic consumes the complete source and exact reduced DesignSpec
    zone. A result is diagnostic evidence only and cannot establish V0 PASS.
    """
    for name, value in (
        ("max_bytes", max_bytes), ("max_vertices", max_vertices),
        ("max_faces", max_faces), ("max_vertex_pairs", max_vertex_pairs),
        ("max_face_pairs", max_face_pairs),
        ("max_distance_piece_pairs", max_distance_piece_pairs),
        ("max_lambda_bits", max_lambda_bits),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise MeshAdjacentClearanceError(f"adjacent_clearance.{name}_invalid")
    if media_type != MESH_MEDIA_TYPE:
        raise MeshAdjacentClearanceError("adjacent_clearance.media_type_unsupported")
    if not isinstance(profile, V0AdjacentNumericProfile):
        raise MeshAdjacentClearanceError("adjacent_clearance.profile_invalid")
    try:
        resolved = resolve_v0_adjacent_numeric_profile(PROFILE_ID)
        threshold = Fraction.from_float(
            resolved.thresholds.near_contact_distance_normalized_max
        )
        lam = parse_adjacent_exclusion_zone(adjacent_exclusion_zone)
    except AdjacentProfileError as error:
        raise MeshAdjacentClearanceError("adjacent_clearance.profile_or_zone_invalid") from error
    if profile != resolved:
        raise MeshAdjacentClearanceError("adjacent_clearance.profile_mismatch")
    if profile.policy_id != ZONE_POLICY_ID:
        raise MeshAdjacentClearanceError("adjacent_clearance.policy_unsupported")
    if max(lam.numerator.bit_length(), lam.denominator.bit_length()) > max_lambda_bits:
        raise MeshAdjacentClearanceError("adjacent_clearance.lambda_bit_budget_exhausted")

    try:
        decoded = decode_indexed_triangle_mesh(
            raw_bytes, media_type=media_type,
            expected_coordinate_frame_id=expected_coordinate_frame_id,
            max_bytes=max_bytes, max_vertices=max_vertices, max_faces=max_faces,
        )
    except (MeshDecodeError, ValueError) as error:
        raise MeshAdjacentClearanceError("adjacent_clearance.source_invalid") from error
    vertex_count = len(decoded.vertices_mm)
    required_vertex_pairs = vertex_count * (vertex_count - 1) // 2
    if required_vertex_pairs == 0:
        raise MeshAdjacentClearanceError("adjacent_clearance.diameter_unavailable")
    if required_vertex_pairs > max_vertex_pairs:
        raise MeshAdjacentClearanceError("adjacent_clearance.vertex_pair_budget_exhausted")

    points = tuple(tuple(Fraction.from_float(axis) for axis in point)
                   for point in decoded.vertices_mm)
    diameter_squared = max(
        sum(((first[axis] - second[axis]) ** 2 for axis in range(3)), Fraction(0))
        for first, second in combinations(points, 2)
    )
    if diameter_squared <= 0:
        raise MeshAdjacentClearanceError("adjacent_clearance.zero_scale")

    try:
        residual = diagnose_indexed_triangle_mesh_adjacent_residual(
            raw_bytes, media_type=media_type,
            expected_coordinate_frame_id=expected_coordinate_frame_id,
            lambda_value=lam, max_bytes=max_bytes, max_vertices=max_vertices,
            max_faces=max_faces, max_face_pairs=max_face_pairs,
            max_distance_piece_pairs=max_distance_piece_pairs,
            max_lambda_bits=max_lambda_bits,
        )
    except MeshAdjacentResidualError as error:
        raise MeshAdjacentClearanceError(f"adjacent_clearance.residual:{error.reason}") from error
    if residual.source_sha256 != decoded.source_sha256:
        raise MeshAdjacentClearanceError("adjacent_clearance.source_binding_mismatch")

    limit_squared = threshold * threshold * diameter_squared
    classified = tuple(_classify(pair, limit_squared) for pair in residual.pairs)
    payload: JSONValue = {
        "status": STATUS,
        "algorithm_version": VERSION,
        "source": {
            "sha256": decoded.source_sha256, "parser_name": decoded.parser_name,
            "parser_version": decoded.parser_version, "media_type": media_type,
            "coordinate_frame_id": decoded.coordinate_frame_id,
            "vertex_count": vertex_count, "face_count": len(decoded.faces),
        },
        "profile": {
            "id": profile.profile_id, "version": profile.profile_version,
            "sha256": profile.record_sha256,
        },
        "policy_id": profile.policy_id,
        "lambda": {"numerator": str(lam.numerator), "denominator": str(lam.denominator)},
        "threshold": {
            "numerator": str(threshold.numerator),
            "denominator": str(threshold.denominator),
            "operator": "LESS_THAN_OR_EQUAL",
        },
        "squared_diameter_mm2": {
            "numerator": str(diameter_squared.numerator),
            "denominator": str(diameter_squared.denominator),
        },
        "budget": {
            "required_vertex_pairs": required_vertex_pairs,
            "vertex_pairs_evaluated": required_vertex_pairs,
            "max_vertex_pairs": max_vertex_pairs,
        },
        "residual_diagnostic_sha256": residual.diagnostic_sha256,
        "pair_coverage": {
            "required_face_pairs": residual.required_face_pairs,
            "adjacent_face_pair_count": residual.adjacent_face_pair_count,
            "nonadjacent_face_pairs_skipped": residual.nonadjacent_face_pairs_skipped,
            "predicted_distance_piece_pairs": residual.predicted_distance_piece_pairs,
            "evaluated_distance_piece_pairs": residual.evaluated_distance_piece_pairs,
        },
        "pairs": [_pair_json(pair) for pair in classified],
    }
    digest = sha256(_HASH_DOMAIN + jcs_bytes(payload)).hexdigest()
    return AdjacentClearanceDiagnostic(
        STATUS, VERSION, decoded.source_sha256, decoded.parser_name, decoded.parser_version,
        media_type, decoded.coordinate_frame_id, vertex_count, len(decoded.faces),
        profile.profile_id, profile.profile_version, profile.record_sha256, profile.policy_id,
        str(lam.numerator), str(lam.denominator), str(threshold.numerator),
        str(threshold.denominator), "LESS_THAN_OR_EQUAL", str(diameter_squared.numerator),
        str(diameter_squared.denominator), max_vertex_pairs, required_vertex_pairs,
        residual.diagnostic_sha256, residual.required_face_pairs,
        residual.adjacent_face_pair_count, residual.nonadjacent_face_pairs_skipped,
        residual.predicted_distance_piece_pairs, residual.evaluated_distance_piece_pairs,
        classified, digest,
    )


def _classify(pair: MeshAdjacentResidualPair, limit_squared: Fraction) -> AdjacentClearancePair:
    distance = Fraction(int(pair.squared_distance_numerator_mm2),
                        int(pair.squared_distance_denominator_mm2))
    return AdjacentClearancePair(
        pair.ordered_face_indices, pair.source_face_indices, pair.shared_entity,
        pair.shared_source_vertex_indices, pair.squared_distance_numerator_mm2,
        pair.squared_distance_denominator_mm2,
        "WITHIN_THRESHOLD" if distance <= limit_squared else "ABOVE_THRESHOLD",
        pair.evaluated_piece_pairs,
    )


def _pair_json(pair: AdjacentClearancePair) -> dict[str, JSONValue]:
    return {
        "ordered_face_indices": list(pair.ordered_face_indices),
        "source_face_indices": list(pair.source_face_indices),
        "shared_entity": pair.shared_entity,
        "shared_source_vertex_indices": list(pair.shared_source_vertex_indices),
        "distance_squared_mm2": {
            "numerator": pair.squared_distance_numerator_mm2,
            "denominator": pair.squared_distance_denominator_mm2,
        },
        "normalized_threshold_state": pair.normalized_threshold_state,
        "evaluated_piece_pairs": pair.evaluated_piece_pairs,
    }
