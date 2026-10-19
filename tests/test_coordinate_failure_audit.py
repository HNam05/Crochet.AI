"""Fail-closed reconstruction of post-trace coordinate sampler terminals."""

from copy import deepcopy
from dataclasses import asdict, replace

from hypothesis import given, settings
from hypothesis import strategies as st
from test_analytic_solver import PROVENANCE, config
from test_coordinate_target_adversarial import explicit_design

from crochet_ai.analytic_solver import generate_analytic
from crochet_ai.analytic_trace_audit import inspect_analytic_search_trace
from crochet_ai.solver_types import GenerationStatus
from crochet_ai.validation import SemanticValidator


def _sample_failure(height: int):
    design, material = explicit_design([(0, 0), (3, 0), (3, height), (0, height)])
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    design["solver_options"]["max_candidate_evaluations"] = 2
    run = replace(
        config(),
        min_courses=3,
        max_courses=3,
        numerics=replace(config().numerics, roundoff_allowance_mm=1e-30),
    )
    batch = generate_analytic(design, material, run, PROVENANCE)
    assert batch.status is GenerationStatus.NUMERICAL_FAILURE
    assert batch.search_trace is not None
    validator = SemanticValidator(material_profiles={material["profile_id"]: material})
    run_config = asdict(run)
    run_config["minimum_shaping_separation_turns"] = "1/12"
    return design, material, run_config, batch.search_trace.to_dict(), validator


@settings(max_examples=8, deadline=None)
@given(height=st.sampled_from([4, 5, 7, 8]))
def test_replayed_sample_failure_proves_exact_reached_course(height: int):
    """Invariant: exact independent replay identifies the first failed conversion.

    The generated domain varies an admitted rectangle dimension. The oracle is the
    separately produced structured terminal plus exact Fraction reconstruction;
    minimized examples retain a producer sample-stage NUMERICAL_FAILURE.
    """
    design, material, run_config, trace, validator = _sample_failure(height)
    assert trace["hypotheses"][0]["stage"] == "sample"
    audit = inspect_analytic_search_trace(
        design, material, run_config, trace, [], validator=validator
    )
    assert audit.status == "PASS", (audit.missing_checks, audit.diagnostics)
    assert audit.to_dict()["coordinate_failure"]["hypothesis_index"] == 0
    assert audit.to_dict()["coordinate_failure"]["course_count"] == 3
    assert audit.to_dict()["coordinate_failure"]["sample_index"] < 3
    assert audit.to_dict()["coordinate_failure"]["completed_samples"] == []


def test_forged_failure_reason_and_terminal_are_rejected():
    design, material, run_config, trace, validator = _sample_failure(4)
    for forged_reason in ("meridian.axial_conversion", "meridian.negative_radius"):
        forged = deepcopy(trace)
        forged["hypotheses"][0]["terminal_reason"] = forged_reason
        forged["terminal"]["reason"] = forged_reason
        audit = inspect_analytic_search_trace(
            design, material, run_config, forged, [], validator=validator
        )
        assert audit.status == "FAIL"
        assert audit.to_dict()["coordinate_failure"]["failing_reason"] == "meridian.s_conversion"


def test_producer_circumference_overflow_is_replayed_from_real_trace():
    design, material = explicit_design([(0, 0), (3e307, 0), (3e307, 1e307), (0, 1e307)])
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    design["solver_options"]["max_candidate_evaluations"] = 2
    base = config()
    numerics = replace(
        base.numerics,
        arc_length_abs_tolerance_mm=1e300,
        roundoff_allowance_mm=1e295,
    )
    run = replace(base, numerics=numerics)
    batch = generate_analytic(design, material, run, PROVENANCE)
    assert batch.status is GenerationStatus.NUMERICAL_FAILURE
    assert batch.reason == "solver.circumference"
    assert batch.search_trace is not None
    validator = SemanticValidator(material_profiles={material["profile_id"]: material})
    run_config = asdict(run)
    run_config["minimum_shaping_separation_turns"] = "1/12"
    audit = inspect_analytic_search_trace(
        design, material, run_config, batch.search_trace.to_dict(), [], validator=validator
    )
    assert audit.status == "PASS", (audit.missing_checks, audit.diagnostics)
    failure = audit.to_dict()["coordinate_failure"]
    assert failure["stage"] == "circumference"
    assert failure["sample_index"] == 1
    assert failure["failing_reason"] == "solver.circumference"
    assert len(failure["completed_samples"]) == 3
    assert len(failure["completed_circumferences"]) == 1


def test_producer_radius_conversion_failure_is_replayed_from_real_trace():
    design, material = explicit_design([(0, 0), (1, 2.8284271247461903), (0, 5.656854249492381)])
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    design["solver_options"]["max_candidate_evaluations"] = 2
    base = config()
    run = replace(
        base,
        min_courses=3,
        max_courses=3,
        numerics=replace(base.numerics, roundoff_allowance_mm=1e-30),
    )
    batch = generate_analytic(design, material, run, PROVENANCE)
    assert batch.status is GenerationStatus.NUMERICAL_FAILURE
    assert batch.reason == "meridian.radius_conversion"
    assert batch.search_trace is not None
    validator = SemanticValidator(material_profiles={material["profile_id"]: material})
    run_config = asdict(run)
    run_config["minimum_shaping_separation_turns"] = "1/12"
    audit = inspect_analytic_search_trace(
        design, material, run_config, batch.search_trace.to_dict(), [], validator=validator
    )
    assert audit.status == "PASS"
    failure = audit.to_dict()["coordinate_failure"]
    assert failure["stage"] == "sample"
    assert failure["sample_index"] == 0
    assert failure["failing_reason"] == "meridian.radius_conversion"


def test_later_hypothesis_failure_retains_prior_completed_work_evidence():
    design, material = explicit_design([(0, 0), (3, 0), (3, 4), (0, 4)])
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    design["solver_options"]["max_candidate_evaluations"] = 2
    base = config()
    run = replace(
        base,
        min_courses=2,
        max_courses=3,
        min_count=32,
        max_count=32,
        initial_ring_min=32,
        initial_ring_max=32,
        numerics=replace(base.numerics, roundoff_allowance_mm=1e-30),
    )
    batch = generate_analytic(design, material, run, PROVENANCE)
    assert batch.status is GenerationStatus.NUMERICAL_FAILURE
    assert batch.reason.startswith("meridian.")
    assert batch.search_trace is not None
    validator = SemanticValidator(material_profiles={material["profile_id"]: material})
    run_config = asdict(run)
    run_config["minimum_shaping_separation_turns"] = "1/12"
    audit = inspect_analytic_search_trace(
        design, material, run_config, batch.search_trace.to_dict(), [], validator=validator
    )
    assert audit.status == "PASS", (audit.missing_checks, audit.diagnostics)
    failure = audit.to_dict()["coordinate_failure"]
    assert failure["hypothesis_index"] == 1
    assert failure["completed_prior_hypotheses"][0]["course_count"] == 2
    assert failure["completed_prior_hypotheses"][0]["completed"] is True
