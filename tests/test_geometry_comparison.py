from __future__ import annotations

from copy import deepcopy

import pytest

from crochet_ai.geometry_comparison import GeometryComparisonError, compare_geometry


def tetra(scale: float = 1.0, shift=(0.0, 0.0, 0.0)):
    vertices = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]
    return {
        "representation_version": "INDEXED_TRIANGLE_MESH_V1",
        "coordinate_system": {
            "length_unit": "MILLIMETER",
            "handedness": "RIGHT_HANDED",
            "coordinate_frame_id": "frame_fixture",
        },
        "vertices": [
            {"position_mm": [scale * x + shift[0], scale * y + shift[1], scale * z + shift[2]]}
            for x, y, z in vertices
        ],
        "faces": [
            {"vertex_indices": list(f)} for f in ((0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3))
        ],
    }


def policy():
    return {
        "policy_version": "GEOMETRY_COMPARISON_POLICY_V1",
        "profile_id": "GEOMETRY_COMPARISON_DIAGNOSTIC_V1",
        "provenance_status": "HYPOTHESIS",
        "coordinate_frame_id": "frame_fixture",
        "initial_alignment": "IDENTITY_V1",
        "characteristic_length_mm": 2.0,
        "characteristic_length_owner": "test owner",
        "characteristic_length_rationale": "fixed fixture scale",
        "max_vertices": 512,
        "max_faces": 1024,
        "max_distance_queries": 200000,
        "max_raster_tests": 2000000,
        "samples_per_face": 3,
        "robust_percentile": 95,
        "raster_resolution": 8,
        "section_planes_z_mm": [0.2],
        "landmarks": [],
        "hard_thresholds": {
            "symmetric_chamfer_normalized": {
                "value": 0.1,
                "unit": "1",
                "owner": "test owner",
                "rationale": "fixture",
                "validation_path": "fixture",
            },
            "silhouette_iou_min": {
                "value": 0.1,
                "unit": "1",
                "owner": "test owner",
                "rationale": "fixture",
                "validation_path": "fixture",
            },
            "topology_match": {
                "value": 0,
                "unit": "1",
                "owner": "test owner",
                "rationale": "fixture",
                "validation_path": "fixture",
            },
            "normal_mean_degrees": {
                "value": 5,
                "unit": "degree",
                "owner": "test owner",
                "rationale": "fixture",
                "validation_path": "fixture",
            },
            "section_error_normalized": {
                "value": 0.1,
                "unit": "1",
                "owner": "test owner",
                "rationale": "fixture",
                "validation_path": "fixture",
            },
            "relative_volume_error": {
                "value": 0.1,
                "unit": "1",
                "owner": "test owner",
                "rationale": "fixture",
                "validation_path": "fixture",
            },
            "curvature_error_normalized": {
                "value": 0.01,
                "unit": "1",
                "owner": "test owner",
                "rationale": "fixture",
                "validation_path": "fixture",
            },
        },
    }


def subdivided_octahedron(level: int):
    mesh = {
        "representation_version": "INDEXED_TRIANGLE_MESH_V1",
        "coordinate_system": {
            "length_unit": "MILLIMETER",
            "handedness": "RIGHT_HANDED",
            "coordinate_frame_id": "frame_fixture",
        },
        "vertices": [
            {"position_mm": list(point)}
            for point in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))
        ],
        "faces": [
            {"vertex_indices": list(face)}
            for face in (
                (4, 0, 2),
                (4, 2, 1),
                (4, 1, 3),
                (4, 3, 0),
                (5, 2, 0),
                (5, 1, 2),
                (5, 3, 1),
                (5, 0, 3),
            )
        ],
    }
    for _ in range(level):
        vertices = [vertex["position_mm"] for vertex in mesh["vertices"]]
        midpoint_ids = {}

        def midpoint(first, second, cache=midpoint_ids, points=vertices):
            edge = tuple(sorted((first, second)))
            if edge not in cache:
                a, b = (points[index] for index in edge)
                cache[edge] = len(points)
                points.append([(x + y) / 2 for x, y in zip(a, b, strict=True)])
            return cache[edge]

        faces = []
        for record in mesh["faces"]:
            a, b, c = record["vertex_indices"]
            ab, bc, ca = midpoint(a, b), midpoint(b, c), midpoint(c, a)
            faces.extend(((a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)))
        mesh["vertices"] = [{"position_mm": point} for point in vertices]
        mesh["faces"] = [{"vertex_indices": list(face)} for face in faces]
    return mesh


