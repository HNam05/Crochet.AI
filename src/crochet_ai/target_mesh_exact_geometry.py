"""Exact-coordinate geometry findings for decoded indexed triangle meshes.

This module reports exact coordinate equality and exact zero-area triangles. It
does not perform V0 acceptance or apply a numerical geometry profile.
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

EXACT_GEOMETRY_STATUS = "EXACT_GEOMETRY_DIAGNOSTIC_ONLY"
EXACT_GEOMETRY_VERSION = "1.0.0"
_HASH_DOMAIN = b"EXACT_MESH_GEOMETRY_DIAGNOSTIC_V1\0"


class MeshGeometryError(ValueError):
    """The source cannot support an exact geometry diagnostic."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class CoincidentVertexGroup:
    """Distinct vertex identities with exactly equal represented coordinates."""

    vertex_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ZeroAreaFace:
    """A face whose represented binary64 coordinates are exactly collinear."""

    face_index: int


@dataclass(frozen=True, slots=True)
class ExactGeometryDiagnostic:
    status: str
    algorithm_version: str
    source_sha256: str
    parser_name: str
    parser_version: str
    media_type: str
    vertex_count: int
    face_count: int
    coincident_vertex_groups: tuple[CoincidentVertexGroup, ...]
    zero_area_faces: tuple[ZeroAreaFace, ...]
    diagnostic_sha256: str

    @property
    def coincident_vertex_group_count(self) -> int:
        return len(self.coincident_vertex_groups)

    @property
    def zero_area_face_count(self) -> int:
        return len(self.zero_area_faces)


def _cross_is_zero(
    first: tuple[float, float, float],
    second: tuple[float, float, float],
    third: tuple[float, float, float],
) -> bool:
    """Return whether the exact rational cross product is zero."""
    p0 = tuple(Fraction.from_float(value) for value in first)
    p1 = tuple(Fraction.from_float(value) for value in second)
    p2 = tuple(Fraction.from_float(value) for value in third)
    a = tuple(p1[index] - p0[index] for index in range(3))
    b = tuple(p2[index] - p0[index] for index in range(3))
    cross = (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )
    return all(component == 0 for component in cross)


def diagnose_indexed_triangle_mesh_exact_geometry(
    raw_bytes: bytes,
    decoded: DecodedIndexedTriangleMesh,
    *,
    media_type: str,
    expected_coordinate_frame_id: str,
    max_bytes: int,
    max_vertices: int,
    max_faces: int,
) -> ExactGeometryDiagnostic:
    """Re-decode source under caller budgets and report exact geometry only."""
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
        raise MeshGeometryError("exact_geometry.source_invalid") from error
    if source_decoded != decoded:
        raise MeshGeometryError("exact_geometry.decoded_source_mismatch")

    coordinate_indices: dict[tuple[float, float, float], list[int]] = {}
    for vertex_index, position in enumerate(decoded.vertices_mm):
        coordinate_indices.setdefault(position, []).append(vertex_index)
    coincident_groups = tuple(
        CoincidentVertexGroup(tuple(indices))
        for _, indices in sorted(coordinate_indices.items())
        if len(indices) > 1
    )

    zero_area_faces = tuple(
        ZeroAreaFace(face_index)
        for face_index, (i0, i1, i2) in enumerate(decoded.faces)
        if _cross_is_zero(
            decoded.vertices_mm[i0], decoded.vertices_mm[i1], decoded.vertices_mm[i2]
        )
    )

    payload: JSONValue = {
        "algorithm_version": EXACT_GEOMETRY_VERSION,
        "status": EXACT_GEOMETRY_STATUS,
        "source_sha256": decoded.source_sha256,
        "parser_name": decoded.parser_name,
        "parser_version": decoded.parser_version,
        "media_type": decoded.media_type,
        "vertex_count": len(decoded.vertices_mm),
        "face_count": len(decoded.faces),
        "coincident_vertex_groups": [
            {"vertex_indices": list(group.vertex_indices)} for group in coincident_groups
        ],
        "zero_area_faces": [{"face_index": item.face_index} for item in zero_area_faces],
    }
    digest = sha256(_HASH_DOMAIN + jcs_bytes(payload)).hexdigest()
    return ExactGeometryDiagnostic(
        status=EXACT_GEOMETRY_STATUS,
        algorithm_version=EXACT_GEOMETRY_VERSION,
        source_sha256=decoded.source_sha256,
        parser_name=decoded.parser_name,
        parser_version=decoded.parser_version,
        media_type=decoded.media_type,
        vertex_count=len(decoded.vertices_mm),
        face_count=len(decoded.faces),
        coincident_vertex_groups=coincident_groups,
        zero_area_faces=zero_area_faces,
        diagnostic_sha256=digest,
    )
