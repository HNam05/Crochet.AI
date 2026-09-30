"""Exact combinatorial diagnostics for decoded indexed triangle meshes."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from hashlib import sha256

from .canonical import jcs_bytes
from .json_types import JSONValue
from .target_mesh_decode import (
    DecodedIndexedTriangleMesh,
    MeshDecodeError,
    decode_indexed_triangle_mesh,
)

TOPOLOGY_STATUS = "EXACT_TOPOLOGY_DIAGNOSTIC_ONLY"
TOPOLOGY_VERSION = "1.0.0"


class MeshTopologyError(ValueError):
    """The source cannot support a topology diagnostic for the supplied decode."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class TopologyIssue:
    code: str
    vertices: tuple[int, ...] = ()
    faces: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class TopologyDiagnostic:
    status: str
    source_sha256: str
    parser_name: str
    parser_version: str
    diagnostic_sha256: str
    vertex_count: int
    face_count: int
    edge_count: int
    boundary_edge_count: int
    nonmanifold_edge_count: int
    component_face_indices: tuple[tuple[int, ...], ...]
    boundary_loops: tuple[tuple[int, ...], ...]
    issues: tuple[TopologyIssue, ...]
    orientable: bool | None

    @property
    def issue_count(self) -> int:
        return len(self.issues)