def test_identical_mesh_has_deterministic_diagnostic_only_pass():
    mesh = tetra()
    first = compare_geometry(mesh, mesh, policy())
    second = compare_geometry(mesh, mesh, policy())
    assert first == second
    assert first["metrics"]["symmetric_chamfer_normalized"] == pytest.approx(0, abs=1e-15)
    assert first["metrics"]["relative_volume_error"] == 0
    assert first["metrics"]["topology"]["predicted"]["betti_1"] == 0
    assert first["metrics"]["volume_status"] == "COMPUTED"
    assert first["metrics"]["curvature_diagnostics"]["status"] == "COMPUTED"
    assert first["metrics"]["curvature_diagnostics"][
        "area_weighted_p95_absolute_error_normalized"
    ] == pytest.approx(0, abs=1e-12)
    assert first["verification_claim"] == "NOT_VERIFIED"
    assert first["physical_status"] == "UNTESTED"
    assert first["outcome"] == "PASS"


def test_uniform_scale_is_not_aligned_and_reports_geometry_failure():
    result = compare_geometry(tetra(1), tetra(2), policy())
    assert result["alignment"] == "IDENTITY_V1"
    assert result["metrics"]["symmetric_chamfer_normalized"] > 0
    assert result["metrics"]["silhouette_iou_min"] < 1
    assert result["outcome"] == "FAIL"
    assert result["metrics"]["relative_volume_error"] > 0
    assert result["metrics"]["curvature_diagnostics"]["area_weighted_p95_absolute_error"] > 0


def test_curvature_is_invariant_under_rigid_transform_in_fixed_frame():
    from crochet_ai.geometry_comparison import (
        _face_data,
        _mesh,
        _topology,
        _vertex_gaussian_curvature,
    )

    source = tetra()
    transformed = deepcopy(source)
    for vertex in transformed["vertices"]:
        x, y, z = vertex["position_mm"]
        vertex["position_mm"] = [-y + 3, x - 2, z + 5]
    source_mesh = _mesh(source, "frame_fixture")
    transformed_mesh = _mesh(transformed, "frame_fixture")
    _, source_areas, _ = _face_data(source_mesh)
    _, transformed_areas, _ = _face_data(transformed_mesh)
    source_values = _vertex_gaussian_curvature(source_mesh, source_areas, _topology(source_mesh))
    transformed_values = _vertex_gaussian_curvature(
        transformed_mesh, transformed_areas, _topology(transformed_mesh)
    )
    assert source_values == pytest.approx(transformed_values, abs=1e-12)
    result = compare_geometry(transformed, transformed, policy())
    curvature = result["metrics"]["curvature_diagnostics"]
    assert curvature["status"] == "COMPUTED"
    assert curvature["area_weighted_p95_absolute_error_normalized"] == pytest.approx(0, abs=1e-12)


def test_curvature_detects_irregular_vertex_displacement():
    irregular = tetra()
    irregular["vertices"][1]["position_mm"][0] = 1.7
    irregular["vertices"][3]["position_mm"][2] = 1.4
    result = compare_geometry(irregular, tetra(), policy())
    curvature = result["metrics"]["curvature_diagnostics"]
    assert curvature["status"] == "COMPUTED"
    assert curvature["area_weighted_mean_absolute_error"] > 0
    assert "curvature_error_normalized" in result["hard_failures"]


def test_curvature_is_indeterminate_for_open_surface():
    open_mesh = tetra()
    open_mesh["faces"] = open_mesh["faces"][:-1]
    result = compare_geometry(open_mesh, open_mesh, policy())
    curvature = result["metrics"]["curvature_diagnostics"]
    assert curvature["status"] == "INDETERMINATE"
    assert "closed_manifold_surface_required" in curvature["reason"]
    assert (
        result["threshold_evaluations"]["curvature_error_normalized"]["status"] == "INDETERMINATE"
    )


def test_degenerate_triangle_fails_closed_before_curvature():
    degenerate = tetra()
    degenerate["vertices"][1]["position_mm"] = [0, 0, 0]
    with pytest.raises(GeometryComparisonError) as error:
        compare_geometry(degenerate, tetra(), policy())
    assert error.value.code == "E_INPUT"


