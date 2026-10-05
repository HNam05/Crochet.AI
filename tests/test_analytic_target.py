from __future__ import annotations

from copy import deepcopy
from math import isclose
from typing import Any

import pytest
from conftest import resolved_artifacts
from hypothesis import given
from hypothesis import strategies as st

from crochet_ai.analytic_target import AnalyticTargetError, admit_analytic_target
from crochet_ai.canonical import CanonicalProfile, canonical_hash
from crochet_ai.validation import SemanticValidator


def _validator_for(design: dict[str, Any]) -> SemanticValidator:
    material = resolved_artifacts()[1]
    return SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={(material["profile_id"], material["revision"]): material},
    )


def _admit(design: dict[str, Any]):
    return admit_analytic_target(design, _validator_for(design))


def _ellipsoid() -> dict[str, Any]:
    design, _ = resolved_artifacts()
    design["dimensions"]["measurements"][0]["value_mm"] = 2.5
    design["dimensions"]["measurements"].append(
        {
            "measurement_id": "dim_polar",
            "semantic": "CUSTOM",
            "label": "Polar radius",
            "value_mm": 4.25,
            "tolerance_mm": 0,
        }
    )
    design["target_geometry"]["primitive"] = "ELLIPSOID"
    design["target_geometry"]["parameters"] = [
        {"parameter": "EQUATORIAL_RADIUS", "measurement_id": "dim_fixture_radius"},
        {"parameter": "POLAR_RADIUS", "measurement_id": "dim_polar"},
    ]
    design["target_geometry"]["origin_mm"] = [10.0, -3.0, 7.5]
    design["target_geometry"]["coordinate_frame"]["up_axis"] = "NEGATIVE_Y"
    design["target_geometry"]["coordinate_frame"]["front_axis"] = "POSITIVE_X"
    return design


def test_ellipsoid_grid_satisfies_independent_implicit_equation_and_exact_vectors() -> None:
    design = _ellipsoid()
    target = _admit(design)
    assert target.right_axis == (0, 0, 1)
    assert target.second_axis == (-1, 0, 0)
    assert target.up_axis == (0, -1, 0)
    assert target.characteristic_length_mm == 8.5
    sample = target.sample(ring_count=4, sector_count=8)
    assert len(sample.points_mm) == 26
    assert sample.points_mm[0] == (10.0, 1.25, 7.5)
    assert sample.points_mm[-1] == (10.0, -7.25, 7.5)
    assert (7.5, -3.0, 7.5) in sample.points_mm
    assert (10.0, -3.0, 10.0) in sample.points_mm
    for point in sample.points_mm:
        delta = tuple(point[i] - target.origin_mm[i] for i in range(3))
        right = sum(delta[i] * target.right_axis[i] for i in range(3))
        second = sum(delta[i] * target.second_axis[i] for i in range(3))
        up = sum(delta[i] * target.up_axis[i] for i in range(3))
        implicit = (right / 2.5) ** 2 + (second / 2.5) ** 2 + (up / 4.25) ** 2
        assert isclose(implicit, 1.0, rel_tol=2e-15, abs_tol=2e-15)


def test_sphere_has_decimal_radius_and_deterministic_domain_hashes() -> None:
    design, _ = resolved_artifacts()
    design["dimensions"]["measurements"][0]["value_mm"] = 12.75
    target = _admit(design)
    again = _admit(deepcopy(design))
    assert target.equatorial_radius_mm == 12.75
    assert target.polar_radius_mm == 12.75
    assert target.to_dict() == again.to_dict()
    first = target.sample(ring_count=8, sector_count=12)
    second = target.sample(ring_count=8, sector_count=12)
    assert first == second
    assert first.sha256 != target.sha256


def test_design_hash_covers_unrelated_designspec_mutations_and_snapshot_is_immutable() -> None:
    design, _ = resolved_artifacts()
    target = _admit(design)
    prior_metadata = target.to_dict()
    design["colors"][0]["label"] = "Changed label"
    changed = _admit(design)
    assert changed.design_spec_sha256 != target.design_spec_sha256
    assert target.to_dict() == prior_metadata
    exposed = target.to_dict()
    exposed["origin_mm"][0] = 999
    assert target.origin_mm[0] == 0


