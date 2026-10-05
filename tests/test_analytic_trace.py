from dataclasses import replace
from fractions import Fraction
from hashlib import sha256

import pytest
from conftest import resolved_artifacts

from crochet_ai.analytic_compile import CompileProvenance
from crochet_ai.analytic_counts import (
    CountSearchBudget,
    CountSearchInput,
    CountSearchStatus,
    CountWindow,
    search_counts,
)
from crochet_ai.analytic_geometry import MeridianNumerics
from crochet_ai.analytic_placement import PlacementBudget, choose_phases
from crochet_ai.analytic_solver import AnalyticRunConfig, generate_analytic
from crochet_ai.analytic_trace import TRACE_DOMAIN
from crochet_ai.solver_types import GenerationError, GenerationStatus


def _inputs():
    design, material = resolved_artifacts()
    design["dimensions"]["measurements"][0]["value_mm"] = 4
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    design["solver_options"]["max_candidate_evaluations"] = 2
    return design, material


def _config() -> AnalyticRunConfig:
    return AnalyticRunConfig(
        "solver_params_fixture_minimal",
        "tension_fixture_default",
        "RELAXED_UNSTUFFED",
        MeridianNumerics(0.05, 1e-8, 10000, 1e-9),
        CountSearchBudget(32, 32, 32, 10000),
        PlacementBudget(64, 10000, 100000),
        3,
        4,
        2,
        2,
        2,
        32,
        2,
        6,
        6,
        6,
        6,
        Fraction(1, 12),
        2,
        200,
    )


PROVENANCE = CompileProvenance("a" * 40, "b" * 64, (("test_profile", "synthetic"),))


def test_trace_is_immutable_canonical_and_deterministic() -> None:
    design, material = _inputs()
    first = generate_analytic(design, material, _config(), PROVENANCE).search_trace
    second = generate_analytic(design, material, _config(), PROVENANCE).search_trace
    assert first is not None and second is not None
    assert first.payload_bytes == second.payload_bytes
    assert first.sha256 == second.sha256
    assert first.sha256 == sha256(TRACE_DOMAIN + first.payload_bytes).hexdigest()
    payload = first.to_dict()
    payload["hypotheses"].clear()
    assert first.to_dict()["hypotheses"]


def test_trace_absent_for_invalid_admission_and_present_for_empty_search() -> None:
    design, material = _inputs()
    invalid = generate_analytic(
        design, material, _config(), replace(PROVENANCE, software_commit="")
    )
    assert invalid.status == GenerationStatus.INVALID_SOLVER_INPUT
    assert invalid.search_trace is None
    empty = generate_analytic(
        design, material, replace(_config(), initial_ring_min=100, initial_ring_max=101), PROVENANCE
    )
    assert empty.status == GenerationStatus.NO_FEASIBLE_CONSTRUCTION
    assert empty.search_trace is not None
    assert empty.search_trace.to_dict()["terminal"]["reason"] == "domain.complete"


def test_trace_retains_partial_count_and_phase_work() -> None:
    design, material = _inputs()
    count_limited = replace(_config(), count_budget=CountSearchBudget(32, 32, 32, 1))
    count_batch = generate_analytic(design, material, count_limited, PROVENANCE)
    assert count_batch.search_trace is not None
    first = count_batch.search_trace.to_dict()["hypotheses"][0]
    assert first["completed"] is False
    assert first["count_layers"]
    assert any(not layer["completed"] for layer in first["count_layers"])

    placement_limited = replace(_config(), placement_budget=PlacementBudget(64, 1, 100000))
    phase_batch = generate_analytic(design, material, placement_limited, PROVENANCE)
    assert phase_batch.search_trace is not None
    phase = phase_batch.search_trace.to_dict()["hypotheses"][0]["phase"]
    assert phase["layers"]
    assert phase["layers"][-1]["completed"] is False
    assert phase_batch.placement_transition_evaluations == 1


def test_trace_records_initial_count_layer_budget_and_sampling_failure(monkeypatch) -> None:
    design, material = _inputs()
    narrow_states = replace(_config(), count_budget=CountSearchBudget(32, 32, 1, 10000))
    count_batch = generate_analytic(design, material, narrow_states, PROVENANCE)
    assert count_batch.search_trace is not None
    count_layers = count_batch.search_trace.to_dict()["hypotheses"][0]["count_layers"]
    assert count_layers[0] == {
        "pass": 1,
        "layer": 0,
        "retained_states": 5,
        "transition_evaluations": 0,
        "completed": False,
    }

    from crochet_ai import analytic_geometry

    def fail_sample(self, fraction):
        raise GenerationError(GenerationStatus.NUMERICAL_FAILURE, "fixture.sample_failure")

    monkeypatch.setattr(analytic_geometry.AnalyticMeridian, "sample", fail_sample)
    failed = generate_analytic(design, material, _config(), PROVENANCE)
    assert failed.search_trace is not None
    hypothesis = failed.search_trace.to_dict()["hypotheses"][0]
    assert hypothesis["stage"] == "sample"
    assert hypothesis["completed"] is False
    assert hypothesis["terminal_status"] == GenerationStatus.NUMERICAL_FAILURE.value
    assert hypothesis["terminal_reason"] == "fixture.sample_failure"


