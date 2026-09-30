"""Exact-rational diagnostics for two immutable V0 relative mesh thresholds.

This module is diagnostic only. It does not establish V0 acceptance and does
not implement a filtered adaptive sign backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256

from .canonical import jcs_bytes
from .json_types import JSONValue
from .target_mesh_decode import (
    DecodedIndexedTriangleMesh,
    MeshDecodeError,
    decode_indexed_triangle_mesh,
)
from .v0_numeric_profile import (
    PROFILE_ID,
    NumericalGeometryProfileError,
    V0NumericProfile,
    resolve_v0_numeric_profile,
)

STATUS = "DIAGNOSTIC_ONLY"
VERSION = "1.0.0"
PREDICATE_BACKEND = "EXACT_BINARY64_RATIONAL_V1"
_HASH_DOMAIN = b"TARGET_MESH_RELATIVE_THRESHOLDS_DIAGNOSTIC_V1\0"


class RelativeThresholdDiagnosticError(ValueError):
    """Input, profile, or budget cannot support a bounded diagnostic."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class RelativeThresholdDiagnostic:
    status: str
    algorithm_version: str
    predicate_backend: str
    source_sha256: str
    parser_name: str
    parser_version: str
    media_type: str
    vertex_count: int
    face_count: int
    profile_id: str
    profile_version: str
    profile_sha256: str
    required_pair_evaluations: int
    pair_evaluations: int
    max_pair_evaluations: int
    squared_diameter_numerator_mm2: str
    squared_diameter_denominator_mm2: str
    exact_coincident_vertex_groups: tuple[tuple[int, ...], ...]
    exact_zero_area_faces: tuple[int, ...]
    near_coincident_vertex_pairs: tuple[tuple[int, int], ...]
    near_zero_area_faces: tuple[int, ...]
    diagnostic_sha256: str


def _distance_squared(
    first: tuple[Fraction, Fraction, Fraction],
    second: tuple[Fraction, Fraction, Fraction],
) -> Fraction:
    return sum(((first[i] - second[i]) ** 2 for i in range(3)), Fraction(0))


def _cross_squared(
    first: tuple[Fraction, Fraction, Fraction],
    second: tuple[Fraction, Fraction, Fraction],
    third: tuple[Fraction, Fraction, Fraction],
) -> Fraction:
    a = tuple(second[i] - first[i] for i in range(3))
    b = tuple(third[i] - first[i] for i in range(3))
    cross = (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )
    return sum((component * component for component in cross), Fraction(0))


def _rational(value: Fraction) -> dict[str, JSONValue]:
    return {"numerator": str(value.numerator), "denominator": str(value.denominator)}


