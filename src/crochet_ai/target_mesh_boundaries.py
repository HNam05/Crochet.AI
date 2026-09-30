"""Directed boundary and component ordering evidence for V0 meshes.

This diagnostic records induced boundary directions and canonical data ordering.
It does not normalize the mesh or establish V0 acceptance.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256

from .canonical import jcs_bytes
from .json_types import JSONValue
from .target_mesh_canonical_order import (
    CanonicalOrderDiagnostic,
    MeshCanonicalOrderError,
    diagnose_indexed_triangle_mesh_canonical_order,
)
from .target_mesh_decode import (
    DecodedIndexedTriangleMesh,
    MeshDecodeError,
    decode_indexed_triangle_mesh,
)
from .target_mesh_topology import MeshTopologyError, diagnose_indexed_triangle_mesh

BOUNDARY_STATUS = "DIRECTED_BOUNDARIES_DIAGNOSTIC_ONLY"
BOUNDARY_VERSION = "1.0.0"
_DOMAIN = b"TARGET_MESH_DIRECTED_BOUNDARIES_DIAGNOSTIC_V1\0"


class MeshBoundaryError(ValueError):
    """The source or its topology cannot support directed loop evidence."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class BoundaryComponent:
    ordered_vertex_key: tuple[int, ...]
    ordered_face_key: tuple[tuple[int, int, int], ...]
    source_vertex_indices: tuple[int, ...]
    source_face_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class DirectedBoundaryDiagnostic:
    status: str
    algorithm_version: str
    source_sha256: str
    ordering_diagnostic_sha256: str
    source_to_ordered_vertex_indices: tuple[int, ...]
    ordered_to_source_vertex_indices: tuple[int, ...]
    source_to_ordered_face_indices: tuple[int, ...]
    ordered_to_source_face_indices: tuple[int, ...]
    components: tuple[BoundaryComponent, ...]
    boundary_loops: tuple[tuple[int, ...], ...]
    diagnostic_sha256: str


