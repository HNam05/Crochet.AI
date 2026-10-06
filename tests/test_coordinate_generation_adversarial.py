"""Independent exact and high-precision oracles for coordinate generation."""

import json
from copy import deepcopy
from dataclasses import asdict, replace
from decimal import Decimal, localcontext
from fractions import Fraction
from itertools import pairwise

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from test_analytic_solver import PROVENANCE, config
from test_coordinate_target_adversarial import explicit_design

from crochet_ai.analytic_geometry import MeridianNumerics, decode_meridian
from crochet_ai.analytic_solver import generate_analytic
from crochet_ai.backend_api import BackendAPI
from crochet_ai.job_store import JobStore
from crochet_ai.job_worker import execute_one_isolated
from crochet_ai.solver_types import GenerationError, GenerationStatus
from crochet_ai.validation import SemanticValidator

NUMERICS = MeridianNumerics(0.05, 1e-8, 10000, 1e-9)


def decode(points, numerics=NUMERICS):
    design, material = explicit_design(points)
    validator = SemanticValidator(material_profiles={material["profile_id"]: material})
    return decode_meridian(design, numerics, validator=validator)


@given(
    radius=st.integers(1, 16),
    height=st.integers(1, 16),
    numerator=st.integers(0, 100),
    offset=st.integers(-1000, 1000),
)
@settings(max_examples=40, deadline=None, derandomize=True)
def test_closed_cylinder_matches_exact_hand_piecewise_formula(radius, height, numerator, offset):
    meridian = decode(
        [(0, offset), (radius, offset), (radius, offset + height), (0, offset + height)]
    )
    # Orthogonal caps and side have exact lengths: no numerical square-root oracle.
    arc = Fraction(numerator, 100) * (2 * radius + height)
    if arc <= radius:
        expected_r, expected_z = arc, Fraction(offset)
    elif arc <= radius + height:
        expected_r, expected_z = Fraction(radius), offset + arc - radius
    else:
        expected_r, expected_z = 2 * radius + height - arc, Fraction(offset + height)
    point = meridian.sample(Fraction(numerator, 100))
    assert meridian.length_mm == 2 * radius + height
    assert abs(Fraction(point.s_mm) - arc) <= Fraction(NUMERICS.roundoff_allowance_mm)
    assert abs(Fraction(point.radius_mm) - expected_r) <= Fraction(NUMERICS.roundoff_allowance_mm)
    assert abs(Fraction(point.axial_mm) - expected_z) <= Fraction(NUMERICS.roundoff_allowance_mm)


@pytest.mark.parametrize("fraction", [Fraction(0), Fraction(3, 8), Fraction(1, 2), Fraction(1)])
def test_three_four_five_cone_exact_total_and_knot(fraction):
    meridian = decode([(0, 0), (3, 0), (0, 4)])
    assert meridian.length_mm == 8
    point = meridian.sample(fraction)
    if fraction <= Fraction(3, 8):
        expected_r, expected_z = 8 * fraction, 0
    else:
        expected_r = Fraction(3) * (8 - 8 * fraction) / 5
        expected_z = Fraction(4) * (8 * fraction - 3) / 5
    assert point.radius_mm == pytest.approx(float(expected_r), abs=1e-8)
    assert point.axial_mm == pytest.approx(float(expected_z), abs=1e-8)


