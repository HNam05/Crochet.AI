from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest

from crochet_ai import forward_relax as relax_module
from crochet_ai.canonical import jcs_bytes
from crochet_ai.forward_forces import _evaluate_stretch_terms_at_coordinates
from crochet_ai.forward_initialization import PROFILE as INITIALIZATION_PROFILE
from crochet_ai.forward_initialization import ForwardInitialization
from crochet_ai.forward_inputs import ForwardInputs, admit_forward_inputs
from crochet_ai.forward_relax import ForwardRelaxError, relax_one_stretch_step
from crochet_ai.forward_stretch import ForwardStretchTerms, StretchTerm


def _inputs(*, max_energy: int = 20, max_trials: int = 8, force_tol: float = 0.01):
    loading = {
        "schema_version": "1.0.0", "loading_profile_id": "load-v1",
        "state": "UNLOADED_UNPRESSURIZED",
    }
    model = {
        "schema_version": "1.0.0", "model_profile_id": "hyp-v1",
        "status": "HYPOTHESIS", "source_provenance_id": "fixture-study",
        "stiffness_course_n_per_mm": 2.0, "stiffness_wale_n_per_mm": 2.0,
    }
    units = {
        "force_residual_n": "N", "position_step_mm": "mm",
        "relative_energy_change": "dimensionless", "contact_penetration_mm": "mm",
        "volume_orientation_epsilon_mm3": "mm^3", "mode_equivalence_rms_mm": "mm",
    }
    tolerances = {
        name: {"value": force_tol if name == "force_residual_n" else 0.01,
               "unit": unit, "rationale": f"Fixture {name} threshold.",
               "owner": "fixture-owner", "validation_path_id": f"test-{name}"}
        for name, unit in units.items()
    }
    config = {
        "schema_version": "1.0.0", "config_id": "run-v1",
        "model_version": "F0_STRETCH_PROTOTYPE",
        "work_budgets": {
            "max_initializations": 2, "max_initialization_vertices": 20,
            "max_line_search_trials": max_trials, "max_optimizer_iterations": 3,
            "max_energy_evaluations": max_energy, "max_linear_iterations": 20,
            "max_contact_pairs_evaluated": 20,
        },
        "tolerances": tolerances,
    }
    return admit_forward_inputs(loading, model, config)


def _artifacts(
    points: tuple[tuple[str, tuple[float, float, float]], ...], *,
    inputs: ForwardInputs | None = None,
):
    if inputs is None:
        inputs = _inputs()
    bound_hash = inputs.sha256
    projection_hash = "1" * 64
    material_hash = "2" * 64
    terms = ForwardStretchTerms(
        "EXPERIMENTAL_STRETCH_TERMS", projection_hash, material_hash,
        bound_hash, (StretchTerm("COURSE", "a", "b", 3.0, 2.0, "response-1"),),
    )
    payload = {
        "profile": INITIALIZATION_PROFILE, "status": "EXPERIMENTAL_INITIALIZATION",
        "projection_sha256": projection_hash, "material_sha256": material_hash,
        "forward_inputs_sha256": bound_hash, "anchor_location_groups": [],
        "coordinates_mm": [
            {"attachment_location_id": key, "xyz_mm": list(point)} for key, point in points
        ],
    }
    encoded = jcs_bytes(payload)
    init_hash = sha256(
        b"Crochet.AI\0" + INITIALIZATION_PROFILE.encode("ascii") + b"\0" + encoded
    ).hexdigest()
    initialization = ForwardInitialization(
        "EXPERIMENTAL_INITIALIZATION", projection_hash, material_hash, bound_hash,
        (), points, encoded, init_hash,
    )
    return inputs, terms, initialization


def test_one_step_accepts_exact_two_node_armijo_descent_and_is_deterministic() -> None:
    points = (("a", (0.0, 0.0, 0.0)), ("b", (5.0, 0.0, 0.0)))
    inputs, terms, initialization = _artifacts(points)
    first = relax_one_stretch_step(terms, initialization, inputs)
    second = relax_one_stretch_step(terms, initialization, inputs)
    assert first.status == "EXPERIMENTAL_STEP_ACCEPTED"
    assert first.baseline_energy_n_mm == 4.0
    assert first.trial_energies_n_mm == (0.0,)
    assert first.alpha_initial_mm_per_n == 0.25
    assert first.accepted_alpha_mm_per_n == 0.25
    assert first.coordinates_mm == (("a", (1.0, 0.0, 0.0)), ("b", (4.0, 0.0, 0.0)))
    assert first.optimizer_iterations == 1 and first.energy_evaluations == 2
    assert first.line_search_trials == 1
    assert first.canonical_bytes == second.canonical_bytes and first.sha256 == second.sha256


def test_one_step_evidence_binds_the_exact_initialization_artifact() -> None:
    inputs, terms, first_initialization = _artifacts(
        (("a", (0.0, 0.0, 0.0)), ("b", (5.0, 0.0, 0.0)))
    )
    _, _, second_initialization = _artifacts(
        (("a", (0.0, 0.0, 0.0)), ("b", (5.25, 0.0, 0.0)))
    )
    first = relax_one_stretch_step(terms, first_initialization, inputs)
    second = relax_one_stretch_step(terms, second_initialization, inputs)
    assert first.projection_sha256 == second.projection_sha256
    assert first.material_sha256 == second.material_sha256
    assert first.forward_inputs_sha256 == second.forward_inputs_sha256
    assert first.initialization_sha256 == first_initialization.sha256
    assert second.initialization_sha256 == second_initialization.sha256
    assert first.initialization_sha256 != second.initialization_sha256
    assert first.sha256 != second.sha256


