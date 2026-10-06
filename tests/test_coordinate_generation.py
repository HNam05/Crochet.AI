"""Producer integration for explicit-coordinate meridian sampling."""

from __future__ import annotations

from copy import deepcopy
from fractions import Fraction

import pytest
from test_analytic_solver import PROVENANCE, config
from test_coordinate_target_adversarial import explicit_design

from crochet_ai.analytic_geometry import MeridianNumerics, decode_meridian
from crochet_ai.analytic_solver import generate_analytic
from crochet_ai.solver_types import GenerationError, GenerationStatus
from crochet_ai.validation import SemanticValidator


def _decode(points, numerics: MeridianNumerics | None = None):
    design, material = explicit_design(points)
    validator = SemanticValidator(material_profiles={material["profile_id"]: material})
    return decode_meridian(
        design, numerics or MeridianNumerics(0.05, 1e-8, 10000, 1e-9), validator=validator
    )


def test_three_four_five_and_exact_boundaries_sample_declared_coordinates() -> None:
    meridian = _decode([(0, 0), (3, 0), (0, 4)])
    assert meridian.length_mm == 8
    assert meridian.exact_arithmetic_arc_error_bound_mm == 0
    start = meridian.sample(Fraction(0))
    knot = meridian.sample(Fraction(3, 8))
    end = meridian.sample(Fraction(1))
    assert (start.s_mm, start.radius_mm, start.axial_mm) == (0, 0, 0)
    assert (knot.s_mm, knot.radius_mm, knot.axial_mm) == (3, 3, 0)
    assert (end.s_mm, end.radius_mm, end.axial_mm) == (8, 0, 4)


def test_signed_nonmonotone_axial_samples_keep_order_and_values() -> None:
    meridian = _decode([(0, -2), (4, -4), (4, 2), (2, 0), (0, 1)])
    assert meridian.sample(Fraction(0)).axial_mm == -2
    assert meridian.sample(Fraction(1)).axial_mm == 1
    middle = meridian.sample(Fraction(1, 2))
    assert middle.s_mm == pytest.approx(meridian.length_mm / 2)
    assert -4 < middle.axial_mm < 2


def test_sampler_returns_bounded_failures_without_thin_neck_clamping() -> None:
    with pytest.raises(GenerationError) as budget:
        _decode(
            [(0, 0), (4, 0), (4, 6), (0, 6)],
            MeridianNumerics(0.05, 1e-8, 2, 1e-9),
        )
    assert budget.value.status is GenerationStatus.SEARCH_BUDGET_EXHAUSTED
    with pytest.raises(GenerationError) as thin:
        _decode([(0, 0), (4, 0), (1e-9, 3), (0, 4)])
    assert thin.value.status is GenerationStatus.NOT_APPLICABLE


def test_explicit_generation_is_deterministic_complete_and_records_axial_samples() -> None:
    design, material = explicit_design([(0, 0), (4, 0), (4, 6), (0, 6)])
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    design["solver_options"]["max_candidate_evaluations"] = 2
    untouched = deepcopy(design), deepcopy(material)

    first = generate_analytic(design, material, config(), PROVENANCE)
    second = generate_analytic(design, material, config(), PROVENANCE)
    assert first.status is GenerationStatus.CANDIDATES_EMITTED, first.reason
    assert second.status is first.status
    assert first.search_trace is not None and second.search_trace is not None
    assert first.search_trace.payload_bytes == second.search_trace.payload_bytes
    assert [item.crochet_ir.to_dict() for item in first.candidates] == [
        item.crochet_ir.to_dict() for item in second.candidates
    ]
    trace_sample = first.search_trace.to_dict()["hypotheses"][0]["samples"][0]
    assert set(trace_sample) == {"s_mm", "radius_mm", "axial_mm"}
    assert first.candidates
    parameters = first.candidates[0].crochet_ir.to_dict()["provenance"]["solver_parameters"]
    params = {item["name"]: item["value"] for item in parameters}
    assert params["solver.coordinate_sampler_version"] == "EXPLICIT_COORDINATE_MERIDIAN_V1"
    assert params["solver.coordinate_sqrt_bracket_max_steps"] == 2
    assert (design, material) == untouched

    validator = SemanticValidator(
        material_profiles={material["profile_id"]: material},
        design_specs={design["design_spec_id"]: design},
    )
    for candidate in first.candidates:
        assert validator.validate_crochet_ir(candidate.crochet_ir.to_dict()).ok
