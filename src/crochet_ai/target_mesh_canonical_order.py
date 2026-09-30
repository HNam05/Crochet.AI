"""Non-destructive canonical ordering diagnostic for indexed triangle meshes.

This stage records canonical data layout only. It does not perform V0
acceptance, component or boundary ordering, or winding changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from .canonical import jcs_bytes
from .json_types import JSONValue
from .target_mesh_decode import (
    DecodedIndexedTriangleMesh,
    MeshDecodeError,
    decode_indexed_triangle_mesh,
)
from .target_mesh_exact_geometry import (
    MeshGeometryError,
    diagnose_indexed_triangle_mesh_exact_geometry,
)
from .target_mesh_topology import MeshTopologyError, diagnose_indexed_triangle_mesh

ORDERING_STATUS = "ORDERING_DIAGNOSTIC_ONLY"
ORDERING_VERSION = "1.0.0"
IDENTITY_UNAVAILABLE_REASON = "v0_geometry_and_normalization_unverified"
_REPORT_DOMAIN = b"TARGET_MESH_CANONICAL_ORDER_DIAGNOSTIC_V1\0"


class MeshCanonicalOrderError(ValueError):
    """The source or decoded record is invalid or does not match."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class CanonicalOrderDiagnostic:
    status: str
    algorithm_version: str
    source_sha256: str
    topology_diagnostic_sha256: str
    exact_geometry_diagnostic_sha256: str
    source_to_derived_vertex_indices: tuple[int, ...]
    derived_to_source_vertex_indices: tuple[int, ...]
    source_to_derived_face_indices: tuple[int, ...]
    derived_to_source_face_indices: tuple[int, ...]
    derived_vertices_mm: tuple[tuple[float, float, float], ...]
    derived_faces: tuple[tuple[int, int, int], ...]
    identity_unavailable_reason: str | None
    diagnostic_sha256: str


def diagnose_indexed_triangle_mesh_canonical_order(
    raw_bytes: bytes,
    decoded: DecodedIndexedTriangleMesh,
    *,
    media_type: str,
    expected_coordinate_frame_id: str,
    max_bytes: int,
    max_vertices: int,
    max_faces: int,
) -> CanonicalOrderDiagnostic:
    """Sort vertices/faces under the geometry contract, retaining both maps."""
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
        raise MeshCanonicalOrderError("canonical_order.source_invalid") from error
    if source_decoded != decoded:
        raise MeshCanonicalOrderError("canonical_order.decoded_source_mismatch")

    try:
        topology = diagnose_indexed_triangle_mesh(
            raw_bytes,
            decoded,
            media_type=media_type,
            expected_coordinate_frame_id=expected_coordinate_frame_id,
            max_bytes=max_bytes,
            max_vertices=max_vertices,
            max_faces=max_faces,
        )
        geometry = diagnose_indexed_triangle_mesh_exact_geometry(
            raw_bytes,
            decoded,
            media_type=media_type,
            expected_coordinate_frame_id=expected_coordinate_frame_id,
            max_bytes=max_bytes,
            max_vertices=max_vertices,
            max_faces=max_faces,
        )
    except (MeshTopologyError, MeshGeometryError) as error:
        raise MeshCanonicalOrderError("canonical_order.source_revalidation_failed") from error

    issue_codes = sorted({issue.code for issue in topology.issues})
    reasons: list[str] = []
    if issue_codes:
        reasons.append("index_topology_invalid:" + ",".join(issue_codes))
    if topology.orientable is not True:
        reasons.append("index_topology_not_orientable")
    if geometry.coincident_vertex_groups:
        reasons.append("exactly_coincident_vertices")
    if geometry.zero_area_faces:
        reasons.append("zero_area_faces")

    source_to_vertices: tuple[int, ...] = ()
    derived_to_vertices: tuple[int, ...] = ()
    source_to_faces: tuple[int, ...] = ()
    derived_to_faces: tuple[int, ...] = ()
    vertices_out: tuple[tuple[float, float, float], ...] = ()
    faces_out: tuple[tuple[int, int, int], ...] = ()
    if not reasons:
        # Negative zero has the same canonical numeric value as positive zero.
        canonical_positions: tuple[tuple[float, float, float], ...] = tuple(
            (
                0.0 if point[0] == 0.0 else point[0],
                0.0 if point[1] == 0.0 else point[1],
                0.0 if point[2] == 0.0 else point[2],
            )
            for point in decoded.vertices_mm
        )
        derived_to_vertices = tuple(
            sorted(range(len(canonical_positions)), key=canonical_positions.__getitem__)
        )
        vertex_map = [0] * len(derived_to_vertices)
        for derived_index, source_index in enumerate(derived_to_vertices):
            vertex_map[source_index] = derived_index
        source_to_vertices = tuple(vertex_map)
        vertices_out = tuple(canonical_positions[index] for index in derived_to_vertices)

        remapped: list[tuple[tuple[int, int, int], int]] = []
        for source_index, face in enumerate(decoded.faces):
            mapped: tuple[int, int, int] = (
                source_to_vertices[face[0]],
                source_to_vertices[face[1]],
                source_to_vertices[face[2]],
            )
            smallest = mapped.index(min(mapped))
            rotated: tuple[int, int, int] = (
                mapped[smallest],
                mapped[(smallest + 1) % 3],
                mapped[(smallest + 2) % 3],
            )
            remapped.append((rotated, source_index))
        remapped.sort(key=lambda item: item[0])
        faces_out = tuple(face for face, _ in remapped)
        derived_to_faces = tuple(source_index for _, source_index in remapped)
        face_map = [0] * len(derived_to_faces)
        for derived_index, source_index in enumerate(derived_to_faces):
            face_map[source_index] = derived_index
        source_to_faces = tuple(face_map)

    unavailable = ";".join([*reasons, IDENTITY_UNAVAILABLE_REASON])
    report_payload: JSONValue = {
        "algorithm_version": ORDERING_VERSION,
        "status": ORDERING_STATUS,
        "source_sha256": decoded.source_sha256,
        "topology_diagnostic_sha256": topology.diagnostic_sha256,
        "exact_geometry_diagnostic_sha256": geometry.diagnostic_sha256,
        "source_to_derived_vertex_indices": list(source_to_vertices),
        "derived_to_source_vertex_indices": list(derived_to_vertices),
        "source_to_derived_face_indices": list(source_to_faces),
        "derived_to_source_face_indices": list(derived_to_faces),
        "derived_vertices_mm": [list(point) for point in vertices_out],
        "derived_faces": [list(face) for face in faces_out],
        "identity_unavailable_reason": unavailable,
    }
    report_hash = sha256(_REPORT_DOMAIN + jcs_bytes(report_payload)).hexdigest()
    return CanonicalOrderDiagnostic(
        status=ORDERING_STATUS,
        algorithm_version=ORDERING_VERSION,
        source_sha256=decoded.source_sha256,
        topology_diagnostic_sha256=topology.diagnostic_sha256,
        exact_geometry_diagnostic_sha256=geometry.diagnostic_sha256,
        source_to_derived_vertex_indices=source_to_vertices,
        derived_to_source_vertex_indices=derived_to_vertices,
        source_to_derived_face_indices=source_to_faces,
        derived_to_source_face_indices=derived_to_faces,
        derived_vertices_mm=vertices_out,
        derived_faces=faces_out,
        identity_unavailable_reason=unavailable,
        diagnostic_sha256=report_hash,
    )
