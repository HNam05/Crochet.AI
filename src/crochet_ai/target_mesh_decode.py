"""Strict, decode-only adapter for self-describing indexed triangle mesh JSON."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import cast

from .canonical import CanonicalizationError, parse_json
from .diagnostics import ArtifactValidationError
from .json_types import JSONValue
from .schema import validate_schema

MESH_MEDIA_TYPE = "application/vnd.crochet.indexed-triangle-mesh+json"
PARSER_NAME = "crochet-ai-indexed-triangle-mesh-json"
PARSER_VERSION = "1.0.0"


class MeshDecodeError(ValueError):
    """Input cannot be decoded under the strict indexed mesh contract."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class DecodedIndexedTriangleMesh:
    representation_version: str
    coordinate_frame_id: str
    vertices_mm: tuple[tuple[float, float, float], ...]
    faces: tuple[tuple[int, int, int], ...]
    source_sha256: str
    parser_name: str
    parser_version: str
    media_type: str
    source_to_decoded_vertex_indices: tuple[int, ...]
    decoded_to_source_vertex_indices: tuple[int, ...]
    source_to_decoded_face_indices: tuple[int, ...]
    decoded_to_source_face_indices: tuple[int, ...]
    status: str = "DECODED_ONLY"


def decode_indexed_triangle_mesh(
    raw_bytes: bytes,
    *,
    media_type: str,
    expected_coordinate_frame_id: str,
    max_bytes: int,
    max_vertices: int,
    max_faces: int,
) -> DecodedIndexedTriangleMesh:
    """Decode validated mesh records without normalization or geometry claims."""
    if not isinstance(raw_bytes, bytes):
        raise MeshDecodeError("mesh.source_bytes_required")
    if media_type != MESH_MEDIA_TYPE:
        raise MeshDecodeError("mesh.unsupported_media_type")
    if not expected_coordinate_frame_id:
        raise MeshDecodeError("mesh.expected_frame_required")
    for name, budget in (
        ("max_bytes", max_bytes),
        ("max_vertices", max_vertices),
        ("max_faces", max_faces),
    ):
        if isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0:
            raise MeshDecodeError(f"mesh.{name}_invalid")
    if len(raw_bytes) > max_bytes:
        raise MeshDecodeError("mesh.byte_budget_exhausted")

    try:
        value = parse_json(raw_bytes)
    except CanonicalizationError as error:
        raise MeshDecodeError("mesh.invalid_ijson") from error
    report = validate_schema("indexed_triangle_mesh", value)
    if not report.ok:
        raise ArtifactValidationError(report)
    mesh = cast(dict[str, JSONValue], value)
    coordinate_system = cast(dict[str, JSONValue], mesh["coordinate_system"])
    frame_id = cast(str, coordinate_system["coordinate_frame_id"])
    if frame_id != expected_coordinate_frame_id:
        raise MeshDecodeError("mesh.frame_mismatch")

    vertices_data = cast(list[JSONValue], mesh["vertices"])
    faces_data = cast(list[JSONValue], mesh["faces"])
    if len(vertices_data) > max_vertices:
        raise MeshDecodeError("mesh.vertex_budget_exhausted")
    if len(faces_data) > max_faces:
        raise MeshDecodeError("mesh.face_budget_exhausted")

    vertices: list[tuple[float, float, float]] = []
    for vertex_value in vertices_data:
        vertex = cast(dict[str, JSONValue], vertex_value)
        position = cast(list[JSONValue], vertex["position_mm"])
        vertices.append(
            (
                float(cast(int | float, position[0])),
                float(cast(int | float, position[1])),
                float(cast(int | float, position[2])),
            )
        )

    faces: list[tuple[int, int, int]] = []
    vertex_count = len(vertices)
    for face_index, face_value in enumerate(faces_data):
        face = cast(dict[str, JSONValue], face_value)
        raw_indices = cast(list[JSONValue], face["vertex_indices"])
        indices: list[int] = []
        for index in raw_indices:
            if isinstance(index, bool) or not isinstance(index, (int, float)):
                raise MeshDecodeError(f"mesh.face_{face_index}.index_type")
            if isinstance(index, float) and not index.is_integer():
                raise MeshDecodeError(f"mesh.face_{face_index}.index_fractional")
            integer_index = int(index)
            if integer_index < 0 or integer_index >= vertex_count:
                raise MeshDecodeError(f"mesh.face_{face_index}.index_out_of_range")
            indices.append(integer_index)
        if len(set(indices)) != 3:
            raise MeshDecodeError(f"mesh.face_{face_index}.index_repeated")
        faces.append((indices[0], indices[1], indices[2]))

    vertex_map = tuple(range(len(vertices)))
    face_map = tuple(range(len(faces)))
    return DecodedIndexedTriangleMesh(
        representation_version=cast(str, mesh["representation_version"]),
        coordinate_frame_id=frame_id,
        vertices_mm=tuple(vertices),
        faces=tuple(faces),
        source_sha256=sha256(raw_bytes).hexdigest(),
        parser_name=PARSER_NAME,
        parser_version=PARSER_VERSION,
        media_type=media_type,
        source_to_decoded_vertex_indices=vertex_map,
        decoded_to_source_vertex_indices=vertex_map,
        source_to_decoded_face_indices=face_map,
        decoded_to_source_face_indices=face_map,
    )
