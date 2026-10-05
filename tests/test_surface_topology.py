from __future__ import annotations

from itertools import product

import pytest

from crochet_ai.surface_topology import (
    MAX_FACES,
    MAX_VERTICES,
    SurfaceTopologyInputError,
    audit_surface_topology,
)


def tetrahedron(prefix: str = "v") -> tuple[list[str], list[list[str]]]:
    vertices = [f"{prefix}{index}" for index in range(4)]
    a, b, c, d = vertices
    return vertices, [[a, c, b], [a, b, d], [b, c, d], [c, a, d]]


def torus_grid(size: int = 4) -> tuple[list[str], list[list[str]]]:
    vertices = [f"v{i}_{j}" for i, j in product(range(size), repeat=2)]

    def vertex(i: int, j: int) -> str:
        return f"v{i % size}_{j % size}"

    faces: list[list[str]] = []
    for i, j in product(range(size), repeat=2):
        lower_left = vertex(i, j)
        lower_right = vertex(i + 1, j)
        upper_right = vertex(i + 1, j + 1)
        upper_left = vertex(i, j + 1)
        faces.extend(
            ([lower_left, lower_right, upper_right], [lower_left, upper_right, upper_left])
        )
    return vertices, faces


def join_disjoint(
    first: tuple[list[str], list[list[str]]], second: tuple[list[str], list[list[str]]]
) -> tuple[list[str], list[list[str]]]:
    return first[0] + second[0], first[1] + second[1]


def test_tetrahedron_is_oriented_sphere() -> None:
    vertices, faces = tetrahedron()
    result = audit_surface_topology(vertices, faces)

    assert result.status == "PASS"
    assert (result.vertex_count, result.edge_count, result.face_count) == (4, 6, 4)
    assert result.components == 1
    assert result.euler_characteristic == 2
    assert result.betti_numbers == (1, 0, 1)
    assert result.diagnostics == ()


def test_periodic_grid_is_torus_and_fails_sphere_profile() -> None:
    vertices, faces = torus_grid()
    result = audit_surface_topology(vertices, faces)

    assert result.status == "FAIL"
    assert result.euler_characteristic == 0
    assert result.betti_numbers == (1, 2, 1)
    assert result.diagnostics == ("surface.euler_characteristic_not_two",)


def test_disjoint_spheres_have_homology_for_both_components() -> None:
    left = tetrahedron("l")
    right = tetrahedron("r")
    result = audit_surface_topology(*join_disjoint(left, right))

    assert result.status == "FAIL"
    assert result.components == 2
    assert result.euler_characteristic == 4
    assert result.betti_numbers == (2, 0, 2)
    assert result.diagnostics == (
        "surface.disconnected",
        "surface.euler_characteristic_not_two",
    )


def test_spheres_pinched_at_one_vertex_fail_vertex_link() -> None:
    first_vertices, first_faces = tetrahedron("a")
    second_vertices, second_faces = tetrahedron("b")
    second_vertices[0] = first_vertices[0]
    second_faces = [
        [first_vertices[0] if value == "b0" else value for value in face] for face in second_faces
    ]
    result = audit_surface_topology(
        first_vertices + second_vertices[1:], first_faces + second_faces
    )

    assert result.status == "FAIL"
    assert result.components == 1
    assert result.betti_numbers is None
    assert "vertex.link_not_simple_cycle" in result.diagnostics


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("reverse", "edge.orientation_not_opposed"),
        ("missing", "edge.incidence_count_not_two"),
        ("duplicate", "face.duplicate_unoriented"),
    ],
)
def test_winding_boundary_and_duplicate_defects(mutation: str, expected: str) -> None:
    vertices, faces = tetrahedron()
    if mutation == "reverse":
        faces[0] = list(reversed(faces[0]))
    elif mutation == "missing":
        faces.pop()
    else:
        faces.append(faces[0].copy())

    result = audit_surface_topology(vertices, faces)

    assert result.status == "FAIL"
    assert expected in result.diagnostics
    if mutation in {"reverse", "missing", "duplicate"}:
        assert result.betti_numbers is None


def test_unused_vertex_is_reported() -> None:
    vertices, faces = tetrahedron()
    vertices.append("unused")
    result = audit_surface_topology(vertices, faces)

    assert result.status == "FAIL"
    assert "vertex.unused" in result.diagnostics
    assert result.betti_numbers is None


