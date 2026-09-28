from fractions import Fraction
from math import cos, hypot, pi, sin

import pytest
from conftest import resolved_artifacts

from crochet_ai.analytic_geometry import MeridianNumerics, decode_meridian
from crochet_ai.canonical import CanonicalProfile, canonical_hash
from crochet_ai.solver_types import GenerationError, GenerationStatus
from crochet_ai.validation import SemanticValidator


def _target(primitive: str, parameters: dict[str, float]):
    design, material = resolved_artifacts()
    design["target_geometry"]["primitive"] = primitive
    design["dimensions"]["measurements"] = [
        {
            "measurement_id": f"dim_{name.lower()}",
            "semantic": "RADIUS" if "RADIUS" in name else "LENGTH",
            "label": name,
            "value_mm": value,
            "tolerance_mm": 0,
        }
        for name, value in parameters.items()
    ]
    design["target_geometry"]["parameters"] = [
        {"parameter": name, "measurement_id": f"dim_{name.lower()}"} for name in parameters
    ]
    validator = SemanticValidator(material_profiles={material["profile_id"]: material})
    return design, validator


def test_sphere_and_cone_use_meridional_not_axial_distance() -> None:
    profile = MeridianNumerics(0.05, 1e-8, 10000, 1e-9)
    design, validator = _target("SPHERE", {"RADIUS": 20})
    sphere = decode_meridian(design, profile, validator=validator)
    assert sphere.length_mm == 20 * pi
    assert sphere.sample(Fraction(0)).radius_mm == sphere.sample(Fraction(1)).radius_mm == 0
    assert sphere.sample(Fraction(1, 2)).radius_mm == 20
    for i in range(1, 20):
        assert (
            sphere.sample(Fraction(i, 20)).radius_mm
            == sphere.sample(Fraction(20 - i, 20)).radius_mm
        )
    design, validator = _target("CONE", {"BASE_RADIUS": 3, "AXIAL_LENGTH": 4})
    cone = decode_meridian(design, profile, validator=validator)
    assert cone.length_mm == 5
    assert cone.sample(Fraction(1, 2)).radius_mm == 1.5


@pytest.mark.parametrize("a,b", [(12.0, 3.0), (3.0, 12.0), (7.0, 7.0)])
def test_ellipse_independent_quadrature_and_scale(a: float, b: float) -> None:
    design, validator = _target("ELLIPSOID", {"EQUATORIAL_RADIUS": a, "POLAR_RADIUS": b})
    meridian = decode_meridian(
        design, MeridianNumerics(0.01, 1e-8, 100000, 1e-9), validator=validator
    )
    # Separate midpoint quadrature is only a numerical cross-check, not a golden.
    panels = 20000
    expected = (
        sum(
            hypot(a * cos((i + 0.5) * pi / panels), b * sin((i + 0.5) * pi / panels))
            for i in range(panels)
        )
        * pi
        / panels
    )
    assert abs(meridian.length_mm - expected) <= 0.01
    assert meridian.sample(Fraction(1, 2)).radius_mm == a
    for i in range(1, 20):
        assert (
            meridian.sample(Fraction(i, 20)).radius_mm
            == meridian.sample(Fraction(20 - i, 20)).radius_mm
        )
    design, validator = _target("ELLIPSOID", {"EQUATORIAL_RADIUS": a * 8, "POLAR_RADIUS": b * 8})
    scaled = decode_meridian(
        design, MeridianNumerics(0.08, 8e-8, 100000, 8e-9), validator=validator
    )
    assert scaled.arc_panels == meridian.arc_panels
    assert scaled.length_mm == meridian.length_mm * 8
    assert scaled.sample(Fraction(1, 3)).radius_mm == meridian.sample(Fraction(1, 3)).radius_mm * 8


def test_ellipse_budget_is_not_convergence() -> None:
    design, validator = _target("ELLIPSOID", {"EQUATORIAL_RADIUS": 12, "POLAR_RADIUS": 3})
    with pytest.raises(GenerationError) as error:
        decode_meridian(design, MeridianNumerics(0.001, 1e-8, 10, 1e-9), validator=validator)
    assert error.value.status == GenerationStatus.SEARCH_BUDGET_EXHAUSTED


def _radial_target(radii: tuple[float, ...]):
    design, validator = _target(
        "SURFACE_OF_REVOLUTION", {"MERIDIONAL_LENGTH": 4 * (len(radii) - 1)}
    )
    profile = {
        "canonicalization_profile": "SURFACE_OF_REVOLUTION_PROFILE_CANONICAL_JSON_V1",
        "samples": [
            {"sample_index": i, "s_mm": i * 4, "radius_mm": r} for i, r in enumerate(radii)
        ],
        "start_boundary": {"boundary_type": "CLOSED_POLE"},
        "end_boundary": {"boundary_type": "CLOSED_POLE"},
    }
    profile["sha256"] = canonical_hash(profile, CanonicalProfile.SURFACE_OF_REVOLUTION)
    design["target_geometry"]["axis_direction"] = [0, 0, 1]
    design["target_geometry"]["radial_profile"] = profile
    return design, validator


@pytest.mark.parametrize(
    "radii,reason",
    [
        ((0, 5, 0), "impossible_arc_slope"),
        ((1, 3, 0), "nonzero_pole"),
        ((0, 2, 0, 2, 0), "interior_pole"),
        ((0, 0, 0), "interior_pole"),
    ],
)
def test_radial_profile_defects_are_not_repaired(radii, reason: str) -> None:
    design, validator = _radial_target(radii)
    with pytest.raises(GenerationError, match=reason):
        decode_meridian(design, MeridianNumerics(0.01, 1e-8, 1000, 1e-9), validator=validator)


def test_radial_profile_is_interpolated_in_arc_length_without_invented_axis_shape() -> None:
    design, validator = _radial_target((0, 3, 0))
    meridian = decode_meridian(
        design, MeridianNumerics(0.01, 1e-8, 1000, 1e-9), validator=validator
    )
    assert meridian.sample(Fraction(1, 4)).radius_mm == 1.5
    assert meridian.sample(Fraction(3, 4)).s_mm == 6


@pytest.mark.parametrize("a,b", [(12, 3), (3, 12)])
def test_ellipse_inverse_arc_has_independent_partial_integral_check(a: float, b: float) -> None:
    from math import asin

    design, validator = _target("ELLIPSOID", {"EQUATORIAL_RADIUS": a, "POLAR_RADIUS": b})
    tolerance = 0.01
    meridian = decode_meridian(
        design, MeridianNumerics(tolerance, 1e-8, 100000, 1e-9), validator=validator
    )
    for fraction in (Fraction(1, 100), Fraction(1, 5), Fraction(49, 100)):
        point = meridian.sample(fraction)
        angle = asin(point.radius_mm / a)
        h = angle / 10000
        actual_arc = h * sum(
            hypot(a * cos((i + 0.5) * h), b * sin((i + 0.5) * h)) for i in range(10000)
        )
        assert abs(actual_arc - point.s_mm) <= tolerance