def diagnose_indexed_triangle_mesh_boundaries(
    raw_bytes: bytes,
    decoded: DecodedIndexedTriangleMesh,
    ordering: CanonicalOrderDiagnostic,
    *,
    media_type: str,
    expected_coordinate_frame_id: str,
    max_bytes: int,
    max_vertices: int,
    max_faces: int,
) -> DirectedBoundaryDiagnostic:
    """Revalidate inputs and order directed source-face boundary cycles."""
    try:
        fresh_decoded = decode_indexed_triangle_mesh(
            raw_bytes,
            media_type=media_type,
            expected_coordinate_frame_id=expected_coordinate_frame_id,
            max_bytes=max_bytes,
            max_vertices=max_vertices,
            max_faces=max_faces,
        )
    except (MeshDecodeError, ValueError) as error:
        raise MeshBoundaryError("boundary.source_invalid") from error
    if fresh_decoded != decoded:
        raise MeshBoundaryError("boundary.decoded_source_mismatch")
    try:
        fresh_ordering = diagnose_indexed_triangle_mesh_canonical_order(
            raw_bytes,
            fresh_decoded,
            media_type=media_type,
            expected_coordinate_frame_id=expected_coordinate_frame_id,
            max_bytes=max_bytes,
            max_vertices=max_vertices,
            max_faces=max_faces,
        )
    except MeshCanonicalOrderError as error:
        raise MeshBoundaryError("boundary.ordering_invalid") from error
    if fresh_ordering != ordering:
        raise MeshBoundaryError("boundary.ordering_mismatch")
    if ordering.identity_unavailable_reason != "v0_geometry_and_normalization_unverified":
        raise MeshBoundaryError("boundary.ordering_preconditions_failed")
    try:
        topology = diagnose_indexed_triangle_mesh(
            raw_bytes,
            fresh_decoded,
            media_type=media_type,
            expected_coordinate_frame_id=expected_coordinate_frame_id,
            max_bytes=max_bytes,
            max_vertices=max_vertices,
            max_faces=max_faces,
        )
    except MeshTopologyError as error:
        raise MeshBoundaryError("boundary.topology_invalid") from error
    if topology.issues or topology.orientable is not True:
        raise MeshBoundaryError("boundary.topology_preconditions_failed")

    v_to_ordered = ordering.source_to_derived_vertex_indices
    f_to_ordered = ordering.source_to_derived_face_indices
    edge_uses: dict[tuple[int, int], list[tuple[int, int, int]]] = defaultdict(list)
    for face_index, face in enumerate(fresh_decoded.faces):
        for start, end in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge_uses[(min(start, end), max(start, end))].append((face_index, start, end))
    directed: list[tuple[int, int]] = []
    for uses in edge_uses.values():
        if len(uses) == 1:
            _, start, end = uses[0]
            directed.append((v_to_ordered[start], v_to_ordered[end]))

    outgoing: dict[int, list[int]] = defaultdict(list)
    incoming: dict[int, list[int]] = defaultdict(list)
    for start, end in directed:
        outgoing[start].append(end)
        incoming[end].append(start)
    boundary_vertices = set(outgoing) | set(incoming)
    if any(len(outgoing[v]) != 1 or len(incoming[v]) != 1 for v in boundary_vertices):
        raise MeshBoundaryError("boundary.non_cycle_boundary_graph")
    remaining = set(directed)
    loops: list[tuple[int, ...]] = []
    for seed in sorted(remaining):
        if seed not in remaining:
            continue
        start = seed[0]
        current = start
        loop: list[int] = []
        visited: set[int] = set()
        while True:
            if current in visited:
                if current != start:
                    raise MeshBoundaryError("boundary.repeated_vertex")
                break
            loop.append(current)
            visited.add(current)
            following = outgoing[current][0]
            edge = (current, following)
            if edge not in remaining:
                raise MeshBoundaryError("boundary.edge_reuse")
            remaining.remove(edge)
            current = following
            if current == start:
                break
        least_position = loop.index(min(loop))
        loops.append(tuple(loop[least_position:] + loop[:least_position]))
    loops.sort()

    ordered_faces = ordering.derived_faces
    source_to_ordered_face = f_to_ordered
    source_components: list[tuple[int, ...]] = []
    for source_component in topology.component_face_indices:
        source_components.append(
            tuple(sorted(source_component, key=source_to_ordered_face.__getitem__))
        )
    components: list[BoundaryComponent] = []
    for source_faces in source_components:
        face_key = tuple(
            sorted(ordered_faces[f_to_ordered[source_face]] for source_face in source_faces)
        )
        source_component_vertices = {
            vertex
            for face_index in source_faces
            for vertex in fresh_decoded.faces[face_index]
        }
        vertex_key = tuple(sorted(v_to_ordered[v] for v in source_component_vertices))
        source_vertices = tuple(
            ordering.derived_to_source_vertex_indices[index] for index in vertex_key
        )
        components.append(
            BoundaryComponent(vertex_key, face_key, source_vertices, tuple(source_faces))
        )
    components.sort(
        key=lambda component: (component.ordered_vertex_key, component.ordered_face_key)
    )

    payload: JSONValue = {
        "algorithm_version": BOUNDARY_VERSION,
        "status": BOUNDARY_STATUS,
        "source_sha256": fresh_decoded.source_sha256,
        "ordering_diagnostic_sha256": ordering.diagnostic_sha256,
        "source_to_ordered_vertex_indices": list(v_to_ordered),
        "ordered_to_source_vertex_indices": list(ordering.derived_to_source_vertex_indices),
        "source_to_ordered_face_indices": list(f_to_ordered),
        "ordered_to_source_face_indices": list(ordering.derived_to_source_face_indices),
        "components": [{
            "ordered_vertex_key": list(component.ordered_vertex_key),
            "ordered_face_key": [list(face) for face in component.ordered_face_key],
            "source_vertex_indices": list(component.source_vertex_indices),
            "source_face_indices": list(component.source_face_indices),
        } for component in components],
        "boundary_loops": [list(loop) for loop in loops],
    }
    digest = sha256(_DOMAIN + jcs_bytes(payload)).hexdigest()
    return DirectedBoundaryDiagnostic(
        BOUNDARY_STATUS, BOUNDARY_VERSION, fresh_decoded.source_sha256,
        ordering.diagnostic_sha256, v_to_ordered,
        ordering.derived_to_source_vertex_indices, f_to_ordered,
        ordering.derived_to_source_face_indices, tuple(components), tuple(loops), digest,
    )