@pytest.mark.parametrize("primitive", ["CYLINDER", "CONE", "SURFACE_OF_REVOLUTION"])
def test_ambiguous_or_unsupported_primitives_are_not_applicable(primitive: str) -> None:
    design, _ = resolved_artifacts()
    target = design["target_geometry"]
    target["primitive"] = primitive
    if primitive == "CYLINDER":
        design["dimensions"]["measurements"].append(
            {
                "measurement_id": "dim_len",
                "semantic": "LENGTH",
                "label": "L",
                "value_mm": 10,
                "tolerance_mm": 0,
            }
        )
        target["parameters"] = [
            {"parameter": "RADIUS", "measurement_id": "dim_fixture_radius"},
            {"parameter": "AXIAL_LENGTH", "measurement_id": "dim_len"},
        ]
    elif primitive == "CONE":
        design["dimensions"]["measurements"][0]["semantic"] = "CUSTOM"
        design["dimensions"]["measurements"].append(
            {
                "measurement_id": "dim_len",
                "semantic": "LENGTH",
                "label": "L",
                "value_mm": 10,
                "tolerance_mm": 0,
            }
        )
        target["parameters"] = [
            {"parameter": "BASE_RADIUS", "measurement_id": "dim_fixture_radius"},
            {"parameter": "AXIAL_LENGTH", "measurement_id": "dim_len"},
        ]
    else:
        design["dimensions"]["measurements"][0]["semantic"] = "LENGTH"
        design["dimensions"]["measurements"][0]["value_mm"] = 10
        target["parameters"] = [
            {"parameter": "MERIDIONAL_LENGTH", "measurement_id": "dim_fixture_radius"}
        ]
        target["axis_direction"] = [0, 1, 0]
        target["radial_profile"] = {
            "canonicalization_profile": "SURFACE_OF_REVOLUTION_PROFILE_CANONICAL_JSON_V1",
            "samples": [
                {"sample_index": 0, "s_mm": 0, "radius_mm": 0},
                {"sample_index": 1, "s_mm": 5, "radius_mm": 3},
                {"sample_index": 2, "s_mm": 10, "radius_mm": 0},
            ],
            "start_boundary": {"boundary_type": "CLOSED_POLE"},
            "end_boundary": {"boundary_type": "CLOSED_POLE"},
        }
        target["radial_profile"]["sha256"] = canonical_hash(
            target["radial_profile"], CanonicalProfile.SURFACE_OF_REVOLUTION
        )
    with pytest.raises(AnalyticTargetError) as raised:
        _admit(design)
    assert raised.value.status == "NOT_APPLICABLE"


def test_existing_radial_profile_without_axial_signs_fails_closed() -> None:
    design, _ = resolved_artifacts()
    design["target_geometry"]["primitive"] = "SURFACE_OF_REVOLUTION"
    # This symmetric radial profile permits axial traces ++,+-,-+,--; r(s) alone
    # contains no sign data selecting one trace.
    design["dimensions"]["measurements"][0]["semantic"] = "LENGTH"
    design["dimensions"]["measurements"][0]["value_mm"] = 10
    design["target_geometry"]["parameters"] = [
        {"parameter": "MERIDIONAL_LENGTH", "measurement_id": "dim_fixture_radius"}
    ]
    design["target_geometry"]["axis_direction"] = [0, 1, 0]
    design["target_geometry"]["radial_profile"] = {
        "canonicalization_profile": "SURFACE_OF_REVOLUTION_PROFILE_CANONICAL_JSON_V1",
        "samples": [
            {"sample_index": 0, "s_mm": 0, "radius_mm": 0},
            {"sample_index": 1, "s_mm": 5, "radius_mm": 3},
            {"sample_index": 2, "s_mm": 10, "radius_mm": 0},
        ],
        "start_boundary": {"boundary_type": "CLOSED_POLE"},
        "end_boundary": {"boundary_type": "CLOSED_POLE"},
    }
    design["target_geometry"]["radial_profile"]["sha256"] = canonical_hash(
        design["target_geometry"]["radial_profile"], CanonicalProfile.SURFACE_OF_REVOLUTION
    )
    with pytest.raises(AnalyticTargetError) as raised:
        _admit(design)
    assert raised.value.status == "NOT_APPLICABLE"