def test_topology_change_is_a_hard_metric_failure():
    changed = tetra()
    changed["faces"] = changed["faces"][:-1]
    result = compare_geometry(changed, tetra(), policy())
    assert result["metrics"]["topology"]["matches"] is False
    assert "topology_match" in result["hard_failures"]


def test_reversed_winding_is_caught_by_normal_metric_after_face_reordering():
    reversed_mesh = tetra()
    reversed_mesh["faces"] = [
        {
            "vertex_indices": [
                face["vertex_indices"][0],
                face["vertex_indices"][2],
                face["vertex_indices"][1],
            ]
        }
        for face in reversed(reversed_mesh["faces"])
    ]
    result = compare_geometry(reversed_mesh, tetra(), policy())
    assert result["metrics"]["surface_normal_mean_degrees"] == pytest.approx(180)
    assert "normal_mean_degrees" in result["hard_failures"]
    assert "relative_volume_error" in result["hard_failures"]


def test_section_area_is_computed_and_scale_changes_section_metrics():
    base = tetra()
    policy_value = policy()
    policy_value["section_planes_z_mm"] = [0.2]
    identical = compare_geometry(base, base, policy_value)
    section = identical["metrics"]["cross_sections"][0]
    assert section["status"] == "COMPUTED"
    assert section["predicted_area_mm2"] > 0
    assert section["relative_area_error"] == 0

    scaled = compare_geometry(tetra(2), base, policy_value)
    scaled_section = scaled["metrics"]["cross_sections"][0]
    assert scaled_section["relative_area_error"] > 0
    assert scaled_section["error_normalized"] > 0
    assert "section_error_normalized" in scaled["hard_failures"]


def test_translated_section_contour_changes_even_when_both_meshes_intersect_plane():
    policy_value = policy()
    policy_value["section_planes_z_mm"] = [0.2]
    shifted = tetra(shift=(0, 0, 0.1))
    result = compare_geometry(shifted, tetra(), policy_value)
    section = result["metrics"]["cross_sections"][0]
    assert section["status"] == "COMPUTED"
    assert section["error_normalized"] > 0
    assert "section_error_normalized" in result["hard_failures"]


def test_missing_section_is_hard_failure_even_with_generous_numeric_threshold():
    policy_value = policy()
    policy_value["section_planes_z_mm"] = [0.2]
    policy_value["hard_thresholds"]["section_error_normalized"]["value"] = 10
    shifted = tetra(shift=(0, 0, 2))
    result = compare_geometry(shifted, tetra(), policy_value)
    assert result["metrics"]["section_topology_mismatch"] is True
    assert "section_error_normalized" in result["hard_failures"]


def test_empty_projected_coverage_is_indeterminate_not_perfect_iou():
    planar_patch = {
        "representation_version": "INDEXED_TRIANGLE_MESH_V1",
        "coordinate_system": {
            "length_unit": "MILLIMETER",
            "handedness": "RIGHT_HANDED",
            "coordinate_frame_id": "frame_fixture",
        },
        "vertices": [
            {"position_mm": [0, 0, 0]},
            {"position_mm": [1, 0, 0]},
            {"position_mm": [1, 1, 0]},
            {"position_mm": [0, 1, 0]},
        ],
        "faces": [{"vertex_indices": [0, 1, 2]}, {"vertex_indices": [0, 2, 3]}],
    }
    result = compare_geometry(planar_patch, planar_patch, policy())
    assert result["metrics"]["silhouette_iou_by_view"]["Y"] is None
    assert result["metrics"]["silhouette_iou_min"] is None
    assert result["threshold_evaluations"]["silhouette_iou_min"]["status"] == "INDETERMINATE"


def test_absolute_translation_is_not_registered_away():
    result = compare_geometry(tetra(), tetra(shift=(4, 0, 0)), policy())
    assert result["metrics"]["symmetric_chamfer_normalized"] > 0
    assert result["hard_failures"]


def test_budgets_fail_before_partial_metric_record():
    p = policy()
    p["max_distance_queries"] = 1
    with pytest.raises(
        GeometryComparisonError, match="distance_queries_budget_exhausted_before_work"
    ) as error:
        compare_geometry(tetra(), tetra(), p)
    assert error.value.code == "E_SEARCH_BUDGET"


