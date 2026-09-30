"""Exact algebraic signed six-volume diagnostic for closed mesh components."""

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
from .target_mesh_topology import (
    TopologyDiagnostic,
    diagnose_indexed_triangle_mesh,
)
from .v0_numeric_profile import (
    V0NumericProfile,
    resolve_v0_numeric_profile,
)

VOLUME_STATUS = "VOLUME_DIAGNOSTIC_ONLY"
VOLUME_VERSION = "1.0.0"
PREDICATE_BACKEND = "python-fractions-exact-binary64-rational"
PREDICATE_BACKEND_VERSION = "1.0.0"
_HASH_DOMAIN = b"TARGET_MESH_SIGNED_SIX_VOLUME_DIAGNOSTIC_V1\0"


class MeshVolumeError(ValueError):
    """The supplied source, evidence, profile, or work budget is invalid."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ComponentVolumeDiagnostic:
    face_indices: tuple[int, ...]
    reference_vertex_index: int
    signed_six_volume_numerator_mm3: str
    signed_six_volume_denominator_mm3: str
    status: str
    decision: str
    ineligibility_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SignedSixVolumeDiagnostic:
    status: str
    algorithm_version: str
    predicate_backend: str
    predicate_backend_version: str
    source_sha256: str
    parser_name: str
    parser_version: str
    media_type: str
    coordinate_frame_id: str
    numerical_profile_id: str
    numerical_profile_version: str
    numerical_profile_record_sha256: str
    topology_diagnostic_sha256: str
    vertex_count: int
    face_count: int
    max_bytes: int
    max_vertices: int
    max_faces: int
    max_vertex_pairs_evaluated: int
    required_vertex_pairs: int
    vertex_pairs_evaluated: int
    squared_diameter_numerator_mm2: str
    squared_diameter_denominator_mm2: str
    components: tuple[ComponentVolumeDiagnostic, ...]
    self_intersection_state: str
    diagnostic_sha256: str


def _rational(value: Fraction) -> JSONValue:
    result: dict[str, JSONValue] = {
        "numerator": str(value.numerator),
        "denominator": str(value.denominator),
    }
    return result


def _point(position: tuple[float, float, float]) -> tuple[Fraction, Fraction, Fraction]:
    return (
        Fraction.from_float(position[0]),
        Fraction.from_float(position[1]),
        Fraction.from_float(position[2]),
    )


def _difference(
    left: tuple[Fraction, Fraction, Fraction],
    right: tuple[Fraction, Fraction, Fraction],
) -> tuple[Fraction, Fraction, Fraction]:
    return (
        left[0] - right[0],
        left[1] - right[1],
        left[2] - right[2],
    )


def _determinant(
    first: tuple[Fraction, Fraction, Fraction],
    second: tuple[Fraction, Fraction, Fraction],
    third: tuple[Fraction, Fraction, Fraction],
) -> Fraction:
    return (
        first[0] * (second[1] * third[2] - second[2] * third[1])
        - first[1] * (second[0] * third[2] - second[2] * third[0])
        + first[2] * (second[0] * third[1] - second[1] * third[0])
    )


def _squared_distance(
    left: tuple[Fraction, Fraction, Fraction],
    right: tuple[Fraction, Fraction, Fraction],
) -> Fraction:
    delta = _difference(left, right)
    return sum((coordinate * coordinate for coordinate in delta), Fraction(0))


def _payload(
    decoded: DecodedIndexedTriangleMesh,
    profile: V0NumericProfile,
    topology: TopologyDiagnostic,
    max_bytes: int,
    max_vertices: int,
    max_faces: int,
    max_vertex_pairs_evaluated: int,
    required_pairs: int,
    diameter_squared: Fraction,
    pair_count: int,
    components: tuple[ComponentVolumeDiagnostic, ...],
) -> JSONValue:
    payload: JSONValue = {
        "status": VOLUME_STATUS,
        "algorithm_version": VOLUME_VERSION,
        "predicate_backend": PREDICATE_BACKEND,
        "predicate_backend_version": PREDICATE_BACKEND_VERSION,
        "source_sha256": decoded.source_sha256,
        "parser_name": decoded.parser_name,
        "parser_version": decoded.parser_version,
        "media_type": decoded.media_type,
        "coordinate_frame_id": decoded.coordinate_frame_id,
        "numerical_profile": {
            "profile_id": profile.profile_id,
            "profile_version": profile.profile_version,
            "record_sha256": profile.record_sha256,
        },
        "topology_diagnostic_sha256": topology.diagnostic_sha256,
        "vertex_count": len(decoded.vertices_mm),
        "face_count": len(decoded.faces),
        "max_bytes": max_bytes,
        "max_vertices": max_vertices,
        "max_faces": max_faces,
        "max_vertex_pairs_evaluated": max_vertex_pairs_evaluated,
        "required_vertex_pairs": required_pairs,
        "vertex_pairs_evaluated": pair_count,
        "squared_diameter_mm2": _rational(diameter_squared),
        "components": [
            {
                "face_indices": list(component.face_indices),
                "reference_vertex_index": component.reference_vertex_index,
                "signed_six_volume_mm3": {
                    "numerator": component.signed_six_volume_numerator_mm3,
                    "denominator": component.signed_six_volume_denominator_mm3,
                },
                "status": component.status,
                "decision": component.decision,
                "ineligibility_reasons": list(component.ineligibility_reasons),
            }
            for component in components
        ],
        "self_intersection_state": "UNRESOLVED",
    }
    return payload


def _check_budget(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise MeshVolumeError("volume.max_vertex_pairs_evaluated_invalid")


def diagnose_indexed_triangle_mesh_signed_six_volume(
    raw_bytes: bytes,
    decoded: DecodedIndexedTriangleMesh,
    topology: TopologyDiagnostic,
    profile: V0NumericProfile,
    *,
    media_type: str,
    expected_coordinate_frame_id: str,
    profile_bytes: bytes | None = None,
    max_bytes: int,
    max_vertices: int,
    max_faces: int,
    max_vertex_pairs_evaluated: int,
) -> SignedSixVolumeDiagnostic:
    """Report exact signed six-volume, without normalizing winding or claiming V0 pass."""
    _check_budget(max_vertex_pairs_evaluated)
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
        raise MeshVolumeError("volume.source_invalid") from error
    if source_decoded != decoded:
        raise MeshVolumeError("volume.decoded_source_mismatch")
    if (
        decoded.media_type != media_type
        or decoded.coordinate_frame_id != expected_coordinate_frame_id
    ):
        raise MeshVolumeError("volume.decoded_source_mismatch")
    if not isinstance(profile, V0NumericProfile):
        raise MeshVolumeError("volume.profile_invalid")
    try:
        resolved_profile = resolve_v0_numeric_profile(profile.profile_id, profile_bytes)
    except (ValueError, TypeError) as error:
        raise MeshVolumeError("volume.profile_unresolved") from error
    if resolved_profile != profile:
        raise MeshVolumeError("volume.profile_mismatch")
    try:
        actual_topology = diagnose_indexed_triangle_mesh(
            raw_bytes,
            decoded,
            media_type=media_type,
            expected_coordinate_frame_id=expected_coordinate_frame_id,
            max_bytes=max_bytes,
            max_vertices=max_vertices,
            max_faces=max_faces,
        )
    except (ValueError, TypeError) as error:
        raise MeshVolumeError("volume.topology_invalid") from error
    if actual_topology != topology:
        raise MeshVolumeError("volume.topology_mismatch")
    if topology.issues or topology.boundary_edge_count or topology.orientable is not True:
        raise MeshVolumeError("volume.topology_ineligible")

    vertex_count = len(decoded.vertices_mm)
    required_pairs = vertex_count * (vertex_count - 1) // 2
    if required_pairs > max_vertex_pairs_evaluated:
        raise MeshVolumeError("volume.vertex_pair_budget_exhausted")
    positions = tuple(_point(position) for position in decoded.vertices_mm)
    diameter_squared = Fraction(0)
    pair_count = 0
    for left in range(vertex_count):
        for right in range(left + 1, vertex_count):
            diameter_squared = max(
                diameter_squared, _squared_distance(positions[left], positions[right])
            )
            pair_count += 1
    if diameter_squared <= 0:
        raise MeshVolumeError("volume.zero_diameter")

    output_components: list[ComponentVolumeDiagnostic] = []
    for face_indices in topology.component_face_indices:
        component_vertices = sorted(
            {vertex for face_index in face_indices for vertex in decoded.faces[face_index]}
        )
        reference_index = component_vertices[0]
        reference = positions[reference_index]
        signed_six_volume = Fraction(0)
        for face_index in face_indices:
            first, second, third = decoded.faces[face_index]
            signed_six_volume += _determinant(
                _difference(positions[first], reference),
                _difference(positions[second], reference),
                _difference(positions[third], reference),
            )
        stability_limit = Fraction.from_float(
            resolved_profile.thresholds.volume6_normalized_min_exclusive
        )
        if signed_six_volume * signed_six_volume <= stability_limit**2 * diameter_squared**3:
            component_status, decision = "INDETERMINATE", "NO_REVERSAL"
        else:
            component_status = "ALGEBRAIC_SIGN_STABLE"
            decision = (
                "ALGEBRAIC_POSITIVE_SIGN_NO_OUTWARD_CLAIM"
                if signed_six_volume > 0
                else "ALGEBRAIC_NEGATIVE_SIGN_POTENTIAL_WHOLE_COMPONENT_REVERSAL_ONLY"
            )
        output_components.append(
            ComponentVolumeDiagnostic(
                face_indices=face_indices,
                reference_vertex_index=reference_index,
                signed_six_volume_numerator_mm3=str(signed_six_volume.numerator),
                signed_six_volume_denominator_mm3=str(signed_six_volume.denominator),
                status=component_status,
                decision=decision,
                ineligibility_reasons=(),
            )
        )
    components = tuple(output_components)
    payload = _payload(
        decoded,
        resolved_profile,
        topology,
        max_bytes,
        max_vertices,
        max_faces,
        max_vertex_pairs_evaluated,
        required_pairs,
        diameter_squared,
        pair_count,
        components,
    )
    digest = sha256(_HASH_DOMAIN + jcs_bytes(payload)).hexdigest()
    return SignedSixVolumeDiagnostic(
        status=VOLUME_STATUS,
        algorithm_version=VOLUME_VERSION,
        predicate_backend=PREDICATE_BACKEND,
        predicate_backend_version=PREDICATE_BACKEND_VERSION,
        source_sha256=decoded.source_sha256,
        parser_name=decoded.parser_name,
        parser_version=decoded.parser_version,
        media_type=decoded.media_type,
        coordinate_frame_id=decoded.coordinate_frame_id,
        numerical_profile_id=resolved_profile.profile_id,
        numerical_profile_version=resolved_profile.profile_version,
        numerical_profile_record_sha256=resolved_profile.record_sha256,
        topology_diagnostic_sha256=topology.diagnostic_sha256,
        vertex_count=vertex_count,
        face_count=len(decoded.faces),
        max_bytes=max_bytes,
        max_vertices=max_vertices,
        max_faces=max_faces,
        max_vertex_pairs_evaluated=max_vertex_pairs_evaluated,
        required_vertex_pairs=required_pairs,
        vertex_pairs_evaluated=pair_count,
        squared_diameter_numerator_mm2=str(diameter_squared.numerator),
        squared_diameter_denominator_mm2=str(diameter_squared.denominator),
        components=components,
        self_intersection_state="UNRESOLVED",
        diagnostic_sha256=digest,
    )
