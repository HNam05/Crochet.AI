"""Independent V0 mesh fixtures, adversarial cases, and metamorphic properties."""

from __future__ import annotations

from copy import deepcopy

from hypothesis import given
from hypothesis import strategies as st

from crochet_ai.mesh_preflight import PreflightOutcome, preflight_mesh


def _mesh(
    vertices: list[list[float]], faces: list[list[int]], frame: str = "frame_mesh"
) -> dict[str, object]:
    return {
        "representation_version": "INDEXED_TRIANGLE_MESH_V1",
        "coordinate_system": {
            "length_unit": "MILLIMETER",
            "handedness": "RIGHT_HANDED",
            "coordinate_frame_id": frame,
        },
        "vertices": [{"position_mm": point} for point in vertices],
        "faces": [{"vertex_indices": face} for face in faces],
    }


def _design(
    profile: str,
    components: int,
    boundaries: int,
    *,
    openings: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "target_geometry": {
            "geometry_type": "MESH_3D",
            "coordinate_frame": {"coordinate_frame_id": "frame_mesh"},
            "preflight_profile_id": profile,
            "preflight_numerical_profile_id": "v0_num_mesh_binary64_v1",
            "topology_expectation": {
                "expected_connected_components": components,
                "expected_boundary_components": boundaries,
            },
        },
        "landmarks": [],
        "construction_constraints": {"intentional_openings": openings or []},
    }


def _tetrahedron() -> dict[str, object]:
    return _mesh(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        [[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]],
    )


def test_closed_tetrahedron_passes_and_is_deterministic() -> None:
    design = _design("V0_AMIGURUMI_CLOSED_SURFACE_V1", 1, 0)
    first = preflight_mesh(_tetrahedron(), design)
    second = preflight_mesh(_tetrahedron(), design)
    assert first.outcome == PreflightOutcome.PASS
    assert first == second
    assert first.components[0].is_closed
    assert first.components[0].is_manifold


def test_reliably_reversed_closed_component_is_normalized_once() -> None:
    mesh = _tetrahedron()
    for face in mesh["faces"]:
        a, b, c = face["vertex_indices"]
        face["vertex_indices"] = [a, c, b]
    result = preflight_mesh(mesh, _design("V0_AMIGURUMI_CLOSED_SURFACE_V1", 1, 0))
    assert result.outcome == PreflightOutcome.PASS
    assert "reverse_reliably_inverted_closed_component_v1" in result.normalization_events


def test_unknown_numerical_profile_is_indeterminate() -> None:
    design = _design("V0_AMIGURUMI_CLOSED_SURFACE_V1", 1, 0)
    design["target_geometry"]["preflight_numerical_profile_id"] = "v0_num_unknown_v1"
    result = preflight_mesh(_tetrahedron(), design)
    assert result.outcome == PreflightOutcome.INDETERMINATE
    assert result.diagnostics[0].message_key == "geometry.numeric_profile_unresolved"


def test_open_garment_sheet_is_not_required_to_be_watertight() -> None:
    mesh = _mesh([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], [[0, 1, 2], [0, 2, 3]])
    opening = {
        "opening_requirement_id": "opening_req_hem",
        "closure_expectation": "REMAIN_OPEN",
        "boundary_landmark_ids": [],
    }
    result = preflight_mesh(
        mesh, _design("V0_GARMENT_DECLARED_BOUNDARY_SURFACE_V1", 1, 1, openings=[opening])
    )
    assert result.outcome == PreflightOutcome.PASS
    assert not result.components[0].is_closed


def test_invalid_index_and_repeated_index_fail_closed() -> None:
    design = _design("V0_AMIGURUMI_CLOSED_SURFACE_V1", 1, 0)
    invalid = _mesh([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 3]])
    repeated = _mesh([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 1]])
    assert preflight_mesh(invalid, design).outcome == PreflightOutcome.FAIL
    assert preflight_mesh(repeated, design).outcome == PreflightOutcome.FAIL


