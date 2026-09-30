"""Bounded exact nonadjacent target-mesh contact diagnostic (not V0 acceptance)."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from itertools import combinations

from .canonical import jcs_bytes
from .exact_triangle_distance import triangle_distance_squared
from .exact_triangle_relation import ExactTriangleRelationError
from .json_types import JSONValue
from .target_mesh_decode import (
    DecodedIndexedTriangleMesh,
    MeshDecodeError,
    decode_indexed_triangle_mesh,
)
from .target_mesh_topology import (
    MeshTopologyError,
    TopologyDiagnostic,
    diagnose_indexed_triangle_mesh,
)
from .v0_numeric_profile import (
    PROFILE_ID,
    NumericalGeometryProfileError,
    V0NumericProfile,
    resolve_v0_numeric_profile,
)

STATUS = "NEAR_CONTACT_DIAGNOSTIC_ONLY"
VERSION = "1.0.0"
_HASH_DOMAIN = b"TARGET_MESH_NEAR_CONTACT_DIAGNOSTIC_V1\0"
_EXPECTED_THRESHOLD = Fraction(1, 1 << 40)


class MeshNearContactError(ValueError):
    """Source, profile, or explicit work budget cannot support this diagnostic."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class NearContactPair:
    face_indices: tuple[int, int]
    squared_distance_numerator_mm2: str
    squared_distance_denominator_mm2: str
    component_relation: str


@dataclass(frozen=True, slots=True)
class NearContactDiagnostic:
    status: str
    algorithm_version: str
    source_sha256: str
    parser_name: str
    parser_version: str
    media_type: str
    coordinate_frame_id: str
    vertex_count: int
    face_count: int
    topology_diagnostic_sha256: str
    profile_id: str
    profile_version: str
    profile_sha256: str
    threshold_numerator: str
    threshold_denominator: str
    required_vertex_pairs: int
    vertex_pairs_evaluated: int
    max_vertex_pairs: int
    required_face_pairs: int
    face_pairs_enumerated: int
    nonadjacent_face_pairs_evaluated: int
    adjacent_face_pairs_skipped: int
    adjacent_residual_state: str
    max_face_pairs: int
    squared_diameter_numerator_mm2: str
    squared_diameter_denominator_mm2: str
    minimum_nonadjacent_squared_distance_numerator_mm2: str | None
    minimum_nonadjacent_squared_distance_denominator_mm2: str | None
    exact_zero_pairs: tuple[NearContactPair, ...]
    near_contact_pairs: tuple[NearContactPair, ...]
    diagnostic_sha256: str


def _point(mesh: DecodedIndexedTriangleMesh, index: int) -> tuple[Fraction, Fraction, Fraction]:
    position = mesh.vertices_mm[index]
    return (
        Fraction.from_float(position[0]),
        Fraction.from_float(position[1]),
        Fraction.from_float(position[2]),
    )


def _distance_squared(
    first: tuple[Fraction, Fraction, Fraction],
    second: tuple[Fraction, Fraction, Fraction],
) -> Fraction:
    return sum(((first[i] - second[i]) ** 2 for i in range(3)), Fraction(0))


def _zero_area(mesh: DecodedIndexedTriangleMesh, face: tuple[int, int, int]) -> bool:
    a, b, c = (_point(mesh, index) for index in face)
    ab = tuple(b[i] - a[i] for i in range(3))
    ac = tuple(c[i] - a[i] for i in range(3))
    cross = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    return all(value == 0 for value in cross)