def test_trace_handles_extreme_empty_windows_and_circumference_overflow(monkeypatch) -> None:
    from crochet_ai import analytic_geometry

    design, material = _inputs()

    def huge_sample(self, fraction):
        return analytic_geometry.MeridianPoint(1e20, 1e20)

    monkeypatch.setattr(analytic_geometry.AnalyticMeridian, "sample", huge_sample)
    empty = generate_analytic(design, material, _config(), PROVENANCE)
    assert empty.search_trace is not None
    first_window = empty.search_trace.to_dict()["hypotheses"][0]["count_windows"][0]
    assert isinstance(first_window["minimum"], str)
    assert first_window["empty"] is True

    def overflowing_sample(self, fraction):
        return analytic_geometry.MeridianPoint(1.0, 1e308)

    monkeypatch.setattr(analytic_geometry.AnalyticMeridian, "sample", overflowing_sample)
    overflow = generate_analytic(design, material, _config(), PROVENANCE)
    assert overflow.status == GenerationStatus.NUMERICAL_FAILURE
    assert overflow.search_trace is not None
    hypothesis = overflow.search_trace.to_dict()["hypotheses"][0]
    assert hypothesis["stage"] == "circumference"
    assert hypothesis["circumference_mm"] == []


def test_count_layer_work_matches_hand_counted_edges() -> None:
    request = CountSearchInput(
        (Fraction(2), Fraction(3)),
        Fraction(1),
        (CountWindow(2, 3), CountWindow(2, 3)),
        1,
        1,
        CountSearchBudget(2, 2, 2, 5),
    )
    result = search_counts(request)
    assert result.status == CountSearchStatus.OPTIMAL_COUNT_PROPOSAL
    assert result.transition_evaluations == 5
    assert [layer.retained_state_count for layer in result.layer_trace] == [2, 2, 1, 1]
    assert sum(layer.transition_evaluations for layer in result.layer_trace) == 5

    interrupted = search_counts(
        CountSearchInput(
            request.circumference_mm,
            request.stitch_pitch_mm,
            request.windows,
            request.max_increases_per_course,
            request.max_decreases_per_course,
            CountSearchBudget(2, 2, 2, 4),
        )
    )
    assert interrupted.status == CountSearchStatus.SEARCH_BUDGET_EXHAUSTED
    assert interrupted.completed_passes == 1
    assert interrupted.transition_evaluations == 4
    assert sum(layer.transition_evaluations for layer in interrupted.layer_trace) == 4
    assert interrupted.layer_trace[-1].pass_index == 2
    assert interrupted.layer_trace[-1].transition_evaluations == 0
    assert not interrupted.layer_trace[-1].completed
    assert interrupted.counts == () and interrupted.objective is None


def test_phase_layer_work_matches_hand_counted_transitions_and_pairs() -> None:
    complete = choose_phases((2, 3, 2), Fraction(0), PlacementBudget(8, 100, 100))
    assert complete.transition_evaluations == 8
    assert complete.pair_evaluations == 6
    assert [layer.transition_evaluations for layer in complete.layer_trace] == [2, 6]
    assert [layer.pair_evaluations for layer in complete.layer_trace] == [0, 6]

    with pytest.raises(GenerationError) as captured:
        choose_phases((2, 3, 2), Fraction(0), PlacementBudget(8, 100, 3))
    error = captured.value
    assert error.reason == "placement.pairs"
    assert error.work["placement_transitions"] == 6
    assert error.work["placement_pairs"] == 3
    assert sum(layer.transition_evaluations for layer in error.trace) == 6
    assert sum(layer.pair_evaluations for layer in error.trace) == 3
    assert not error.trace[-1].completed


def test_trace_course_slot_ceiling_preserves_emitted_prefix() -> None:
    design, material = _inputs()
    config = replace(
        _config(),
        min_courses=250,
        max_courses=512,
        max_course_hypotheses=512,
        initial_ring_min=400,
        initial_ring_max=401,
    )
    # Empty windows still consume their reserved course slots; the next one exceeds 8192.
    batch = generate_analytic(design, material, config, PROVENANCE)
    assert batch.search_trace is not None
    assert batch.reason == "budget.trace_course_slots"
    assert batch.search_trace.to_dict()["terminal"]["reserved_course_slots"] <= 8192