def test_raster_budget_is_admitted_before_rasterization():
    p = policy()
    p["max_raster_tests"] = 1
    with pytest.raises(
        GeometryComparisonError, match="raster_tests_budget_exhausted_before_work"
    ) as error:
        compare_geometry(tetra(), tetra(), p)
    assert error.value.code == "E_SEARCH_BUDGET"


def test_policy_rejects_claims_of_calibrated_provenance():
    p = policy()
    p["provenance_status"] = "CALIBRATED"
    with pytest.raises(GeometryComparisonError) as error:
        compare_geometry(tetra(), tetra(), p)
    assert error.value.code == "E_UNSUPPORTED_FEATURE"


def test_policy_requires_at_least_one_owned_hard_threshold():
    p = policy()
    p["hard_thresholds"] = {}
    with pytest.raises(GeometryComparisonError, match="hard_threshold_required"):
        compare_geometry(tetra(), tetra(), p)


def test_finite_off_vertex_point_triangle_distance_oracle():
    # Independent analytic oracle for the interior projection onto z=0.
    from crochet_ai.geometry_comparison import _nearest

    distances, _, _, _ = _nearest([(0.25, 0.25, 2.0)], [((0, 0, 0), (1, 0, 0), (0, 1, 0))], 1, 1)
    distance_squared = distances[0] ** 2
    assert distance_squared == pytest.approx(4.0)


def test_aabb_pruning_matches_dense_exact_nearest_face_oracle():
    from fractions import Fraction

    from crochet_ai.geometry_comparison import _exact_point_triangle, _face_data, _mesh, _nearest

    decoded = _mesh(tetra(), "frame_fixture")
    triangles, _, _ = _face_data(decoded)
    samples = [(0.2, 0.3, 0.4), (2.0, 1.0, -0.5)]
    distances, indices, queries, broadphase = _nearest(samples, triangles, 100, 100)
    expected = []
    for point in samples:
        exact_point = tuple(Fraction(value) for value in point)
        squared = [
            _exact_point_triangle(
                exact_point,
                tuple(tuple(Fraction(v) for v in vertex) for vertex in tri),
            )
            for tri in triangles
        ]
        minimum = min(squared)
        expected.append((minimum, min(i for i, value in enumerate(squared) if value == minimum)))
    assert indices == [index for _, index in expected]
    assert distances == pytest.approx([float(value) ** 0.5 for value, _ in expected])
    assert 0 < queries <= broadphase


def test_aabb_pruning_admits_surface_pair_beyond_dense_query_budget():
    mesh = subdivided_octahedron(3)
    p = policy()
    p["samples_per_face"] = 1
    p["section_planes_z_mm"] = []
    result = compare_geometry(mesh, mesh, p)
    assert len(mesh["faces"]) == 512
    assert result["work"]["distance_broadphase_tests"] == 2 * 512 * 512
    assert result["work"]["distance_queries"] < 2 * 512 * 512
    assert result["metrics"]["symmetric_chamfer_normalized"] == pytest.approx(0, abs=1e-15)


def test_exact_distance_budget_exhausts_before_over_budget_query():
    from crochet_ai.geometry_comparison import _face_data, _mesh, _nearest

    decoded = _mesh(tetra(), "frame_fixture")
    triangles, _, _ = _face_data(decoded)
    with pytest.raises(
        GeometryComparisonError,
        match="distance_queries_budget_exhausted_before_work",
    ):
        _nearest([(0.2, 0.2, 0.2)], triangles, 0, 4)


def test_input_objects_are_not_mutated():
    mesh = tetra()
    before = deepcopy(mesh)
    compare_geometry(mesh, mesh, policy())
    assert mesh == before


def test_hard_topology_and_units_cannot_be_relaxed_or_mislabeled() -> None:
    for key, bad_value in (("topology_match", 2), ("silhouette_iou_min", 2)):
        p = policy()
        p["hard_thresholds"][key]["value"] = bad_value
        with pytest.raises(GeometryComparisonError):
            compare_geometry(tetra(), tetra(), p)
    p = policy()
    p["hard_thresholds"]["normal_mean_degrees"]["unit"] = "N"
    with pytest.raises(GeometryComparisonError):
        compare_geometry(tetra(), tetra(), p)


