from __future__ import annotations

from copy import deepcopy
from math import pi
from typing import Any

import pytest
from conftest import resolved_artifacts
from test_analytic_coordinate_target import _design as _coordinate_design

from crochet_ai.analytic_coordinate_target import AnalyticCoordinateTarget
from crochet_ai.analytic_target import AnalyticTarget, admit_analytic_target
from crochet_ai.analytic_target_surface import (
    POLICY_PROFILE,
    AnalyticTargetSurfaceError,
    sample_analytic_target_surface,
)
from crochet_ai.canonical import parse_json
from crochet_ai.schema import validate_schema
from crochet_ai.validation import SemanticValidator


def _validator(design: dict[str, Any], material: dict[str, Any]) -> SemanticValidator:
    return SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={(material["profile_id"], material["revision"]): material},
    )


def _sphere(
    radius: float = 2.0,
) -> tuple[dict[str, Any], dict[str, Any], SemanticValidator, AnalyticTarget]:
    design, material = resolved_artifacts()
    design["dimensions"]["measurements"][0]["value_mm"] = radius
    validator = _validator(design, material)
    target = admit_analytic_target(design, validator)
    assert isinstance(target, AnalyticTarget)
    return design, material, validator, target


def _coordinate(
    points: list[tuple[float, float]],
) -> tuple[dict[str, Any], dict[str, Any], SemanticValidator, AnalyticCoordinateTarget]:
    design, material = _coordinate_design(points)
    validator = _validator(design, material)
    target = admit_analytic_target(design, validator)
    assert isinstance(target, AnalyticCoordinateTarget)
    return design, material, validator, target


def _policy(*, rings: int = 8, sectors: int = 16) -> dict[str, Any]:
    return {
        "profile": POLICY_PROFILE,
        "schema_version": "1.0.0",
        "ring_count": rings,
        "azimuth_sectors": sectors,
    }


def _coordinate_policy(*, subdivisions: int = 1, sectors: int = 16) -> dict[str, Any]:
    return {
        "profile": POLICY_PROFILE,
        "schema_version": "1.0.0",
        "linear_segment_subdivisions": subdivisions,
        "azimuth_sectors": sectors,
    }


def _signed_volume(
    vertices: tuple[tuple[float, float, float], ...], faces: tuple[tuple[int, int, int], ...]
) -> float:
    total = 0.0
    for a, b, c in faces:
        p, q, r = vertices[a], vertices[b], vertices[c]
        total += (
            p[0] * (q[1] * r[2] - q[2] * r[1])
            + p[1] * (q[2] * r[0] - q[0] * r[2])
            + p[2] * (q[0] * r[1] - q[1] * r[0])
        ) / 6
    return total


def test_sphere_mesh_is_outward_closed_deterministic_and_within_volume_bounds() -> None:
    design, _material, validator, target = _sphere()
    policy = _policy()
    one = sample_analytic_target_surface(design, target, policy, validator=validator)
    two = sample_analytic_target_surface(design, target, policy, validator=validator)
    assert one == two
    assert len(one.vertices_mm) == 2 + 7 * 16
    assert len(one.faces) == 2 * 16 * 7
    assert one.start_pole_vertex != one.end_pole_vertex
    assert len(set(one.vertices_mm)) == len(one.vertices_mm)
    sampled_volume = _signed_volume(one.vertices_mm, one.faces)
    ideal_volume = 4 * pi * 2.0**3 / 3
    assert 0 < sampled_volume < ideal_volume
    assert sampled_volume / ideal_volume > 0.85
    report = one.to_dict()
    assert report["v0_certificate"] == "NOT_PROVIDED"
    assert report["ideal_surface_certificate"] == "NOT_PROVIDED"
    assert report["approximation"]["coverage_bound_mm"] == one.analytic_discretization_bound_mm
    mesh_doc = parse_json(one.sampled_mesh_jcs_bytes)
    assert validate_schema("indexed_triangle_mesh", mesh_doc).ok
    assert one.sampled_mesh_sha256
    assert one.design_spec_jcs_sha256


def test_minimal_sphere_grid_is_tetrahedral_bipyramid_with_shared_seam_and_poles() -> None:
    design, _material, validator, target = _sphere()
    mesh = sample_analytic_target_surface(
        design, target, _policy(rings=2, sectors=4), validator=validator
    )
    assert len(mesh.vertices_mm) == 6
    assert len(mesh.faces) == 8
    assert _signed_volume(mesh.vertices_mm, mesh.faces) > 0
    assert mesh.vertices_mm[mesh.start_pole_vertex] == (0.0, -2.0, 0.0)
    assert mesh.vertices_mm[mesh.end_pole_vertex] == (0.0, 2.0, 0.0)
    assert all(len(set(face)) == 3 for face in mesh.faces)
    assert all(0 <= index < len(mesh.vertices_mm) for face in mesh.faces for index in face)


