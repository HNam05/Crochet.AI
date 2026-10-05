"""Independent bounded combinatorial audit for oriented triangular surfaces."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from hashlib import sha256 as _sha256
from typing import TypeAlias, cast

from .canonical import jcs_bytes
from .json_types import JSONValue

SURFACE_TOPOLOGY_AUDIT_V1 = "SURFACE_TOPOLOGY_AUDIT_V1"
MAX_VERTICES = 30_000
MAX_FACES = 60_000

_Face: TypeAlias = tuple[str, str, str]
_Edge: TypeAlias = tuple[str, str]


class SurfaceTopologyInputError(ValueError):
    """Malformed or over-budget input to the surface topology auditor."""


@dataclass(frozen=True, slots=True)
class SurfaceTopologyAudit:
    """Canonical result of a purely combinatorial closed-surface audit."""

    status: str
    input_sha256: str
    vertex_count: int
    edge_count: int
    face_count: int
    components: int
    euler_characteristic: int
    diagnostics: tuple[str, ...]
    betti_numbers: tuple[int, int, int] | None
    max_vertices: int
    max_faces: int

    def to_dict(self) -> dict[str, JSONValue]:
        """Return the profile's JSON-compatible canonical evidence payload."""
        return cast(
            dict[str, JSONValue],
            {
                "profile": SURFACE_TOPOLOGY_AUDIT_V1,
                "status": self.status,
                "input_sha256": self.input_sha256,
                "counts": {
                    "vertices": self.vertex_count,
                    "edges": self.edge_count,
                    "faces": self.face_count,
                    "components": self.components,
                    "euler_characteristic": self.euler_characteristic,
                },
                "diagnostics": list(self.diagnostics),
                "rational_homology_betti": (
                    None
                    if self.betti_numbers is None
                    else {
                        "b0": self.betti_numbers[0],
                        "b1": self.betti_numbers[1],
                        "b2": self.betti_numbers[2],
                    }
                ),
                "budgets": {
                    "max_vertices": self.max_vertices,
                    "max_faces": self.max_faces,
                },
            },
        )

    @property
    def canonical_bytes(self) -> bytes:
        """JCS bytes for this deterministic audit record."""
        return jcs_bytes(self.to_dict())

    @property
    def sha256(self) -> str:
        """Domain-separated digest of the canonical audit record."""
        payload = (
            b"Crochet.AI\x00"
            + SURFACE_TOPOLOGY_AUDIT_V1.encode("ascii")
            + b"\x00"
            + self.canonical_bytes
        )
        return _sha256(payload).hexdigest()