def test_finite_normalization_overflow_is_a_typed_numeric_failure() -> None:
    p = policy()
    p["characteristic_length_mm"] = 1e308
    with pytest.raises(GeometryComparisonError, match="arithmetic_undefined"):
        compare_geometry(tetra(), tetra(), p)


def test_landmark_prediction_is_looked_up_from_the_decoded_mesh() -> None:
    p = policy()
    p["landmarks"] = [
        {"name": "tip", "predicted_vertex_index": 1, "target_xyz_mm": [1, 0, 0]}
    ]
    base = compare_geometry(tetra(), tetra(), p)
    shifted = compare_geometry(tetra(shift=(2, 0, 0)), tetra(), p)

    base_landmark = base["metrics"]["landmarks"][0]
    shifted_landmark = shifted["metrics"]["landmarks"][0]
    assert base_landmark["predicted_vertex_index"] == 1
    assert base_landmark["predicted_xyz_mm"] == [1, 0, 0]
    assert base_landmark["target_xyz_mm"] == [1, 0, 0]
    assert base_landmark["distance_mm"] == 0
    assert shifted_landmark["predicted_xyz_mm"] == [3, 0, 0]
    assert shifted_landmark["distance_mm"] == 2
    assert shifted_landmark["normalized"] == 1


def test_landmark_policy_rejects_forged_coordinates_boolean_and_out_of_profile_indices():
    malformed = policy()
    malformed["landmarks"] = [
        {
            "name": "tip",
            "predicted_xyz_mm": [1, 0, 0],
            "target_xyz_mm": [1, 0, 0],
        }
    ]
    with pytest.raises(GeometryComparisonError, match="landmark_shape_invalid"):
        compare_geometry(tetra(), tetra(), malformed)

    for index in (True, -1, 512):
        invalid = policy()
        invalid["landmarks"] = [
            {"name": "tip", "predicted_vertex_index": index, "target_xyz_mm": [1, 0, 0]}
        ]
        with pytest.raises(GeometryComparisonError, match="landmark_vertex_index_invalid"):
            compare_geometry(tetra(), tetra(), invalid)

    dangling = policy()
    dangling["landmarks"] = [
        {"name": "tip", "predicted_vertex_index": 4, "target_xyz_mm": [1, 0, 0]}
    ]
    with pytest.raises(GeometryComparisonError, match="out_of_mesh_bounds") as error:
        compare_geometry(tetra(), tetra(), dangling)
    assert error.value.code == "E_REFERENCE"


def test_empty_landmark_set_has_deterministic_zero_and_explicit_status():
    comparison_policy = policy()
    comparison_policy["hard_thresholds"]["landmark_max_normalized"] = {
        "value": 0.1,
        "unit": "1",
        "owner": "test owner",
        "rationale": "fixture",
        "validation_path": "fixture",
    }
    first = compare_geometry(tetra(), tetra(), comparison_policy)
    second = compare_geometry(tetra(), tetra(), comparison_policy)
    assert first == second
    assert first["metrics"]["landmark_status"] == "NO_REQUIRED_LANDMARKS"
    assert first["metrics"]["landmark_max_normalized"] == 0.0
    assert first["threshold_evaluations"]["landmark_max_normalized"]["status"] == "PASS"


def test_zero_landmark_threshold_passes_only_for_exact_vertex_match():
    p = policy()
    p["landmarks"] = [
        {"name": "tip", "predicted_vertex_index": 1, "target_xyz_mm": [1, 0, 0]}
    ]
    p["hard_thresholds"]["landmark_max_normalized"] = {
        "value": 0,
        "unit": "1",
        "owner": "test owner",
        "rationale": "exact declared vertex match",
        "validation_path": "fixture",
    }

    matching = compare_geometry(tetra(), tetra(), p)
    displaced = compare_geometry(tetra(shift=(0.25, 0, 0)), tetra(), p)
    assert matching["threshold_evaluations"]["landmark_max_normalized"]["status"] == "PASS"
    assert displaced["threshold_evaluations"]["landmark_max_normalized"]["status"] == "FAIL"
    assert displaced["metrics"]["landmark_max_normalized"] > 0

    p["hard_thresholds"]["landmark_max_normalized"]["value"] = -1e-12
    with pytest.raises(
        GeometryComparisonError, match=r"threshold\.landmark_max_normalized_invalid"
    ):
        compare_geometry(tetra(), tetra(), p)
