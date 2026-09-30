"""Exact indexed face-pair intersection diagnostics for target meshes.

This bounded diagnostic reports pair relations only. It does not implement V0
acceptance, near-contact classification, or mesh repair.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from itertools import combinations

from .canonical import jcs_bytes
from .exact_triangle_relation import (
    ExactTriangleRelationError,
    TriangleRelationKind,
    triangle_relation,
)
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

PAIR_RELATIONS_STATUS = "PAIR_RELATIONS_DIAGNOSTIC_ONLY"
PAIR_RELATIONS_VERSION = "1.0.0"
_HASH_DOMAIN = b"TARGET_MESH_PAIR_RELATIONS_DIAGNOSTIC_V1\0"


class MeshPairRelationsError(ValueError):
    """Source or diagnostic preconditions do not support a pair report."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class FacePairRelation:
    face_indices: tuple[int, int]
    relation_kind: str
    coplanar: bool
    witnesses: tuple[tuple[tuple[str, str], tuple[str, str], tuple[str, str]], ...]
    shared_indexed_vertex_count: int
    intended_simplex_allowance: str
    forbidden: bool


@dataclass(frozen=True, slots=True)
class PairRelationsDiagnostic:
    status: str
    algorithm_version: str
    source_sha256: str
    parser_name: str
    parser_version: str
    topology_diagnostic_sha256: str
    vertex_count: int
    face_count: int
    max_face_pairs_evaluated: int
    face_pairs_evaluated: int
    relations: tuple[FacePairRelation, ...]
    diagnostic_sha256: str


def _fraction_point(point: tuple[float, float, float]) -> tuple[Fraction, Fraction, Fraction]:
    return (
        Fraction.from_float(point[0]),
        Fraction.from_float(point[1]),
        Fraction.from_float(point[2]),
    )


def _zero_area(mesh: DecodedIndexedTriangleMesh, face: tuple[int, int, int]) -> bool:
    a, b, c = (_fraction_point(mesh.vertices_mm[index]) for index in face)
    ab = tuple(b[i] - a[i] for i in range(3))
    ac = tuple(c[i] - a[i] for i in range(3))
    cross = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    return all(value == 0 for value in cross)


def _witness(
    point: tuple[Fraction, Fraction, Fraction],
) -> tuple[tuple[str, str], tuple[str, str], tuple[str, str]]:
    return (
        (str(point[0].numerator), str(point[0].denominator)),
        (str(point[1].numerator), str(point[1].denominator)),
        (str(point[2].numerator), str(point[2].denominator)),
    )


