"""Targeted contract checks for explicit meridian coordinate admission."""

from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from hashlib import sha256

import pytest
import rfc8785
from conftest import resolved_artifacts

from crochet_ai.analytic_coordinate_target import AnalyticCoordinateTarget
from crochet_ai.analytic_geometry import MeridianNumerics, decode_meridian
from crochet_ai.analytic_target import AnalyticTargetError, admit_analytic_target
from crochet_ai.canonical import CanonicalProfile, canonical_hash
from crochet_ai.schema import validate_schema
from crochet_ai.validation import SemanticValidator

PROFILE_ID = "SURFACE_OF_REVOLUTION_COORDINATE_PROFILE_CANONICAL_JSON_V1"


def _design(points: list[tuple[float, float]]) -> tuple[dict, dict]:
    design, material = resolved_artifacts()
    design["schema_version"] = "1.2.0"
    measurement = design["dimensions"]["measurements"][0]
    measurement.update(
        semantic="LENGTH",
        label="Axial extent",
        value_mm=max(axial for _, axial in points) - min(axial for _, axial in points),
        tolerance_mm=0,
    )
    frame = design["target_geometry"]["coordinate_frame"]
    axis_by_name = {
        "POSITIVE_X": [1.0, 0.0, 0.0],
        "NEGATIVE_X": [-1.0, 0.0, 0.0],
        "POSITIVE_Y": [0.0, 1.0, 0.0],
        "NEGATIVE_Y": [0.0, -1.0, 0.0],
        "POSITIVE_Z": [0.0, 0.0, 1.0],
        "NEGATIVE_Z": [0.0, 0.0, -1.0],
    }
    profile = {
        "canonicalization_profile": PROFILE_ID,
        "samples": [
            {"sample_index": i, "radius_mm": radius, "axial_mm": axial}
            for i, (radius, axial) in enumerate(points)
        ],
        "start_boundary": {"boundary_type": "CLOSED_POLE"},
        "end_boundary": {"boundary_type": "CLOSED_POLE"},
    }
    profile["sha256"] = sha256(
        b"Crochet.AI\x00" + PROFILE_ID.encode("ascii") + b"\x00" + rfc8785.dumps(profile)
    ).hexdigest()
    design["target_geometry"].update(
        primitive="SURFACE_OF_REVOLUTION",
        parameters=[{"parameter": "AXIAL_LENGTH", "measurement_id": measurement["measurement_id"]}],
        axis_direction=axis_by_name[frame["up_axis"]],
        radial_profile=profile,
    )
    return design, material


def _admit(design: dict, material: dict) -> AnalyticCoordinateTarget:
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={(material["profile_id"], material["revision"]): material},
    )
    result = admit_analytic_target(design, validator)
    assert isinstance(result, AnalyticCoordinateTarget)
    return result


def test_coordinate_profile_schema_hash_extent_and_immutable_target_metadata() -> None:
    design, material = _design([(0, 1), (4, 0), (4, 6), (0, 5)])
    assert validate_schema("design_spec", design).ok
    target = _admit(design, material)
    assert target.characteristic_length_mm == 8
    assert target.segment_pair_checks == 3
    before = target.to_dict()
    digest = before.pop("sha256")
    assert (
        digest
        == sha256(
            b"Crochet.AI\x00ANALYTIC_COORDINATE_TARGET_V1\x00" + rfc8785.dumps(before)
        ).hexdigest()
    )
    assert target.profile_sha256 == design["target_geometry"]["radial_profile"]["sha256"]
    target_dict = target.to_dict()
    target_dict["coordinates_mm"][0][0] = 10
    assert target.to_dict()["coordinates_mm"][0][0] == 0


@pytest.mark.parametrize(
    "points",
    [
        [(0, 0), (4, 4), (1, 4), (4, 1), (0, 5)],
        [(0, 0), (4, 0), (2, 0), (2, 4), (0, 5)],
    ],
)
def test_exact_crossings_and_adjacent_backtracking_fail_closed(
    points: list[tuple[float, float]],
) -> None:
    design, material = _design(points)
    with pytest.raises(AnalyticTargetError) as error:
        _admit(design, material)
    assert error.value.status == "INVALID_SOLVER_INPUT"


def test_axial_extent_uses_full_coordinate_range_and_rejects_mismatch() -> None:
    design, material = _design([(0, 1), (4, 0), (4, 6), (0, 5)])
    design["dimensions"]["measurements"][0]["value_mm"] = 5
    with pytest.raises(AnalyticTargetError):
        _admit(design, material)


def test_legacy_profile_canonical_hash_profile_remains_available() -> None:
    payload = {"canonicalization_profile": "legacy", "samples": []}
    assert canonical_hash(payload, CanonicalProfile.SURFACE_OF_REVOLUTION)
    assert canonical_hash(payload, CanonicalProfile.SURFACE_OF_REVOLUTION_COORDINATES)
    assert canonical_hash(payload, CanonicalProfile.SURFACE_OF_REVOLUTION) != canonical_hash(
        payload, CanonicalProfile.SURFACE_OF_REVOLUTION_COORDINATES
    )


def test_admission_does_not_mutate_input() -> None:
    design, material = _design([(0, 0), (4, 0), (4, 4), (0, 4)])
    snapshot = deepcopy(design)
    _admit(design, material)
    assert design == snapshot


def test_profile_discriminator_and_sample_shape_are_bound_by_schema() -> None:
    design, _ = _design([(0, 0), (4, 0), (4, 4), (0, 4)])
    profile = design["target_geometry"]["radial_profile"]
    profile["samples"][1] = {"sample_index": 1, "s_mm": 1, "radius_mm": 4}
    assert not validate_schema("design_spec", design).ok


def test_schema_1_1_does_not_admit_the_additive_coordinate_profile() -> None:
    design, _ = _design([(0, 0), (4, 0), (4, 4), (0, 4)])
    design["schema_version"] = "1.1.0"
    assert not validate_schema("design_spec", design).ok


def test_coordinate_profile_has_a_bounded_meridian_sampler() -> None:
    design, material = _design([(0, 0), (4, 0), (4, 4), (0, 4)])
    validator = SemanticValidator(
        material_profiles={(material["profile_id"], material["revision"]): material}
    )
    meridian = decode_meridian(
        design,
        MeridianNumerics(0.05, 1e-8, 10000, 1e-9),
        validator=validator,
    )
    assert meridian.length_mm == 12
    point = meridian.sample(Fraction(1, 2))
    assert point.radius_mm == 4
    assert point.axial_mm == 2


def test_axial_extent_overflow_is_reported_as_structured_semantic_error() -> None:
    design, _ = _design([(0, -1e308), (4, -1e308), (4, 1e308), (0, 1e308)])
    design["dimensions"]["measurements"][0]["value_mm"] = 1
    report = SemanticValidator().validate_design_spec(design)
    assert not report.ok
    extent_diagnostic = next(
        item
        for item in report.diagnostics
        if item.message_key == "design.coordinate_profile_extent"
    )
    assert extent_diagnostic.expected == "finite positive axial extent"