def diagnose_indexed_triangle_mesh_near_contact(
    raw_bytes: bytes,
    decoded: DecodedIndexedTriangleMesh,
    topology: TopologyDiagnostic,
    *,
    profile: V0NumericProfile,
    media_type: str,
    expected_coordinate_frame_id: str,
    max_bytes: int,
    max_vertices: int,
    max_faces: int,
    max_vertex_pairs: int,
    max_face_pairs: int,
) -> NearContactDiagnostic:
    """Report exact nonadjacent zero and <= profile-relative contact pairs.

    Pairs sharing any indexed vertex are explicitly skipped. Their residual
    overlap/contact beyond intended adjacency remains unresolved by this API.
    """
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
        raise MeshNearContactError("near_contact.source_invalid") from error
    if source_decoded != decoded:
        raise MeshNearContactError("near_contact.decoded_source_mismatch")

    try:
        current_topology = diagnose_indexed_triangle_mesh(
            raw_bytes,
            decoded,
            media_type=media_type,
            expected_coordinate_frame_id=expected_coordinate_frame_id,
            max_bytes=max_bytes,
            max_vertices=max_vertices,
            max_faces=max_faces,
        )
    except (MeshTopologyError, ValueError) as error:
        raise MeshNearContactError("near_contact.topology_unavailable") from error
    if current_topology != topology:
        raise MeshNearContactError("near_contact.topology_mismatch")

    if not isinstance(profile, V0NumericProfile):
        raise MeshNearContactError("near_contact.profile_invalid")
    try:
        current_profile = resolve_v0_numeric_profile(PROFILE_ID)
    except NumericalGeometryProfileError as error:
        raise MeshNearContactError("near_contact.profile_unresolved") from error
    if current_profile != profile:
        raise MeshNearContactError("near_contact.profile_mismatch")
    threshold = Fraction.from_float(profile.thresholds.near_contact_distance_normalized_max)
    if threshold != _EXPECTED_THRESHOLD:
        raise MeshNearContactError("near_contact.unsupported_threshold")

    for name, budget in (
        ("max_vertex_pairs", max_vertex_pairs),
        ("max_face_pairs", max_face_pairs),
    ):
        if isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0:
            raise MeshNearContactError(f"near_contact.{name}_invalid")
    vertex_count = len(decoded.vertices_mm)
    face_count = len(decoded.faces)
    required_vertex_pairs = vertex_count * (vertex_count - 1) // 2
    required_face_pairs = face_count * (face_count - 1) // 2
    # Both whole-work prechecks happen before either quadratic enumeration.
    if required_vertex_pairs > max_vertex_pairs:
        raise MeshNearContactError("near_contact.vertex_pair_budget_exhausted")
    if required_face_pairs > max_face_pairs:
        raise MeshNearContactError("near_contact.face_pair_budget_exhausted")

    zero_area = tuple(
        index for index, face in enumerate(decoded.faces) if _zero_area(decoded, face)
    )
    if zero_area:
        raise MeshNearContactError("near_contact.zero_area_face")

    positions = tuple(_point(decoded, index) for index in range(vertex_count))
    diameter_squared = Fraction(0)
    for left, right in combinations(range(vertex_count), 2):
        diameter_squared = max(
            diameter_squared, _distance_squared(positions[left], positions[right])
        )
    if diameter_squared <= 0:
        raise MeshNearContactError("near_contact.zero_scale")

    component_by_face = {
        face_index: component_index
        for component_index, component in enumerate(topology.component_face_indices)
        for face_index in component
    }
    exact_zero: list[NearContactPair] = []
    near: list[NearContactPair] = []
    minimum: Fraction | None = None
    adjacent_skipped = 0
    nonadjacent_evaluated = 0
    threshold_squared = threshold**2 * diameter_squared
    try:
        for first_index, second_index in combinations(range(face_count), 2):
            first_ids, second_ids = decoded.faces[first_index], decoded.faces[second_index]
            if set(first_ids).intersection(second_ids):
                adjacent_skipped += 1
                continue
            first = tuple(positions[index] for index in first_ids)
            second = tuple(positions[index] for index in second_ids)
            first_triangle = (first[0], first[1], first[2])
            second_triangle = (second[0], second[1], second[2])
            distance = triangle_distance_squared(first_triangle, second_triangle)
            nonadjacent_evaluated += 1
            minimum = distance if minimum is None else min(minimum, distance)
            relation = (
                "SAME_FACE_COMPONENT"
                if component_by_face[first_index] == component_by_face[second_index]
                else "DIFFERENT_FACE_COMPONENTS"
            )
            if distance == 0:
                exact_zero.append(NearContactPair((first_index, second_index), "0", "1", relation))
            elif distance <= threshold_squared:
                near.append(
                    NearContactPair(
                        (first_index, second_index),
                        str(distance.numerator),
                        str(distance.denominator),
                        relation,
                    )
                )
    except ExactTriangleRelationError as error:
        raise MeshNearContactError("near_contact.exact_distance_failed") from error

    def rational_pair(value: Fraction | None) -> tuple[str | None, str | None]:
        if value is None:
            return None, None
        return str(value.numerator), str(value.denominator)

    min_num, min_den = rational_pair(minimum)
    payload: JSONValue = {
        "status": STATUS,
        "algorithm_version": VERSION,
        "source": {
            "sha256": decoded.source_sha256,
            "parser_name": decoded.parser_name,
            "parser_version": decoded.parser_version,
            "media_type": decoded.media_type,
            "coordinate_frame_id": decoded.coordinate_frame_id,
            "vertex_count": vertex_count,
            "face_count": face_count,
        },
        "topology_diagnostic_sha256": topology.diagnostic_sha256,
        "profile": {"id": profile.profile_id, "version": profile.profile_version,
                    "sha256": profile.record_sha256},
        "threshold": {"numerator": str(threshold.numerator),
                       "denominator": str(threshold.denominator),
                       "operator": "LESS_THAN_OR_EQUAL"},
        "budget": {"required_vertex_pairs": required_vertex_pairs,
                   "vertex_pairs_evaluated": required_vertex_pairs,
                   "max_vertex_pairs": max_vertex_pairs,
                   "required_face_pairs": required_face_pairs,
                   "face_pairs_enumerated": required_face_pairs,
                   "nonadjacent_face_pairs_evaluated": nonadjacent_evaluated,
                   "adjacent_face_pairs_skipped": adjacent_skipped,
                   "adjacent_residual_state": "UNRESOLVED",
                   "max_face_pairs": max_face_pairs},
        "squared_diameter_mm2": {"numerator": str(diameter_squared.numerator),
                                  "denominator": str(diameter_squared.denominator)},
        "minimum_nonadjacent_squared_distance_mm2": (
            None if minimum is None else {"numerator": min_num, "denominator": min_den}),
        "exact_zero_pairs": [_pair_json(item) for item in exact_zero],
        "near_contact_pairs": [_pair_json(item) for item in near],
    }
    digest = sha256(_HASH_DOMAIN + jcs_bytes(payload)).hexdigest()
    return NearContactDiagnostic(
        STATUS, VERSION, decoded.source_sha256, decoded.parser_name, decoded.parser_version,
        decoded.media_type, decoded.coordinate_frame_id, vertex_count, face_count,
        topology.diagnostic_sha256, profile.profile_id, profile.profile_version,
        profile.record_sha256, str(threshold.numerator), str(threshold.denominator),
        required_vertex_pairs, required_vertex_pairs, max_vertex_pairs, required_face_pairs,
        required_face_pairs, nonadjacent_evaluated, adjacent_skipped, "UNRESOLVED", max_face_pairs,
        str(diameter_squared.numerator), str(diameter_squared.denominator),
        min_num, min_den, tuple(exact_zero), tuple(near), digest,
    )


def _pair_json(pair: NearContactPair) -> dict[str, JSONValue]:
    return {
        "face_indices": list(pair.face_indices),
        "squared_distance_mm2": {
            "numerator": pair.squared_distance_numerator_mm2,
            "denominator": pair.squared_distance_denominator_mm2,
        },
        "component_relation": pair.component_relation,
    }