def test_signed_axis_and_origin_are_applied_in_declared_right_handed_frame() -> None:
    design, _material, validator, _target = _sphere()
    design["target_geometry"]["origin_mm"] = [10.0, -3.0, 7.5]
    design["target_geometry"]["coordinate_frame"]["up_axis"] = "NEGATIVE_Y"
    design["target_geometry"]["coordinate_frame"]["front_axis"] = "POSITIVE_X"
    target = admit_analytic_target(design, validator)
    assert isinstance(target, AnalyticTarget)
    mesh = sample_analytic_target_surface(
        design, target, _policy(rings=4, sectors=8), validator=validator
    )
    assert mesh.vertices_mm[mesh.start_pole_vertex] == (10.0, -1.0, 7.5)
    assert mesh.vertices_mm[mesh.end_pole_vertex] == (10.0, -5.0, 7.5)
    assert _signed_volume(mesh.vertices_mm, mesh.faces) > 0


@pytest.mark.parametrize(
    "points",
    [
        [(0, 0), (2, 1), (5, 3), (4, 6), (2, 8), (0, 10)],  # pear-like
        [(0, 0), (4, 2), (2, 4), (4, 6), (0, 8)],  # hourglass meridian
        [(0, 0), (4, 0), (4, 4), (0, 4)],  # explicit planar cap at each end
    ],
)
def test_coordinate_mesh_preserves_every_authored_knot_and_has_outward_closed_topology(
    points: list[tuple[float, float]],
) -> None:
    design, _material, validator, target = _coordinate(points)
    mesh = sample_analytic_target_surface(
        design, target, _coordinate_policy(subdivisions=2, sectors=12), validator=validator
    )
    assert len(mesh.authored_knot_vertex_indices) == len(points)
    assert len(set(mesh.authored_knot_vertex_indices)) == len(points)
    assert mesh.authored_knot_vertex_indices[0] == mesh.start_pole_vertex
    assert mesh.authored_knot_vertex_indices[-1] == mesh.end_pole_vertex
    for (radius, axial), vertex_index in zip(
        points, mesh.authored_knot_vertex_indices, strict=True
    ):
        point = mesh.vertices_mm[vertex_index]
        origin = target.origin_mm
        delta = tuple(point[axis] - origin[axis] for axis in range(3))
        assert sum(delta[axis] * target.right_axis[axis] for axis in range(3)) == pytest.approx(
            radius
        )
        assert sum(delta[axis] * target.second_axis[axis] for axis in range(3)) == pytest.approx(
            0.0
        )
        assert sum(delta[axis] * target.up_axis[axis] for axis in range(3)) == pytest.approx(axial)
    assert _signed_volume(mesh.vertices_mm, mesh.faces) > 0
    assert mesh.source_profile_sha256 == target.profile_sha256
    assert mesh.analytic_discretization_bound_mm > 0


@pytest.mark.parametrize(
    "policy",
    [
        {**_policy(), "surprise": 1},
        {**_policy(), "schema_version": "2.0.0"},
        {**_policy(), "ring_count": True},
        {**_policy(), "azimuth_sectors": 3},
        {**_policy(rings=64, sectors=64)},
    ],
)
def test_policy_schema_native_integer_ranges_and_output_caps_fail_closed(
    policy: dict[str, Any],
) -> None:
    design, _material, validator, target = _sphere()
    with pytest.raises(AnalyticTargetSurfaceError):
        sample_analytic_target_surface(design, target, policy, validator=validator)


def test_coordinate_policy_checks_mesh_caps_before_sampling() -> None:
    design, _material, validator, target = _coordinate([(0, 0), (4, 1), (3, 5), (0, 6)])
    with pytest.raises(AnalyticTargetSurfaceError, match="mesh_budget_exceeded"):
        sample_analytic_target_surface(
            design,
            target,
            _coordinate_policy(subdivisions=8, sectors=64),
            validator=validator,
        )


def test_binary64_coordinate_collapse_is_rejected_without_welding() -> None:
    design, material = resolved_artifacts()
    design["dimensions"]["measurements"][0]["value_mm"] = 1e-323
    validator = _validator(design, material)
    target = admit_analytic_target(design, validator)
    assert isinstance(target, AnalyticTarget)
    with pytest.raises(AnalyticTargetSurfaceError, match="sample_vertices_collapse"):
        sample_analytic_target_surface(design, target, _policy(), validator=validator)


def test_design_target_hash_binding_is_rechecked_before_mesh_emission() -> None:
    design, _material, validator, target = _sphere()
    changed = deepcopy(design)
    changed["target_geometry"]["origin_mm"] = [0.5, 0.0, 0.0]
    with pytest.raises(AnalyticTargetSurfaceError, match="target_design_binding_mismatch"):
        sample_analytic_target_surface(changed, target, _policy(), validator=validator)
