"""Closed request assembly for the local human-test prototype."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
from math import pi, sqrt
from typing import Any

from .analytic_counts import CountSearchBudget
from .analytic_geometry import MeridianNumerics, decode_meridian
from .analytic_placement import PlacementBudget
from .analytic_solver import AnalyticRunConfig
from .prototype_shapes import SHAPE_IDS, coordinate_profile
from .validation import SemanticValidator

PROTOTYPE_VERSION = "1.0.0"
REQUEST_FIELDS = {
    "prototype_version",
    "shape",
    "diameter_mm",
    "height_mm",
    "stitches_per_100mm",
    "courses_per_100mm",
    "hook_diameter_mm",
    "yarn_label",
    "color_hex",
    "uncertainty_percent",
}


def _number(value: object, low: float, high: float, field: str) -> float:
    if type(value) is int:
        numeric: int | float = value
    elif type(value) is float:
        numeric = value
    else:
        raise ValueError(f"request.{field}")
    if not low <= numeric <= high:
        raise ValueError(f"request.{field}")
    return float(numeric)


def assemble_request(
    value: object,
    *,
    software_commit: str,
    working_tree_dirty: bool,
) -> tuple[dict[str, Any], dict[str, Any], AnalyticRunConfig]:
    if not isinstance(value, dict) or set(value) != REQUEST_FIELDS:
        raise ValueError("request.fields")
    if value["prototype_version"] != PROTOTYPE_VERSION:
        raise ValueError("request.prototype_version")
    shape = value["shape"]
    if not isinstance(shape, str) or shape not in SHAPE_IDS:
        raise ValueError("request.shape")
    diameter = _number(value["diameter_mm"], 20, 100, "diameter_mm")
    height = _number(value["height_mm"], 20, 100, "height_mm")
    if shape == "sphere" and height != diameter:
        raise ValueError("request.sphere_height")
    if shape == "capsule" and height < diameter:
        raise ValueError("request.capsule_height")
    stitches = value["stitches_per_100mm"]
    courses = value["courses_per_100mm"]
    if type(stitches) is not int or not 5 <= stitches <= 60:
        raise ValueError("request.stitches_per_100mm")
    if type(courses) is not int or not 5 <= courses <= 60:
        raise ValueError("request.courses_per_100mm")
    hook = _number(value["hook_diameter_mm"], 0.5, 12, "hook_diameter_mm")
    uncertainty = _number(value["uncertainty_percent"], 1, 50, "uncertainty_percent")
    yarn = value["yarn_label"]
    color = value["color_hex"]
    if not isinstance(yarn, str) or not 1 <= len(yarn) <= 120:
        raise ValueError("request.yarn_label")
    if not isinstance(color, str) or re.fullmatch(r"#[0-9A-Fa-f]{6}", color) is None:
        raise ValueError("request.color_hex")

    material: dict[str, Any] = {
        "schema_version": "1.0.0",
        "profile_id": "mp_local_prototype",
        "revision": 1,
        "yarn": {"description": yarn},
        "hook_diameter_mm": hook,
        "calibration_responses": [
            {
                "response_id": "mr_user_entered_gauge",
                "measurement_conditions": {
                    "canonical_stitch_type": "SINGLE_CROCHET",
                    "course_mode": "CYCLIC",
                    "tension_profile_id": "tension_user_entered",
                    "fabric_state": "RELAXED_UNSTUFFED",
                },
                "observations": [
                    {
                        "specimen_id": "user_entered_observation",
                        "stitch_span_count": stitches,
                        "stitch_span_length_mm": 100,
                        "course_span_count": courses,
                        "course_span_length_mm": 100,
                    }
                ],
                "effective_gauge": {
                    "effective_stitch_pitch_mm": 100 / stitches,
                    "effective_course_pitch_mm": 100 / courses,
                },
                "uncertainty": {
                    "stitch_pitch_standard_uncertainty_mm": (100 / stitches) * uncertainty / 100,
                    "course_pitch_standard_uncertainty_mm": (100 / courses) * uncertainty / 100,
                    "basis": "DOCUMENTED_ENGINEERING_BOUND",
                    "assumptions": ("User-entered relative bound; not a calibration result."),
                },
            }
        ],
        "canonicalization": {
            "profile": "MATERIAL_PROFILE_CANONICAL_JSON_V1",
            "hash_algorithm": "SHA-256",
        },
        "provenance": {
            "created_at": "2026-10-04T00:00:00Z",
            "measurement_protocol_id": "local_user_entry_v1",
            "source_record_ids": ["local_user_entry"],
            "software_commit": software_commit,
            "working_tree_dirty": working_tree_dirty,
        },
    }
    r = diameter / 2
    h = height / 2
    profile: dict[str, Any] | None = None
    profile_provenance: dict[str, Any] | None = None
    if shape in {"sphere", "ellipsoid"}:
        primitive = "SPHERE" if shape == "sphere" else "ELLIPSOID"
    else:
        primitive = "SURFACE_OF_REVOLUTION"
        profile, profile_provenance = coordinate_profile(shape, diameter, height)
    measurements = [
        {
            "measurement_id": "dim_radius",
            "semantic": "RADIUS",
            "label": "Equatorial radius",
            "value_mm": r,
            "tolerance_mm": 1,
        }
    ]
    parameters = [
        {
            "parameter": "RADIUS" if shape == "sphere" else "EQUATORIAL_RADIUS",
            "measurement_id": "dim_radius",
        }
    ]
    if shape == "ellipsoid":
        measurements.append(
            {
                "measurement_id": "dim_polar_radius",
                "semantic": "RADIUS",
                "label": "Polar radius",
                "value_mm": h,
                "tolerance_mm": 1,
            }
        )
        parameters.append({"parameter": "POLAR_RADIUS", "measurement_id": "dim_polar_radius"})
    elif profile is not None:
        measurements.append(
            {
                "measurement_id": "dim_axial_length",
                "semantic": "LENGTH",
                "label": "Axial extent",
                "value_mm": height,
                "tolerance_mm": 0,
            }
        )
        parameters = [{"parameter": "AXIAL_LENGTH", "measurement_id": "dim_axial_length"}]
    design: dict[str, Any] = {
        "schema_version": "1.2.0" if profile is not None else "1.0.0",
        "design_spec_id": "ds_local_prototype",
        "project_type": "AMIGURUMI_3D",
        "dimensions": {"length_unit": "MILLIMETER", "measurements": measurements},
        "target_geometry": {
            "geometry_type": "ANALYTIC_SHAPE",
            "primitive": primitive,
            "parameters": parameters,
            "origin_mm": [0, 0, 0],
            "coordinate_frame": {
                "coordinate_frame_id": "frame_target",
                "handedness": "RIGHT_HANDED",
                "length_unit": "MILLIMETER",
                "up_axis": "POSITIVE_Y",
                "front_axis": "POSITIVE_Z",
            },
        },
        "symmetries": [],
        "landmarks": [],
        "material_profile": {"binding_type": "INLINE", "profile": deepcopy(material)},
        "construction_constraints": {
            "priority_policy": "GEOMETRY_GATED_SEAMLESS_LEXICOGRAPHIC_V1",
            "hard_geometry_gate_required": True,
            "maximum_sewn_seams": 0,
            "maximum_yarn_cuts": 0,
            "maximum_reattachments": 0,
            "allowed_join_methods": ["CROCHETED"],
            "intentional_openings": [],
        },
        "colors": [
            {"color_id": "color_main", "label": "User color", "srgb_hex": color, "roles": ["main"]}
        ],
        "difficulty_constraints": {
            "maximum_skill_level": "BEGINNER",
            "allowed_stitch_types": ["SINGLE_CROCHET"],
            "allowed_shaping": ["INCREASE", "DECREASE"],
            "allowed_construction_operations": ["MAGIC_RING", "CLOSE"],
            "maximum_simultaneously_active_frontiers": 1,
            "allow_unsupported_techniques": False,
        },
        "solver_options": {
            "allowed_solver_families": ["ANALYTIC"],
            "solver_family_preference": ["ANALYTIC"],
            "random_seed": 0,
            "max_candidate_evaluations": 1,
            "max_backtracks": 0,
            "max_beam_width": 1,
            "parameter_profile_id": "solver_params_prototype_analytic_v1",
        },
        "verification_requirements": {
            "threshold_profile_id": "thresholds_prototype_not_verified",
            "required_gates": ["V0", "V1", "V2", "V3", "V4", "V5", "V6", "V7", "V10"],
            "required_geometry_metrics": ["SYMMETRIC_CHAMFER", "TOPOLOGY"],
            "require_export_round_trip": False,
            "require_material_robustness": False,
            "require_collision_check": True,
            "minimum_physical_validation": "UNTESTED",
        },
        "domain_constraints": {
            "domain": "AMIGURUMI_3D",
            "stuffing_level": "NONE",
            "surface_mode": "CLOSED",
        },
        "interpretation_provenance": {
            "authoring_mode": "MANUAL",
            "producer": {"name": "local-prototype", "version": PROTOTYPE_VERSION},
            "source_artifacts": [],
            "assumptions": [
                {
                    "assumption_id": "assumption_user_measurements",
                    "statement": (
                        "Gauge uses user-entered 100 mm spans; uncertainty remains a "
                        "conservative engineering hypothesis, not a calibration result. "
                        "The 2026-10-04 timestamp is this deterministic profile revision date, "
                        "not a measurement time; checkout cleanliness is unconfirmed and "
                        "is conservatively recorded as dirty."
                    ),
                    "disposition": "EXPLICIT_PROFILE_DEFAULT",
                }
            ],
            "unresolved_ambiguities": [],
        },
    }
    if profile is not None:
        design["target_geometry"]["axis_direction"] = [0, 1, 0]
        design["target_geometry"]["radial_profile"] = profile
        assert profile_provenance is not None
        design["interpretation_provenance"]["assumptions"].append(
            {
                "assumption_id": "assumption_versioned_shape_silhouette",
                "statement": (
                    f"Target uses {profile_provenance['profile_design_id']}; "
                    "its ordered piecewise-linear profile defines the target with "
                    f"{profile_provenance['profile_resolution_sample_count']} samples, "
                    f"axial extent {profile_provenance['profile_axial_extent_mm']} mm, "
                    f"and maximum radius {profile_provenance['profile_max_radius_mm']} mm. "
                    "Resolution records sample density only; it is not a certified geometric "
                    "approximation bound."
                ),
                "disposition": "EXPLICIT_PROFILE_DEFAULT",
            }
        )
    run = default_run_config()
    polar = h if shape == "ellipsoid" else r
    # One deterministic meridian/course-pitch proposal avoids publishing a partial
    # candidate batch. It is a construction hypothesis, not target acceptance.
    if profile is not None:
        meridian = decode_meridian(
            design,
            run.numerics,
            validator=SemanticValidator(
                material_profiles={(material["profile_id"], material["revision"]): material},
                design_specs={design["design_spec_id"]: design},
            ),
        )
        meridian_length = meridian.length_mm
    else:
        mean_radius = (r + polar) / 2
        meridian_length = (
            pi
            * mean_radius
            * (
                1
                + 3
                * ((r - polar) / (r + polar)) ** 2
                / (10 + sqrt(4 - 3 * ((r - polar) / (r + polar)) ** 2))
            )
        )
    course_count = round(meridian_length / (100 / courses))
    if not 3 <= course_count <= 32:
        raise ValueError("request.course_count_unsupported")
    run = replace(run, min_courses=course_count, max_courses=course_count, max_course_hypotheses=1)
    return design, material, run


def default_run_config() -> AnalyticRunConfig:
    return AnalyticRunConfig(
        "solver_params_prototype_analytic_v1",
        "tension_user_entered",
        "RELAXED_UNSTUFFED",
        MeridianNumerics(0.05, 1e-8, 10000, 1e-9),
        CountSearchBudget(64, 64, 64, 100000),
        PlacementBudget(128, 100000, 1000000),
        3,
        32,
        1,
        4,
        2,
        32,
        6,
        10,
        6,
        6,
        12,
        Fraction(1, 12),
        1,
        10000,
    )