def test_oversized_label_is_rejected_before_content_inspection() -> None:
    class OversizedLabel(str):
        def isascii(self) -> bool:
            raise AssertionError("Oversized labels must be rejected before inspection")

    with pytest.raises(SurfaceTopologyInputError, match="at_most_128"):
        audit_surface_topology([OversizedLabel("a" * 129)], [["a", "b", "c"]])


@pytest.mark.parametrize(
    ("vertices", "faces"),
    [
        (["a", "b", "c"], [["a", "b", "missing"]]),
        (["a", "b", "c"], [["a", "b"]]),
        (["a", "b", "c"], [["a", "b", "b"]]),
        (["a", "b", "é"], [["a", "b", "é"]]),
        (["a", "a", "c"], [["a", "c", "a"]]),
        (["a", "b", "c"], [["a", "b", 3]]),
        (["a" * 129, "b", "c"], [["a" * 129, "b", "c"]]),
    ],
)
def test_malformed_ids_and_faces_reject(vertices: object, faces: object) -> None:
    with pytest.raises(SurfaceTopologyInputError):
        audit_surface_topology(vertices, faces)


@pytest.mark.parametrize("vertices,faces", [(True, 4), (0, 4), (4, False), (4, 0)])
def test_budget_values_are_exact_positive_ints(vertices: object, faces: object) -> None:
    sphere = tetrahedron()
    with pytest.raises(SurfaceTopologyInputError):
        audit_surface_topology(sphere[0], sphere[1], max_vertices=vertices, max_faces=faces)


def test_budgets_accept_exact_size_and_reject_one_below() -> None:
    vertices, faces = tetrahedron()
    assert audit_surface_topology(vertices, faces, max_vertices=4, max_faces=4).status == "PASS"
    with pytest.raises(SurfaceTopologyInputError, match=r"vertices.budget_exceeded"):
        audit_surface_topology(vertices, faces, max_vertices=3, max_faces=4)
    with pytest.raises(SurfaceTopologyInputError, match=r"faces.budget_exceeded"):
        audit_surface_topology(vertices, faces, max_vertices=4, max_faces=3)
    with pytest.raises(SurfaceTopologyInputError, match="max_vertices"):
        audit_surface_topology(vertices, faces, max_vertices=MAX_VERTICES + 1)
    with pytest.raises(SurfaceTopologyInputError, match="max_faces"):
        audit_surface_topology(vertices, faces, max_faces=MAX_FACES + 1)


def test_non_list_inputs_reject() -> None:
    vertices, faces = tetrahedron()
    with pytest.raises(SurfaceTopologyInputError):
        audit_surface_topology(tuple(vertices), faces)
    with pytest.raises(SurfaceTopologyInputError):
        audit_surface_topology(vertices, tuple(tuple(face) for face in faces))


def test_repeated_call_has_identical_canonical_evidence() -> None:
    vertices, faces = tetrahedron()
    first = audit_surface_topology(vertices, faces)
    second = audit_surface_topology(vertices.copy(), [face.copy() for face in faces])

    assert first.canonical_bytes == second.canonical_bytes
    assert first.sha256 == second.sha256
    assert len(first.sha256) == 64
    assert first.to_dict()["profile"] == "SURFACE_TOPOLOGY_AUDIT_V1"


def test_reordering_and_renaming_preserve_topology_metrics() -> None:
    vertices, faces = tetrahedron()
    renamed = {value: f"id_{index}" for index, value in enumerate(reversed(vertices))}
    transformed_vertices = [renamed[value] for value in reversed(vertices)]
    transformed_faces = [[renamed[value] for value in face] for face in reversed(faces)]
    first = audit_surface_topology(vertices, faces)
    second = audit_surface_topology(transformed_vertices, transformed_faces)

    assert (
        first.status,
        first.vertex_count,
        first.edge_count,
        first.face_count,
        first.components,
        first.euler_characteristic,
        first.betti_numbers,
    ) == (
        second.status,
        second.vertex_count,
        second.edge_count,
        second.face_count,
        second.components,
        second.euler_characteristic,
        second.betti_numbers,
    )
