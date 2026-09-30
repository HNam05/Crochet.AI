"""Experimental mesh-wide wrapper for exact adjacent-triangle residuals.

This diagnostic is deliberately separate from V0 admission and solver behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256

from .adjacent_triangle_residual import (
    EXPERIMENTAL_ZONE_VERSION,
    AdjacentTriangleResidualError,
    adjacent_triangle_residual_squared,
)
from .canonical import jcs_bytes
from .diagnostics import ArtifactValidationError
from .json_types import JSONValue
from .target_mesh_canonical_order import (
    ORDERING_VERSION,
    MeshCanonicalOrderError,
    diagnose_indexed_triangle_mesh_canonical_order,
)
from .target_mesh_decode import (
    MeshDecodeError,
    decode_indexed_triangle_mesh,
)
from .target_mesh_exact_geometry import (
    MeshGeometryError,
    diagnose_indexed_triangle_mesh_exact_geometry,
)
from .target_mesh_topology import (
    TOPOLOGY_VERSION,
    MeshTopologyError,
    diagnose_indexed_triangle_mesh,
)

ADJACENT_RESIDUAL_VERSION = "1.0.0"
ADJACENT_RESIDUAL_STATUS = "EXPERIMENTAL_MESH_ADJACENT_RESIDUAL_ONLY"
_HASH_DOMAIN = b"EXPERIMENTAL_MESH_ADJACENT_RESIDUAL_V1\0"


class MeshAdjacentResidualError(ValueError):
    """Invalid mesh, unsupported topology, or exhausted explicit work budget."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class MeshAdjacentResidualPair:
    ordered_face_indices: tuple[int, int]
    source_face_indices: tuple[int, int]
    shared_entity: str
    shared_source_vertex_indices: tuple[int, ...]
    squared_distance_numerator_mm2: str
    squared_distance_denominator_mm2: str
    evaluated_piece_pairs: int


@dataclass(frozen=True, slots=True)
class MeshAdjacentResidualDiagnostic:
    status: str
    algorithm_version: str
    kernel_version: str
    ordering_version: str
    topology_version: str
    source_sha256: str
    parser_name: str
    parser_version: str
    media_type: str
    coordinate_frame_id: str
    vertex_count: int
    face_count: int
    topology_diagnostic_sha256: str
    ordering_diagnostic_sha256: str
    source_to_ordered_vertex_indices: tuple[int, ...]
    ordered_to_source_vertex_indices: tuple[int, ...]
    source_to_ordered_face_indices: tuple[int, ...]
    ordered_to_source_face_indices: tuple[int, ...]
    lambda_numerator: str
    lambda_denominator: str
    max_lambda_bits: int
    max_bytes: int
    max_vertices: int
    max_faces: int
    max_face_pairs: int
    max_distance_piece_pairs: int
    required_face_pairs: int
    adjacent_face_pair_count: int
    nonadjacent_face_pairs_skipped: int
    predicted_distance_piece_pairs: int
    evaluated_distance_piece_pairs: int
    minimum_squared_distance_numerator_mm2: str | None
    minimum_squared_distance_denominator_mm2: str | None
    pairs: tuple[MeshAdjacentResidualPair, ...]
    diagnostic_sha256: str