def diagnose_indexed_triangle_mesh_relative_thresholds(
    raw_bytes: bytes,
    decoded: DecodedIndexedTriangleMesh,
    *,
    profile: V0NumericProfile,
    media_type: str,
    expected_coordinate_frame_id: str,
    max_bytes: int,
    max_vertices: int,
    max_faces: int,
    max_pair_evaluations: int,
) -> RelativeThresholdDiagnostic:
    """Report exact comparisons for area2 and coordinate-distance thresholds."""
    try:
        source_decoded = decode_indexed_triangle_mesh(
            raw_bytes,
            media_type=media_type,
            expected_coordinate_frame_id=expected_coordinate_frame_id,
            max_bytes=max_bytes,
            max_vertices=max_vertices,
            max_faces=max_faces,
        )
    except (MeshDecodeError, ValueError) as error:
        raise RelativeThresholdDiagnosticError("relative_thresholds.source_invalid") from error
    if source_decoded != decoded:
        raise RelativeThresholdDiagnosticError("relative_thresholds.decoded_source_mismatch")

    if not isinstance(profile, V0NumericProfile):
        raise RelativeThresholdDiagnosticError("relative_thresholds.profile_invalid")
    try:
        builtin_profile = resolve_v0_numeric_profile(PROFILE_ID)
    except NumericalGeometryProfileError as error:
        raise RelativeThresholdDiagnosticError("relative_thresholds.profile_unresolved") from error
    if profile != builtin_profile:
        raise RelativeThresholdDiagnosticError("relative_thresholds.profile_mismatch")
    if (
        isinstance(max_pair_evaluations, bool)
        or not isinstance(max_pair_evaluations, int)
        or max_pair_evaluations <= 0
    ):
        raise RelativeThresholdDiagnosticError("relative_thresholds.pair_budget_invalid")

    vertex_count = len(decoded.vertices_mm)
    if vertex_count < 2:
        raise RelativeThresholdDiagnosticError("relative_thresholds.vertex_count_below_two")
    pair_count = vertex_count * (vertex_count - 1) // 2
    required = 2 * pair_count
    if required > max_pair_evaluations:
        raise RelativeThresholdDiagnosticError("relative_thresholds.pair_budget_exhausted")

    positions: tuple[tuple[Fraction, Fraction, Fraction], ...] = tuple(
        (
            Fraction.from_float(point[0]),
            Fraction.from_float(point[1]),
            Fraction.from_float(point[2]),
        )
        for point in decoded.vertices_mm
    )
    diameter_squared = Fraction(0)
    for left in range(vertex_count):
        for right in range(left + 1, vertex_count):
            diameter_squared = max(
                diameter_squared, _distance_squared(positions[left], positions[right])
            )
    if diameter_squared == 0:
        raise RelativeThresholdDiagnosticError("relative_thresholds.zero_scale")

    threshold_area = Fraction.from_float(profile.thresholds.triangle_area2_normalized_max)
    threshold_distance = Fraction.from_float(
        profile.thresholds.coordinate_distance_normalized_max
    )
    if threshold_area != Fraction(1, 1 << 40) or threshold_distance != Fraction(1, 1 << 40):
        raise RelativeThresholdDiagnosticError("relative_thresholds.unsupported_threshold")

    groups_by_position: dict[tuple[Fraction, Fraction, Fraction], list[int]] = {}
    for index, position in enumerate(positions):
        groups_by_position.setdefault(position, []).append(index)
    exact_groups = tuple(
        tuple(indices)
        for _, indices in sorted(groups_by_position.items())
        if len(indices) > 1
    )

    near_pairs: list[tuple[int, int]] = []
    evaluations = pair_count
    distance_limit_squared = threshold_distance**2 * diameter_squared
    for left in range(vertex_count):
        for right in range(left + 1, vertex_count):
            distance_squared = _distance_squared(positions[left], positions[right])
            if 0 < distance_squared <= distance_limit_squared:
                near_pairs.append((left, right))
    evaluations += pair_count

    exact_zero_faces: list[int] = []
    near_zero_faces: list[int] = []
    area_limit_squared = threshold_area**2 * diameter_squared**2
    for face_index, (i0, i1, i2) in enumerate(decoded.faces):
        area2_squared = _cross_squared(positions[i0], positions[i1], positions[i2])
        if area2_squared == 0:
            exact_zero_faces.append(face_index)
        if area2_squared <= area_limit_squared:
            near_zero_faces.append(face_index)

    exact_groups_tuple = tuple(sorted(exact_groups))
    exact_zero_tuple = tuple(exact_zero_faces)
    near_pairs_tuple = tuple(sorted(near_pairs))
    near_faces_tuple = tuple(near_zero_faces)
    payload: JSONValue = {
        "status": STATUS,
        "algorithm_version": VERSION,
        "predicate_backend": PREDICATE_BACKEND,
        "source": {
            "sha256": decoded.source_sha256,
            "parser_name": decoded.parser_name,
            "parser_version": decoded.parser_version,
            "media_type": decoded.media_type,
            "vertex_count": vertex_count,
            "face_count": len(decoded.faces),
        },
        "profile": {
            "id": profile.profile_id,
            "version": profile.profile_version,
            "sha256": profile.record_sha256,
            "threshold_fields": [
                "triangle_area2_normalized_max",
                "coordinate_distance_normalized_max",
            ],
        },
        "thresholds": {
            "triangle_area2_normalized_max": {
                "value": _rational(threshold_area),
                "operator": "LESS_THAN_OR_EQUAL",
            },
            "coordinate_distance_normalized_max": {
                "value": _rational(threshold_distance),
                "operator": "LESS_THAN_OR_EQUAL",
            },
        },
        "squared_diameter_mm2": _rational(diameter_squared),
        "budget": {
            "required_pair_evaluations": required,
            "pair_evaluations": evaluations,
            "max_pair_evaluations": max_pair_evaluations,
        },
        "exact_coincident_vertex_groups": [list(group) for group in exact_groups_tuple],
        "exact_zero_area_faces": list(exact_zero_tuple),
        "near_coincident_vertex_pairs": [list(pair) for pair in near_pairs_tuple],
        "near_zero_area_faces": list(near_faces_tuple),
    }
    digest = sha256(_HASH_DOMAIN + jcs_bytes(payload)).hexdigest()
    return RelativeThresholdDiagnostic(
        status=STATUS,
        algorithm_version=VERSION,
        predicate_backend=PREDICATE_BACKEND,
        source_sha256=decoded.source_sha256,
        parser_name=decoded.parser_name,
        parser_version=decoded.parser_version,
        media_type=decoded.media_type,
        vertex_count=vertex_count,
        face_count=len(decoded.faces),
        profile_id=profile.profile_id,
        profile_version=profile.profile_version,
        profile_sha256=profile.record_sha256,
        required_pair_evaluations=required,
        pair_evaluations=evaluations,
        max_pair_evaluations=max_pair_evaluations,
        squared_diameter_numerator_mm2=str(diameter_squared.numerator),
        squared_diameter_denominator_mm2=str(diameter_squared.denominator),
        exact_coincident_vertex_groups=exact_groups_tuple,
        exact_zero_area_faces=exact_zero_tuple,
        near_coincident_vertex_pairs=near_pairs_tuple,
        near_zero_area_faces=near_faces_tuple,
        diagnostic_sha256=digest,
    )