def decimal_point(points, fraction):
    """Different arithmetic implementation: Decimal square roots, linear scan."""
    with localcontext() as context:
        context.prec = 100
        vertices = [(Decimal.from_float(float(r)), Decimal.from_float(float(z))) for r, z in points]
        lengths = [((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2).sqrt()
                   for a, b in pairwise(vertices)]
        total = sum(lengths)
        arc = Decimal(fraction.numerator) / Decimal(fraction.denominator) * total
        remaining = arc
        for index, length in enumerate(lengths):
            if remaining <= length or index == len(lengths) - 1:
                weight = remaining / length
                a, b = vertices[index], vertices[index + 1]
                return total, a[0] + weight * (b[0] - a[0]), a[1] + weight * (b[1] - a[1])
            remaining -= length
    raise AssertionError("Independent decimal oracle did not locate segment")


@pytest.mark.parametrize(
    "fraction", [Fraction(1, 17), Fraction(1, 3), Fraction(1, 2), Fraction(4, 5)]
)
def test_nonmonotone_meridian_against_independent_decimal_oracle(fraction):
    points = [(0, 1), (4, 0), (4, 6), (2, 4), (0, 5)]
    meridian = decode(points)
    total, radius, axial = decimal_point(points, fraction)
    point = meridian.sample(fraction)
    error = Decimal.from_float(meridian.exact_arithmetic_arc_error_bound_mm)
    allowance = Decimal.from_float(NUMERICS.roundoff_allowance_mm)
    assert abs(Decimal.from_float(meridian.length_mm) - total) <= error + allowance
    # Each coordinate is bounded by path displacement plus its conversion error.
    assert abs(Decimal.from_float(point.radius_mm) - radius) <= 2 * error + allowance
    assert abs(Decimal.from_float(point.axial_mm) - axial) <= 2 * error + allowance


@pytest.mark.parametrize("fraction", [Fraction(0), Fraction(1, 7), Fraction(1, 2), Fraction(1)])
def test_declared_order_reversal_and_axial_reflection_preserve_samples(fraction):
    points = [(0, 1), (4, 0), (4, 6), (2, 4), (0, 5)]
    baseline = decode(points)
    reverse = decode(list(reversed(points)))
    reflected = decode([(r, -z) for r, z in points])
    a = baseline.sample(fraction)
    b = reverse.sample(1 - fraction)
    c = reflected.sample(fraction)
    assert reverse.length_mm == reflected.length_mm == baseline.length_mm
    assert abs(a.radius_mm - b.radius_mm) <= 1e-8
    assert abs(a.axial_mm - b.axial_mm) <= 1e-8
    assert c.radius_mm == a.radius_mm
    assert c.axial_mm == -a.axial_mm


def test_arc_work_budget_is_not_reported_as_no_feasible_pattern():
    points = [(0, 0), (4, 0), (4, 6), (0, 6)]
    with pytest.raises(GenerationError) as error:
        decode(points, replace(NUMERICS, max_arc_panels=2))
    assert error.value.status is GenerationStatus.SEARCH_BUDGET_EXHAUSTED


def test_total_conversion_loss_cannot_hide_short_cap_lengths():
    # The long side is representable, but rounding the complete length loses
    # eight millimetres of caps. Local target admission alone cannot detect this.
    with pytest.raises(GenerationError) as error:
        decode([(0, 0), (4, 0), (4, 1e308), (0, 1e308)])
    assert error.value.status is GenerationStatus.NUMERICAL_FAILURE


def test_sample_coordinate_rounding_is_checked_separately_from_total_length():
    numerics = replace(NUMERICS, roundoff_allowance_mm=1e-30)
    meridian = decode([(0, 0), (3, 0), (0, 4)], numerics)
    # Total length is exactly eight. The one-third sample is not exactly binary64.
    with pytest.raises(GenerationError) as error:
        meridian.sample(Fraction(1, 3))
    assert error.value.status is GenerationStatus.NUMERICAL_FAILURE


def test_untrusted_hypot_estimate_is_rejected_with_bounded_widening(monkeypatch):
    from crochet_ai import analytic_coordinate_meridian as kernel

    original_nextafter = kernel.nextafter
    calls = []

    def counted_nextafter(value, direction):
        calls.append((value, direction))
        return original_nextafter(value, direction)

    monkeypatch.setattr(kernel, "hypot", lambda *_: 1e9)
    monkeypatch.setattr(kernel, "nextafter", counted_nextafter)
    with pytest.raises(GenerationError) as error:
        decode([(0, 0), (3, 0), (0, 4)])
    assert error.value.status is GenerationStatus.NUMERICAL_FAILURE
    assert len(calls) <= 4  # At most two widening steps per side, no unbounded retry.


@pytest.mark.parametrize("axis,up,front", [
    ([1, 0, 0], "POSITIVE_X", "POSITIVE_Y"),
    ([-1, 0, 0], "NEGATIVE_X", "POSITIVE_Y"),
    ([0, 1, 0], "POSITIVE_Y", "POSITIVE_Z"),
    ([0, -1, 0], "NEGATIVE_Y", "POSITIVE_Z"),
    ([0, 0, 1], "POSITIVE_Z", "POSITIVE_X"),
    ([0, 0, -1], "NEGATIVE_Z", "POSITIVE_X"),
])
def test_local_coordinate_sampling_is_invariant_under_admitted_world_frames(axis, up, front):
    points = [(0, 1), (4, 0), (4, 6), (2, 4), (0, 5)]
    design, material = explicit_design(points)
    geometry = design["target_geometry"]
    geometry.update(axis_direction=axis, origin_mm=[10, -20, 30])
    geometry["coordinate_frame"].update(up_axis=up, front_axis=front)
    validator = SemanticValidator(material_profiles={material["profile_id"]: material})
    meridian = decode_meridian(design, NUMERICS, validator=validator)
    assert meridian.sample(Fraction(1, 3)) == decode(points).sample(Fraction(1, 3))


@pytest.mark.parametrize("power", [-10, 0, 10])
def test_binary_scale_covariance_keeps_units_and_numerical_policy(power):
    scale = 2.0 ** power
    points = [(0, 0), (3, 0), (0, 4)]
    numerics = replace(
        NUMERICS,
        arc_length_abs_tolerance_mm=NUMERICS.arc_length_abs_tolerance_mm * scale,
        roundoff_allowance_mm=NUMERICS.roundoff_allowance_mm * scale,
        radius_zero_tolerance_mm=NUMERICS.radius_zero_tolerance_mm * scale,
    )
    base = decode(points)
    scaled = decode([(r * scale, z * scale) for r, z in points], numerics)
    assert scaled.length_mm == base.length_mm * scale
    assert scaled.arc_panels == base.arc_panels
    for fraction in (Fraction(0), Fraction(1, 7), Fraction(3, 8), Fraction(1)):
        first, second = base.sample(fraction), scaled.sample(fraction)
        assert second.s_mm == first.s_mm * scale
        assert second.radius_mm == first.radius_mm * scale
        assert second.axial_mm == first.axial_mm * scale


def test_coordinate_api_generation_is_bound_complete_and_unverified(tmp_path):
    design, material = explicit_design([(0, 0), (4, 0), (4, 6), (0, 6)])
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    design["solver_options"]["max_candidate_evaluations"] = 2
    untouched = deepcopy(design), deepcopy(material)
    batch = generate_analytic(design, material, config(), PROVENANCE)
    assert batch.status is GenerationStatus.CANDIDATES_EMITTED, batch.reason
    assert batch.search_trace is not None
    raw_config = asdict(config())
    raw_config["minimum_shaping_separation_turns"] = "1/12"
    request = {
        "api_version": "1.0.0", "operation": "generate_analytic", "design_spec": design,
        "material_profile": material, "run_config": raw_config,
    }
    response = BackendAPI(PROVENANCE).handle(request)
    assert response["ok"], response
    data = response["data"]
    assert data["generation_status"] == "CANDIDATES_EMITTED"
    assert data["verification_state"] == "NOT_VERIFIED"
    assert data["physical_status"] == "UNTESTED"
    assert data["search_trace_sha256"] == batch.search_trace.sha256
    validator = SemanticValidator(material_profiles={material["profile_id"]: material},
                                  design_specs={design["design_spec_id"]: design})
    for candidate in batch.candidates:
        assert validator.validate_crochet_ir(candidate.crochet_ir.to_dict()).ok
    audit = BackendAPI(PROVENANCE).handle({
        "api_version": "1.0.0", "operation": "inspect_analytic_search_trace",
        "design_spec": design, "material_profile": material, "run_config": raw_config,
        "search_trace": batch.search_trace.to_dict(),
        "candidate_proposals": [candidate.crochet_ir.to_dict() for candidate in batch.candidates],
    })
    assert audit["ok"], audit
    assert audit["data"]["status"] == "INDETERMINATE", audit
    assert "unsupported_target_sampler" in audit["data"]["missing_checks"]
    store = JobStore(tmp_path / "coordinate-generation.sqlite3")
    job_id = store.submit(json.dumps(request), "coordinate-generation")
    assert execute_one_isolated(store, BackendAPI(PROVENANCE), max_wall_seconds=20)
    delivered = JobStore(tmp_path / "coordinate-generation.sqlite3").get(job_id)
    assert delivered["status"] == "SUCCEEDED"
    assert delivered["result"] == response
    assert (design, material) == untouched