def diagnose_indexed_triangle_mesh(
    raw_bytes: bytes,
    decoded: DecodedIndexedTriangleMesh,
    *,
    media_type: str,
    expected_coordinate_frame_id: str,
    max_bytes: int,
    max_vertices: int,
    max_faces: int,
) -> TopologyDiagnostic:
    """Revalidate source provenance, then report exact incidence properties only."""
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
        raise MeshTopologyError("topology.source_invalid") from error
    if source_decoded != decoded:
        raise MeshTopologyError("topology.decoded_source_mismatch")

    faces = decoded.faces
    vertex_count = len(decoded.vertices_mm)
    edge_faces: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    vertex_faces: list[list[int]] = [[] for _ in range(vertex_count)]
    used_vertices: set[int] = set()
    issues: list[TopologyIssue] = []
    duplicate_groups: dict[
        tuple[int, int, int], list[tuple[int, tuple[int, int, int]]]
    ] = defaultdict(list)

    for face_index, face in enumerate(faces):
        used_vertices.update(face)
        for vertex in face:
            vertex_faces[vertex].append(face_index)
        ordered_face = tuple(sorted(face))
        duplicate_key = (ordered_face[0], ordered_face[1], ordered_face[2])
        duplicate_groups[duplicate_key].append((face_index, face))
        for start, end in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge = (min(start, end), max(start, end))
            direction = 1 if (start, end) == edge else -1
            edge_faces[edge].append((face_index, direction))

    for vertex in range(vertex_count):
        if vertex not in used_vertices:
            issues.append(TopologyIssue("UNREFERENCED_VERTEX", (vertex,)))

    face_neighbors: list[set[int]] = [set() for _ in faces]
    parity_neighbors: list[list[tuple[int, int]]] = [[] for _ in faces]
    boundary_edges: list[tuple[int, int]] = []
    nonmanifold_count = 0
    for edge in sorted(edge_faces):
        incidents = sorted(edge_faces[edge])
        if len(incidents) == 1:
            boundary_edges.append(edge)
        elif len(incidents) == 2:
            (left, left_direction), (right, right_direction) = incidents
            face_neighbors[left].add(right)
            face_neighbors[right].add(left)
            parity = int(left_direction == right_direction)
            parity_neighbors[left].append((right, parity))
            parity_neighbors[right].append((left, parity))
            if parity:
                issues.append(TopologyIssue("WINDING_MISMATCH", edge, (left, right)))
        else:
            nonmanifold_count += 1
            issues.append(
                TopologyIssue("NONMANIFOLD_EDGE", edge, tuple(item[0] for item in incidents))
            )
            first_face = incidents[0][0]
            for incident_face, _ in incidents[1:]:
                face_neighbors[first_face].add(incident_face)
                face_neighbors[incident_face].add(first_face)

    for key in sorted(duplicate_groups):
        group = duplicate_groups[key]
        if len(group) > 1:
            ordered = sorted(group)
            issues.append(TopologyIssue("DUPLICATE_FACE", key, tuple(item[0] for item in ordered)))
            canonical_face_index, canonical_face = ordered[0]
            for duplicate_index, duplicate_face in ordered[1:]:
                same_winding = duplicate_face in (
                    canonical_face,
                    (canonical_face[1], canonical_face[2], canonical_face[0]),
                    (canonical_face[2], canonical_face[0], canonical_face[1]),
                )
                issues.append(
                    TopologyIssue(
                        "DUPLICATE_FACE_SAME_WINDING"
                        if same_winding
                        else "DUPLICATE_FACE_REVERSED_WINDING",
                        key,
                        (canonical_face_index, duplicate_index),
                    )
                )

    components: list[tuple[int, ...]] = []
    seen_faces: set[int] = set()
    for start in range(len(faces)):
        if start in seen_faces:
            continue
        pending = [start]
        seen_faces.add(start)
        component: list[int] = []
        while pending:
            current = pending.pop()
            component.append(current)
            for neighbor in sorted(face_neighbors[current], reverse=True):
                if neighbor not in seen_faces:
                    seen_faces.add(neighbor)
                    pending.append(neighbor)
        components.append(tuple(sorted(component)))
    components.sort(key=lambda component: component[0])
    for face_index, neighbors in enumerate(face_neighbors):
        if not neighbors:
            issues.append(TopologyIssue("ISOLATED_FACE", (), (face_index,)))

    orientable: bool | None = True
    assigned: dict[int, int] = {}
    if nonmanifold_count:
        orientable = None
    else:
        for start in range(len(faces)):
            if start in assigned:
                continue
            assigned[start] = 0
            pending_faces = deque([start])
            while pending_faces:
                current = pending_faces.popleft()
                for neighbor, parity in sorted(parity_neighbors[current]):
                    expected = assigned[current] ^ parity
                    if neighbor in assigned:
                        if assigned[neighbor] != expected:
                            orientable = False
                    else:
                        assigned[neighbor] = expected
                        pending_faces.append(neighbor)

    boundary_adjacency: dict[int, list[int]] = defaultdict(list)
    for left, right in boundary_edges:
        boundary_adjacency[left].append(right)
        boundary_adjacency[right].append(left)
    for vertex in sorted(boundary_adjacency):
        degree = len(boundary_adjacency[vertex])
        if degree != 2:
            issues.append(TopologyIssue("BOUNDARY_DEGREE", (vertex,), (),))
    loops: list[tuple[int, ...]] = []
    if boundary_edges and all(len(neighbors) == 2 for neighbors in boundary_adjacency.values()):
        remaining = {tuple(sorted(edge)) for edge in boundary_edges}
        while remaining:
            first_edge = min(remaining)
            start, current = first_edge
            loop = [start, current]
            remaining.remove(first_edge)
            previous = start
            while current != start:
                candidates = sorted(
                    neighbor
                    for neighbor in boundary_adjacency[current]
                    if neighbor != previous
                )
                following = candidates[0]
                low, high = sorted((current, following))
                edge = (low, high)
                if following != start:
                    loop.append(following)
                remaining.remove(edge)
                previous, current = current, following
            loops.append(tuple(loop))
        loops.sort()

    for vertex, incident_faces in enumerate(vertex_faces):
        if not incident_faces:
            continue
        link: dict[int, set[int]] = defaultdict(set)
        for face_index in incident_faces:
            face = faces[face_index]
            others = [item for item in face if item != vertex]
            link[others[0]].add(others[1])
            link[others[1]].add(others[0])
        link_seen: set[int] = set()
        link_components = 0
        for link_start in sorted(link):
            if link_start in link_seen:
                continue
            link_components += 1
            stack = [link_start]
            link_seen.add(link_start)
            while stack:
                for adjacent in link[stack.pop()]:
                    if adjacent not in link_seen:
                        link_seen.add(adjacent)
                        stack.append(adjacent)
        degrees = sorted(len(neighbors) for neighbors in link.values())
        boundary_degree = len(boundary_adjacency.get(vertex, ()))
        valid_cycle = boundary_degree == 0 and bool(degrees) and all(
            degree == 2 for degree in degrees
        )
        valid_path = (
            boundary_degree == 2
            and degrees.count(1) == 2
            and all(degree in (1, 2) for degree in degrees)
        )
        if link_components != 1 or not (valid_cycle or valid_path):
            issues.append(
                TopologyIssue(
                    "NONMANIFOLD_VERTEX_LINK", (vertex,), tuple(sorted(incident_faces))
                )
            )

    report_payload: JSONValue = {
        "algorithm_version": TOPOLOGY_VERSION,
        "status": TOPOLOGY_STATUS,
        "source_sha256": decoded.source_sha256,
        "parser_name": decoded.parser_name,
        "parser_version": decoded.parser_version,
        "vertex_count": vertex_count,
        "face_count": len(faces),
        "edge_count": len(edge_faces),
        "boundary_edge_count": len(boundary_edges),
        "nonmanifold_edge_count": nonmanifold_count,
        "component_face_indices": [list(component) for component in components],
        "boundary_loops": [list(loop) for loop in loops],
        "issues": [
            {
                "code": issue.code,
                "vertices": list(issue.vertices),
                "faces": list(issue.faces),
            }
            for issue in issues
        ],
        "orientable": orientable,
    }
    encoded_payload = jcs_bytes(report_payload)
    report_hash = sha256(b"EXACT_TOPOLOGY_DIAGNOSTIC_V1\0" + encoded_payload).hexdigest()
    return TopologyDiagnostic(
        status=TOPOLOGY_STATUS,
        source_sha256=decoded.source_sha256,
        parser_name=decoded.parser_name,
        parser_version=decoded.parser_version,
        diagnostic_sha256=report_hash,
        vertex_count=vertex_count,
        face_count=len(faces),
        edge_count=len(edge_faces),
        boundary_edge_count=len(boundary_edges),
        nonmanifold_edge_count=nonmanifold_count,
        component_face_indices=tuple(components),
        boundary_loops=tuple(loops),
        issues=tuple(issues),
        orientable=orientable,
    )