def test_duplicate_and_coordinate_coincidence_fail() -> None:
    duplicate = _tetrahedron()
    duplicate["faces"].append({"vertex_indices": [0, 1, 2]})
    result = preflight_mesh(duplicate, _design("V0_AMIGURUMI_CLOSED_SURFACE_V1", 1, 0))
    assert any(item.message_key == "geometry.duplicate_face" for item in result.diagnostics)
    coincident = _mesh([[0, 0, 0], [0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 2, 3], [1, 3, 2]])
    result = preflight_mesh(coincident, _design("V0_GARMENT_DECLARED_BOUNDARY_SURFACE_V1", 1, 1))
    assert any(item.message_key == "geometry.coincident_vertex" for item in result.diagnostics)


def test_closed_profile_rejects_open_sheet() -> None:
    mesh = _mesh([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], [[0, 1, 2], [0, 2, 3]])
    result = preflight_mesh(mesh, _design("V0_AMIGURUMI_CLOSED_SURFACE_V1", 1, 0))
    assert result.outcome == PreflightOutcome.FAIL
    assert any(item.message_key == "geometry.unexpected_boundary" for item in result.diagnostics)


def test_nonmanifold_edge_and_coplanar_overlap_are_reported() -> None:
    nonmanifold = _mesh(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [0, -1, 0]],
        [[0, 1, 2], [1, 0, 3], [0, 1, 4]],
    )
    result = preflight_mesh(nonmanifold, _design("V0_AMIGURUMI_CLOSED_SURFACE_V1", 1, 0))
    assert any(item.message_key == "geometry.non_manifold" for item in result.diagnostics)
    overlap = _mesh(
        [
            [0, 0, 0],
            [2, 0, 0],
            [0, 2, 0],
            [0.5, 0.5, 0],
            [1.5, 0.5, 0],
            [0.5, 1.5, 0],
        ],
        [[0, 1, 2], [3, 4, 5]],
    )
    result = preflight_mesh(overlap, _design("V0_AMIGURUMI_CLOSED_SURFACE_V1", 2, 0))
    assert any(item.message_key == "geometry.intersection" for item in result.diagnostics)


def test_positive_uniform_scale_preserves_closed_tetrahedron_outcome() -> None:
    design = _design("V0_AMIGURUMI_CLOSED_SURFACE_V1", 1, 0)
    expected = preflight_mesh(_tetrahedron(), design).outcome
    for scale in (1e-6, 1e6):
        mesh = _tetrahedron()
        for vertex in mesh["vertices"]:
            vertex["position_mm"] = [scale * value for value in vertex["position_mm"]]
        assert preflight_mesh(mesh, design).outcome == expected


@given(
    translation=st.tuples(
        st.floats(-10, 10, allow_nan=False, allow_infinity=False),
        st.floats(-10, 10, allow_nan=False, allow_infinity=False),
        st.floats(-10, 10, allow_nan=False, allow_infinity=False),
    )
)
def test_translation_preserves_v0_classification(translation: tuple[float, float, float]) -> None:
    mesh = _tetrahedron()
    moved = deepcopy(mesh)
    for vertex in moved["vertices"]:
        point = vertex["position_mm"]
        vertex["position_mm"] = [point[index] + translation[index] for index in range(3)]
    design = _design("V0_AMIGURUMI_CLOSED_SURFACE_V1", 1, 0)
    assert preflight_mesh(mesh, design).outcome == preflight_mesh(moved, design).outcome


def test_vertex_renumbering_and_face_order_preserve_outcome() -> None:
    mesh = _tetrahedron()
    permutation = (3, 1, 0, 2)
    inverse = {old: new for new, old in enumerate(permutation)}
    remapped = _mesh(
        [mesh["vertices"][index]["position_mm"] for index in permutation],
        [[inverse[index] for index in item["vertex_indices"]] for item in reversed(mesh["faces"])],
    )
    design = _design("V0_AMIGURUMI_CLOSED_SURFACE_V1", 1, 0)
    assert preflight_mesh(mesh, design).outcome == preflight_mesh(remapped, design).outcome