def audit_surface_topology(
    vertices: object,
    faces: object,
    *,
    max_vertices: int = MAX_VERTICES,
    max_faces: int = MAX_FACES,
) -> SurfaceTopologyAudit:
    """Audit a closed oriented triangular complex without geometric inference.

    Input bounds are checked before scanning either caller-provided list. Invalid
    inputs raise; admitted but defective complexes produce a complete FAIL record.
    """
    _validate_budget(max_vertices, MAX_VERTICES, "max_vertices")
    _validate_budget(max_faces, MAX_FACES, "max_faces")
    if not isinstance(vertices, list) or not vertices:
        raise SurfaceTopologyInputError("vertices.must_be_nonempty_list")
    if len(vertices) > max_vertices:
        raise SurfaceTopologyInputError("vertices.budget_exceeded")
    if not isinstance(faces, list) or not faces:
        raise SurfaceTopologyInputError("faces.must_be_nonempty_list")
    if len(faces) > max_faces:
        raise SurfaceTopologyInputError("faces.budget_exceeded")

    vertex_ids: list[str] = []
    seen_ids: set[str] = set()
    for identifier in vertices:
        if (
            not isinstance(identifier, str)
            or not identifier
            or len(identifier) > 128
            or not identifier.isascii()
        ):
            raise SurfaceTopologyInputError(
                "vertices.ids_must_be_nonempty_ascii_strings_at_most_128_chars"
            )
        if identifier in seen_ids:
            raise SurfaceTopologyInputError("vertices.ids_must_be_unique")
        seen_ids.add(identifier)
        vertex_ids.append(identifier)

    face_ids: list[_Face] = []
    for face in faces:
        if not isinstance(face, list) or len(face) != 3:
            raise SurfaceTopologyInputError("faces.each_face_must_be_three_id_list")
        if any(not isinstance(identifier, str) for identifier in face):
            raise SurfaceTopologyInputError("faces.ids_must_be_strings")
        a, b, c = face
        if len({a, b, c}) != 3:
            raise SurfaceTopologyInputError("faces.vertices_must_be_distinct")
        if any(identifier not in seen_ids for identifier in (a, b, c)):
            raise SurfaceTopologyInputError("faces.reference_unknown_vertex")
        face_ids.append((a, b, c))

    input_payload = jcs_bytes(
        cast(JSONValue, {"vertices": vertex_ids, "faces": [list(face) for face in face_ids]})
    )
    input_digest = _sha256(
        b"Crochet.AI\x00"
        + SURFACE_TOPOLOGY_AUDIT_V1.encode("ascii")
        + b"\x00INPUT\x00"
        + input_payload
    ).hexdigest()

    diagnostics: set[str] = set()
    unique_faces: set[tuple[str, str, str]] = set()
    edge_incidents: dict[_Edge, list[int]] = defaultdict(list)
    graph: dict[str, set[str]] = {identifier: set() for identifier in vertex_ids}
    vertex_links: dict[str, list[_Edge]] = {identifier: [] for identifier in vertex_ids}
    used_vertices: set[str] = set()

    for a, b, c in face_ids:
        first_id, second_id, third_id = sorted((a, b, c))
        unoriented = (first_id, second_id, third_id)
        if unoriented in unique_faces:
            diagnostics.add("face.duplicate_unoriented")
        unique_faces.add(unoriented)
        used_vertices.update((a, b, c))
        for start, end in ((a, b), (b, c), (c, a)):
            edge = (start, end) if start < end else (end, start)
            edge_incidents[edge].append(1 if (start, end) == edge else -1)
            graph[start].add(end)
            graph[end].add(start)
        vertex_links[a].append(_ordered_edge(b, c))
        vertex_links[b].append(_ordered_edge(c, a))
        vertex_links[c].append(_ordered_edge(a, b))

    if len(used_vertices) != len(vertex_ids):
        diagnostics.add("vertex.unused")

    for directions in edge_incidents.values():
        if len(directions) != 2:
            diagnostics.add("edge.incidence_count_not_two")
        elif sum(directions) != 0:
            diagnostics.add("edge.orientation_not_opposed")

    component_count = _component_count(graph)
    if component_count != 1:
        diagnostics.add("surface.disconnected")

    links_valid = all(_is_simple_cycle(link_edges) for link_edges in vertex_links.values())
    if not links_valid:
        diagnostics.add("vertex.link_not_simple_cycle")

    vertex_count = len(vertex_ids)
    edge_count = len(edge_incidents)
    face_count = len(face_ids)
    euler = vertex_count - edge_count + face_count
    manifold_oriented = (
        "face.duplicate_unoriented" not in diagnostics
        and "edge.incidence_count_not_two" not in diagnostics
        and "edge.orientation_not_opposed" not in diagnostics
        and links_valid
    )
    betti = (
        (component_count, 2 * component_count - euler, component_count)
        if manifold_oriented
        else None
    )
    if manifold_oriented and euler != 2:
        diagnostics.add("surface.euler_characteristic_not_two")
    status = "PASS" if not diagnostics else "FAIL"
    return SurfaceTopologyAudit(
        status=status,
        input_sha256=input_digest,
        vertex_count=vertex_count,
        edge_count=edge_count,
        face_count=face_count,
        components=component_count,
        euler_characteristic=euler,
        diagnostics=tuple(sorted(diagnostics)),
        betti_numbers=betti,
        max_vertices=max_vertices,
        max_faces=max_faces,
    )


def _validate_budget(value: object, maximum: int, name: str) -> None:
    if type(value) is not int or not 1 <= value <= maximum:
        raise SurfaceTopologyInputError(f"{name}.must_be_positive_exact_int_at_most_{maximum}")


def _ordered_edge(first: str, second: str) -> _Edge:
    return (first, second) if first < second else (second, first)


def _component_count(graph: dict[str, set[str]]) -> int:
    unseen = set(graph)
    components = 0
    while unseen:
        components += 1
        start = next(iter(unseen))
        unseen.remove(start)
        queue = deque([start])
        while queue:
            current = queue.popleft()
            for neighbor in graph[current]:
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    queue.append(neighbor)
    return components


def _is_simple_cycle(link_edges: list[_Edge]) -> bool:
    if not link_edges:
        return False
    edge_set = set(link_edges)
    if len(edge_set) != len(link_edges):
        return False
    adjacency: dict[str, set[str]] = defaultdict(set)
    for first, second in link_edges:
        adjacency[first].add(second)
        adjacency[second].add(first)
    if any(len(neighbors) != 2 for neighbors in adjacency.values()):
        return False
    start = min(adjacency)
    reached = {start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for neighbor in adjacency[current]:
            if neighbor not in reached:
                reached.add(neighbor)
                queue.append(neighbor)
    return len(reached) == len(adjacency)