def diagnose_indexed_triangle_mesh_pair_relations(
    raw_bytes: bytes,
    decoded: DecodedIndexedTriangleMesh,
    topology: TopologyDiagnostic,
    *,
    media_type: str,
    expected_coordinate_frame_id: str,
    max_bytes: int,
    max_vertices: int,
    max_faces: int,
    max_face_pairs_evaluated: int,
) -> PairRelationsDiagnostic:
    """Revalidate provenance and report every exact unordered face-pair relation."""
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
        raise MeshPairRelationsError("pair_relations.source_invalid") from error
    if source_decoded != decoded:
        raise MeshPairRelationsError("pair_relations.decoded_source_mismatch")

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
        raise MeshPairRelationsError("pair_relations.topology_unavailable") from error
    if current_topology != topology:
        raise MeshPairRelationsError("pair_relations.topology_mismatch")

    face_count = len(decoded.faces)
    if (isinstance(max_face_pairs_evaluated, bool)
            or not isinstance(max_face_pairs_evaluated, int)
            or max_face_pairs_evaluated <= 0):
        raise MeshPairRelationsError("pair_relations.pair_budget_invalid")
    required_pairs = face_count * (face_count - 1) // 2
    if max_face_pairs_evaluated < required_pairs:
        raise MeshPairRelationsError("pair_relations.pair_budget_exhausted")

    for face in decoded.faces:
        if _zero_area(decoded, face):
            raise MeshPairRelationsError("pair_relations.zero_area_face")

    relations: list[FacePairRelation] = []
    for first_index, second_index in combinations(range(face_count), 2):
        first_ids, second_ids = decoded.faces[first_index], decoded.faces[second_index]
        shared_ids = tuple(sorted(set(first_ids).intersection(second_ids)))
        first_points = tuple(_fraction_point(decoded.vertices_mm[index]) for index in first_ids)
        second_points = tuple(_fraction_point(decoded.vertices_mm[index]) for index in second_ids)
        first = (first_points[0], first_points[1], first_points[2])
        second = (second_points[0], second_points[1], second_points[2])
        try:
            relation = triangle_relation(first, second)
        except ExactTriangleRelationError as error:
            raise MeshPairRelationsError("pair_relations.exact_relation_failed") from error

        allowance = "NONE"
        forbidden = False
        if len(shared_ids) == 0:
            forbidden = relation.kind is not TriangleRelationKind.DISJOINT
        elif len(shared_ids) == 1:
            shared_point = _fraction_point(decoded.vertices_mm[shared_ids[0]])
            permitted = (
                relation.kind is TriangleRelationKind.POINT
                and relation.witnesses == (shared_point,)
            )
            allowance = "SHARED_VERTEX" if permitted else "NONE"
            forbidden = not permitted
        elif len(shared_ids) == 2:
            edge_points = tuple(sorted(
                _fraction_point(decoded.vertices_mm[index]) for index in shared_ids
            ))
            permitted = (
                relation.kind is TriangleRelationKind.SEGMENT
                and relation.witnesses == edge_points
            )
            allowance = "SHARED_EDGE" if permitted else "NONE"
            forbidden = not permitted
        else:
            raise MeshPairRelationsError("pair_relations.shared_simplex_malformed")

        relations.append(FacePairRelation(
            face_indices=(first_index, second_index),
            relation_kind=relation.kind.value,
            coplanar=relation.coplanar,
            witnesses=tuple(_witness(point) for point in relation.witnesses),
            shared_indexed_vertex_count=len(shared_ids),
            intended_simplex_allowance=allowance,
            forbidden=forbidden,
        ))

    report_payload: JSONValue = {
        "status": PAIR_RELATIONS_STATUS,
        "algorithm_version": PAIR_RELATIONS_VERSION,
        "source_sha256": decoded.source_sha256,
        "parser_name": decoded.parser_name,
        "parser_version": decoded.parser_version,
        "media_type": decoded.media_type,
        "topology_diagnostic_sha256": topology.diagnostic_sha256,
        "vertex_count": len(decoded.vertices_mm),
        "face_count": face_count,
        "max_face_pairs_evaluated": max_face_pairs_evaluated,
        "face_pairs_evaluated": required_pairs,
        "relations": [
            {
                "face_indices": list(item.face_indices),
                "relation_kind": item.relation_kind,
                "coplanar": item.coplanar,
                "witnesses": [
                    [[numerator, denominator] for numerator, denominator in point]
                    for point in item.witnesses
                ],
                "shared_indexed_vertex_count": item.shared_indexed_vertex_count,
                "intended_simplex_allowance": item.intended_simplex_allowance,
                "forbidden": item.forbidden,
            }
            for item in relations
        ],
    }
    digest = sha256(_HASH_DOMAIN + jcs_bytes(report_payload)).hexdigest()
    return PairRelationsDiagnostic(
        status=PAIR_RELATIONS_STATUS,
        algorithm_version=PAIR_RELATIONS_VERSION,
        source_sha256=decoded.source_sha256,
        parser_name=decoded.parser_name,
        parser_version=decoded.parser_version,
        topology_diagnostic_sha256=topology.diagnostic_sha256,
        vertex_count=len(decoded.vertices_mm),
        face_count=face_count,
        max_face_pairs_evaluated=max_face_pairs_evaluated,
        face_pairs_evaluated=required_pairs,
        relations=tuple(relations),
        diagnostic_sha256=digest,
    )