@pytest.mark.parametrize(
    "radius,origin",
    [
        (1.0, [1e308, 1e308, 1e308]),
        (1e308, [1e308, 0.0, 0.0]),
        (1e308, [0.0, 0.0, 0.0]),
    ],
)
def test_overflow_and_binary64_coordinate_collapse_reject_at_admission(
    radius: float, origin: list[float]
) -> None:
    design, _ = resolved_artifacts()
    design["dimensions"]["measurements"][0]["value_mm"] = radius
    design["target_geometry"]["origin_mm"] = origin
    with pytest.raises(AnalyticTargetError):
        _admit(design)


def test_subnormal_radius_is_admitted_when_cardinal_points_remain_distinct() -> None:
    design, _ = resolved_artifacts()
    design["dimensions"]["measurements"][0]["value_mm"] = 5e-324
    target = _admit(design)
    assert target.equatorial_radius_mm == 5e-324


def test_valid_mesh_target_is_not_applicable_without_primitive_access() -> None:
    design, _ = resolved_artifacts()
    design["target_geometry"] = {
        "geometry_type": "MESH_3D",
        "artifact": {
            "artifact_id": "asset_mesh",
            "uri": "mesh.json",
            "sha256": "0" * 64,
            "media_type": "application/json",
        },
        "coordinate_frame": {
            "coordinate_frame_id": "frame_fixture_target",
            "handedness": "RIGHT_HANDED",
            "length_unit": "MILLIMETER",
            "up_axis": "POSITIVE_Y",
            "front_axis": "POSITIVE_Z",
        },
        "preflight_profile_id": "V0_AMIGURUMI_CLOSED_SURFACE_V1",
        "preflight_numerical_profile_id": "v0_num_mesh_binary64_v1",
        "topology_expectation": {
            "expected_connected_components": 1,
            "boundary_policy": "FORBIDDEN",
            "expected_boundary_components": 0,
            "orientability": "ORIENTABLE",
            "manifold_policy": "TWO_MANIFOLD",
            "self_intersection_policy": "FORBID",
            "inter_component_contact_policy": "FORBID",
        },
    }
    with pytest.raises(AnalyticTargetError) as raised:
        _admit(design)
    assert raised.value.status == "NOT_APPLICABLE"


@pytest.mark.parametrize(
    "rings,sectors",
    [(True, 8), (1, 8), (257, 8), (4, 3), (4, 257)],
)
def test_sampling_budget_and_integer_types_fail_closed(rings: int, sectors: int) -> None:
    design, _ = resolved_artifacts()
    target = _admit(design)
    with pytest.raises(AnalyticTargetError):
        target.sample(ring_count=rings, sector_count=sectors)


@given(
    radius=st.floats(min_value=0.01, max_value=1e100, allow_nan=False, allow_infinity=False),
    rings=st.integers(min_value=2, max_value=16).filter(lambda value: value % 2 == 0),
    sectors=st.integers(min_value=4, max_value=32).filter(lambda value: value % 4 == 0),
)
def test_bounded_sphere_samples_lie_on_implicit_surface(
    radius: float, rings: int, sectors: int
) -> None:
    design, _ = resolved_artifacts()
    design["dimensions"]["measurements"][0]["value_mm"] = radius
    target = _admit(design)
    sample = target.sample(ring_count=rings, sector_count=sectors)
    for point in sample.points_mm:
        norm_squared = sum((point[index] / radius) ** 2 for index in range(3))
        assert isclose(norm_squared, 1.0, rel_tol=2e-14, abs_tol=2e-14)
