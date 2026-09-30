"""Exact vertex-diameter diagnostic for decoded indexed triangle meshes."""

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

DIAMETER_STATUS = "DIAMETER_DIAGNOSTIC_ONLY"
DIAMETER_VERSION = "1.0.0"
_HASH_DOMAIN = b"TARGET_MESH_VERTEX_DIAMETER_DIAGNOSTIC_V1\0"


class MeshDiameterError(ValueError):
    """The source or requested work budget cannot support the diagnostic."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class VertexDiameterDiagnostic:
    status: str
    algorithm_version: str
    source_sha256: str
    parser_name: str
    parser_version: str
    media_type: str
    vertex_count: int
    required_vertex_pairs: int
    vertex_pairs_evaluated: int
    squared_diameter_numerator_mm2: str
    squared_diameter_denominator_mm2: str
    maximizing_vertex_pairs: tuple[tuple[int, int], ...]
    diagnostic_sha256: str


def _squared_distance(
    first: tuple[Fraction, Fraction, Fraction],
    second: tuple[Fraction, Fraction, Fraction],
) -> Fraction:
    return sum(
        ((first[axis] - second[axis]) ** 2 for axis in range(3)),
        Fraction(0),
    )


def diagnose_indexed_triangle_mesh_diameter(
    raw_bytes: bytes,
    decoded: DecodedIndexedTriangleMesh,
    *,
    media_type: str,
    expected_coordinate_frame_id: str,
    max_bytes: int,
    max_vertices: int,
    max_faces: int,
    max_vertex_pairs_evaluated: int,
) -> VertexDiameterDiagnostic:
    """Compute exact binary64-rational squared diameter over vertex identities."""
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
        raise MeshDiameterError("diameter.source_invalid") from error
    if source_decoded != decoded:
        raise MeshDiameterError("diameter.decoded_source_mismatch")
    if (
        isinstance(max_vertex_pairs_evaluated, bool)
        or not isinstance(max_vertex_pairs_evaluated, int)
        or max_vertex_pairs_evaluated <= 0
    ):
        raise MeshDiameterError("diameter.max_vertex_pairs_evaluated_invalid")

    vertex_count = len(decoded.vertices_mm)
    required_pairs = vertex_count * (vertex_count - 1) // 2
    if required_pairs > max_vertex_pairs_evaluated:
        raise MeshDiameterError("diameter.vertex_pair_budget_exhausted")

    positions: tuple[tuple[Fraction, Fraction, Fraction], ...] = tuple(
        (
            Fraction.from_float(position[0]),
            Fraction.from_float(position[1]),
            Fraction.from_float(position[2]),
        )
        for position in decoded.vertices_mm
    )
    maximum = Fraction(0)
    maximizing_pairs: list[tuple[int, int]] = []
    evaluated = 0
    for left in range(vertex_count):
        for right in range(left + 1, vertex_count):
            distance_squared = _squared_distance(positions[left], positions[right])
            evaluated += 1
            pair = (left, right)
            if distance_squared > maximum:
                maximum = distance_squared
                maximizing_pairs = [pair]
            elif distance_squared == maximum:
                maximizing_pairs.append(pair)

    pairs_tuple = tuple(maximizing_pairs)
    payload: JSONValue = {
        "algorithm_version": DIAMETER_VERSION,
        "status": DIAMETER_STATUS,
        "source_sha256": decoded.source_sha256,
        "parser_name": decoded.parser_name,
        "parser_version": decoded.parser_version,
        "media_type": decoded.media_type,
        "vertex_count": vertex_count,
        "required_vertex_pairs": required_pairs,
        "vertex_pairs_evaluated": evaluated,
        "squared_diameter_mm2": {
            "numerator": str(maximum.numerator),
            "denominator": str(maximum.denominator),
        },
        "maximizing_vertex_pairs": [list(pair) for pair in pairs_tuple],
    }
    digest = sha256(_HASH_DOMAIN + jcs_bytes(payload)).hexdigest()
    return VertexDiameterDiagnostic(
        status=DIAMETER_STATUS,
        algorithm_version=DIAMETER_VERSION,
        source_sha256=decoded.source_sha256,
        parser_name=decoded.parser_name,
        parser_version=decoded.parser_version,
        media_type=decoded.media_type,
        vertex_count=vertex_count,
        required_vertex_pairs=required_pairs,
        vertex_pairs_evaluated=evaluated,
        squared_diameter_numerator_mm2=str(maximum.numerator),
        squared_diameter_denominator_mm2=str(maximum.denominator),
        maximizing_vertex_pairs=pairs_tuple,
        diagnostic_sha256=digest,
    )