def test_budget_exhaustion_counts_baseline_and_each_full_trial() -> None:
    points = (("a", (0.0, 0.0, 0.0)), ("b", (5.0, 0.0, 0.0)))
    inputs = _inputs(max_energy=1)
    _, terms, init = _artifacts(points, inputs=inputs)
    result = relax_one_stretch_step(terms, init, inputs)
    assert result.status == "BUDGET_EXHAUSTED"
    assert result.energy_evaluations == 1
    assert result.line_search_trials == 0
    assert result.alpha_trace_mm_per_n == ()
    assert result.trial_energies_n_mm == ()


def test_armijo_retry_halves_step_and_counts_rejected_evaluation(monkeypatch) -> None:
    points = (("a", (0.0, 0.0, 0.0)), ("b", (5.0, 0.0, 0.0)))
    inputs, terms, init = _artifacts(points)
    actual_kernel = _evaluate_stretch_terms_at_coordinates
    calls = 0

    def reject_first_trial(term_rows, coordinates):
        nonlocal calls
        calls += 1
        energy, forces, maximum_force = actual_kernel(term_rows, coordinates)
        if calls == 2:
            return energy + 10.0, forces, maximum_force
        return energy, forces, maximum_force

    monkeypatch.setattr(relax_module, "_evaluate_stretch_terms_at_coordinates", reject_first_trial)
    result = relax_one_stretch_step(terms, init, inputs)
    assert result.status == "EXPERIMENTAL_STEP_ACCEPTED"
    assert result.alpha_trace_mm_per_n == (0.25, 0.125)
    assert result.trial_energies_n_mm == (10.0, 1.0)
    assert result.energy_evaluations == 3 and result.line_search_trials == 2


def test_initial_stationarity_is_not_convergence() -> None:
    points = (("a", (0.0, 0.0, 0.0)), ("b", (3.0, 0.0, 0.0)))
    inputs, terms, init = _artifacts(points)
    result = relax_one_stretch_step(terms, init, inputs)
    assert result.status == "EXPERIMENTAL_INITIAL_STATIONARY"
    assert result.coordinates_mm == points
    assert result.energy_evaluations == 1 and result.line_search_trials == 0
    assert "CONVERGED" not in result.status


def test_tiny_unrepresentable_step_is_numerical_failure_not_stationary() -> None:
    points = (("a", (1e16, 0.0, 0.0)), ("b", (1e16 + 4.0, 0.0, 0.0)))
    inputs, terms, init = _artifacts(points)
    result = relax_one_stretch_step(terms, init, inputs)
    assert result.status == "NUMERICAL_FAILURE"
    assert result.baseline_maximum_force_n == 2.0
    assert result.energy_evaluations == 1 and result.line_search_trials == 1


def test_non_finite_trial_is_recorded_and_backtracked(monkeypatch) -> None:
    points = (("a", (0.0, 0.0, 0.0)), ("b", (5.0, 0.0, 0.0)))
    inputs, terms, init = _artifacts(points)
    tiny_stiff_term = replace(terms.terms[0], stiffness_n_per_mm=1e-308)
    terms = replace(terms, terms=(tiny_stiff_term,))
    calls = 0

    def huge_finite_force(_term_rows, _coordinates):
        nonlocal calls
        calls += 1
        if calls == 1:
            return 1.0, (("a", (1e308, 0.0, 0.0)), ("b", (-1e308, 0.0, 0.0))), 1e308
        raise AssertionError("non-finite candidates must not reach the energy kernel")

    monkeypatch.setattr(relax_module, "_evaluate_stretch_terms_at_coordinates", huge_finite_force)
    result = relax_one_stretch_step(terms, init, inputs)
    assert result.status == "LINE_SEARCH_FAILED"
    assert result.trial_energies_n_mm == (None,) * inputs.max_line_search_trials
    assert result.line_search_trials == inputs.max_line_search_trials
    assert result.energy_evaluations == 1 + inputs.max_line_search_trials
    assert result.alpha_trace_mm_per_n == tuple(
        5e307 / (2**index) for index in range(inputs.max_line_search_trials)
    )


def test_initial_zero_distance_and_hash_mismatch_fail_closed() -> None:
    points = (("a", (1.0, 0.0, 0.0)), ("b", (1.0, 0.0, 0.0)))
    inputs, terms, init = _artifacts(points)
    zero = relax_one_stretch_step(terms, init, inputs)
    assert zero.status == "NUMERICAL_FAILURE"
    assert zero.energy_evaluations == 1 and zero.line_search_trials == 0

    inputs, terms, init = _artifacts((("a", (0.0, 0.0, 0.0)), ("b", (5.0, 0.0, 0.0))))
    with pytest.raises(ForwardRelaxError, match=r"relax.inputs_hash_mismatch"):
        relax_one_stretch_step(terms, init, replace(inputs, sha256="f" * 64))


def test_public_api_rejects_arbitrary_target_or_coordinate_arguments() -> None:
    inputs, terms, init = _artifacts((("a", (0.0, 0.0, 0.0)), ("b", (5.0, 0.0, 0.0))))
    with pytest.raises(TypeError):
        relax_one_stretch_step(terms, init, inputs, target_coordinates={})  # type: ignore[call-arg]