def diagnose_indexed_triangle_mesh_adjacent_residual(
    raw_bytes: bytes,
    *,
    media_type: str,
    expected_coordinate_frame_id: str,
    lambda_value: Fraction,
    max_bytes: int,
    max_vertices: int,
    max_faces: int,
    max_face_pairs: int,
    max_distance_piece_pairs: int,
    max_lambda_bits: int,
) -> MeshAdjacentResidualDiagnostic:
    """Report exact residual distances for all adjacent source face pairs."""
    budgets = (
        ("max_bytes", max_bytes), ("max_vertices", max_vertices),
        ("max_faces", max_faces), ("max_face_pairs", max_face_pairs),
        ("max_distance_piece_pairs", max_distance_piece_pairs),
        ("max_lambda_bits", max_lambda_bits),
    )
    for name, value in budgets:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise MeshAdjacentResidualError(f"adjacent_residual.{name}_invalid")
    if not isinstance(lambda_value, Fraction) or not 0 < lambda_value < 1:
        raise MeshAdjacentResidualError("adjacent_residual.lambda_invalid")
    lambda_bits = max(lambda_value.numerator.bit_length(), lambda_value.denominator.bit_length())
    if lambda_bits > max_lambda_bits:
        raise MeshAdjacentResidualError("adjacent_residual.lambda_bit_budget_exhausted")

    try:
        decoded = decode_indexed_triangle_mesh(
            raw_bytes, media_type=media_type,
            expected_coordinate_frame_id=expected_coordinate_frame_id,
            max_bytes=max_bytes, max_vertices=max_vertices, max_faces=max_faces,
        )
        topology = diagnose_indexed_triangle_mesh(
            raw_bytes, decoded, media_type=media_type,
            expected_coordinate_frame_id=expected_coordinate_frame_id,
            max_bytes=max_bytes, max_vertices=max_vertices, max_faces=max_faces,
        )
        if topology.issues or topology.orientable is not True:
            codes = ",".join(sorted({issue.code for issue in topology.issues}))
            raise MeshAdjacentResidualError(
                f"adjacent_residual.topology_invalid:{codes or 'not_orientable'}"
            )
        geometry = diagnose_indexed_triangle_mesh_exact_geometry(
            raw_bytes, decoded, media_type=media_type,
            expected_coordinate_frame_id=expected_coordinate_frame_id,
            max_bytes=max_bytes, max_vertices=max_vertices, max_faces=max_faces,
        )
        if geometry.zero_area_faces:
            indices = ",".join(str(item.face_index) for item in geometry.zero_area_faces)
            raise MeshAdjacentResidualError(f"adjacent_residual.degenerate_faces:{indices}")
        if geometry.coincident_vertex_groups:
            raise MeshAdjacentResidualError("adjacent_residual.coincident_vertices")
        ordering = diagnose_indexed_triangle_mesh_canonical_order(
            raw_bytes, decoded, media_type=media_type,
            expected_coordinate_frame_id=expected_coordinate_frame_id,
            max_bytes=max_bytes, max_vertices=max_vertices, max_faces=max_faces,
        )
    except MeshAdjacentResidualError:
        raise
    except (
        ArtifactValidationError,
        MeshCanonicalOrderError,
        MeshDecodeError,
        MeshGeometryError,
        MeshTopologyError,
    ) as error:
        raise MeshAdjacentResidualError("adjacent_residual.source_or_topology_invalid") from error

    faces = ordering.derived_faces
    source_faces = ordering.derived_to_source_face_indices
    required_pairs = len(faces) * (len(faces) - 1) // 2
    if required_pairs > max_face_pairs:
        raise MeshAdjacentResidualError("adjacent_residual.face_pair_budget_exhausted")

    candidates: list[tuple[int, int, tuple[int, ...], tuple[tuple[int, int], ...], int]] = []
    for first_index in range(len(faces)):
        for second_index in range(first_index + 1, len(faces)):
            first_indices, second_indices = faces[first_index], faces[second_index]
            shared = tuple(sorted(set(first_indices).intersection(second_indices)))
            if not shared:
                continue
            local_pairs = tuple(
                (first_indices.index(vertex), second_indices.index(vertex)) for vertex in shared
            )
            predicted = 2 if len(shared) == 2 else 4 if len(shared) == 1 else 0
            if len(shared) not in (1, 2):
                raise MeshAdjacentResidualError(
                    f"adjacent_residual.invalid_shared_vertex_count:{first_index}:{second_index}"
                )
            candidates.append((first_index, second_index, shared, local_pairs, predicted))
    predicted_total = sum(item[4] for item in candidates)
    if predicted_total > max_distance_piece_pairs:
        raise MeshAdjacentResidualError("adjacent_residual.distance_piece_pair_budget_exhausted")

    points = ordering.derived_vertices_mm
    output: list[MeshAdjacentResidualPair] = []
    minima: list[Fraction] = []
    evaluated_total = 0
    for first_index, second_index, shared, local_pairs, _ in candidates:
        first_face = faces[first_index]
        second_face = faces[second_index]
        first_triangle: tuple[
            tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]
        ] = (
            points[first_face[0]], points[first_face[1]], points[first_face[2]],
        )
        second_triangle: tuple[
            tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]
        ] = (
            points[second_face[0]], points[second_face[1]], points[second_face[2]],
        )
        try:
            result = adjacent_triangle_residual_squared(
                first_triangle, second_triangle,
                shared_identity_indices=local_pairs,
                lambda_value=lambda_value,
                max_piece_pairs=max_distance_piece_pairs,
            )
        except AdjacentTriangleResidualError as error:
            raise MeshAdjacentResidualError(
                f"adjacent_residual.pair_{first_index}_{second_index}:{error}"
            ) from error
        distance = result.distance_squared
        minima.append(distance)
        evaluated_total += result.diagnostic.evaluated_piece_pairs
        source_pair = (min(source_faces[first_index], source_faces[second_index]),
                       max(source_faces[first_index], source_faces[second_index]))
        output.append(MeshAdjacentResidualPair(
            (first_index, second_index), source_pair,
            result.diagnostic.shared_entity,
            tuple(sorted(ordering.derived_to_source_vertex_indices[index] for index in shared)),
            str(distance.numerator), str(distance.denominator),
            result.diagnostic.evaluated_piece_pairs,
        ))

    minimum = min(minima) if minima else None
    payload: JSONValue = {
        "status": ADJACENT_RESIDUAL_STATUS,
        "algorithm_version": ADJACENT_RESIDUAL_VERSION,
        "kernel_version": EXPERIMENTAL_ZONE_VERSION,
        "ordering_version": ORDERING_VERSION,
        "topology_version": TOPOLOGY_VERSION,
        "source_sha256": decoded.source_sha256,
        "parser_name": decoded.parser_name,
        "parser_version": decoded.parser_version,
        "media_type": decoded.media_type,
        "coordinate_frame_id": decoded.coordinate_frame_id,
        "vertex_count": len(decoded.vertices_mm), "face_count": len(faces),
        "topology_diagnostic_sha256": topology.diagnostic_sha256,
        "ordering_diagnostic_sha256": ordering.diagnostic_sha256,
        "source_to_ordered_vertex_indices": list(ordering.source_to_derived_vertex_indices),
        "ordered_to_source_vertex_indices": list(ordering.derived_to_source_vertex_indices),
        "source_to_ordered_face_indices": list(ordering.source_to_derived_face_indices),
        "ordered_to_source_face_indices": list(source_faces),
        "lambda": {
            "numerator": str(lambda_value.numerator),
            "denominator": str(lambda_value.denominator),
        },
        "max_lambda_bits": max_lambda_bits,
        "budgets": {name: value for name, value in budgets},
        "required_face_pairs": required_pairs,
        "adjacent_face_pair_count": len(output),
        "nonadjacent_face_pairs_skipped": required_pairs - len(output),
        "predicted_distance_piece_pairs": predicted_total,
        "evaluated_distance_piece_pairs": evaluated_total,
        "minimum_squared_distance_mm2": None if minimum is None else {
            "numerator": str(minimum.numerator), "denominator": str(minimum.denominator),
        },
        "pairs": [{
            "ordered_face_indices": list(item.ordered_face_indices),
            "source_face_indices": list(item.source_face_indices),
            "shared_entity": item.shared_entity,
            "shared_source_vertex_indices": list(item.shared_source_vertex_indices),
            "distance_squared_mm2": {
                "numerator": item.squared_distance_numerator_mm2,
                "denominator": item.squared_distance_denominator_mm2,
            },
            "evaluated_piece_pairs": item.evaluated_piece_pairs,
        } for item in output],
    }
    digest = sha256(_HASH_DOMAIN + jcs_bytes(payload)).hexdigest()
    return MeshAdjacentResidualDiagnostic(
        ADJACENT_RESIDUAL_STATUS, ADJACENT_RESIDUAL_VERSION,
        EXPERIMENTAL_ZONE_VERSION, ORDERING_VERSION, TOPOLOGY_VERSION,
        decoded.source_sha256, decoded.parser_name, decoded.parser_version,
        decoded.media_type, decoded.coordinate_frame_id, len(decoded.vertices_mm),
        len(faces), topology.diagnostic_sha256,
        ordering.diagnostic_sha256,
        ordering.source_to_derived_vertex_indices, ordering.derived_to_source_vertex_indices,
        ordering.source_to_derived_face_indices, source_faces,
        str(lambda_value.numerator), str(lambda_value.denominator), max_lambda_bits,
        max_bytes, max_vertices, max_faces, max_face_pairs,
        max_distance_piece_pairs, required_pairs, len(output),
        required_pairs - len(output), predicted_total, evaluated_total,
        None if minimum is None else str(minimum.numerator),
        None if minimum is None else str(minimum.denominator), tuple(output), digest,
    )
