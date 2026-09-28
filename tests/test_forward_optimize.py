from __future__ import annotations

from dataclasses import replace
from hashlib import sha256

import pytest

from crochet_ai.canonical import jcs_bytes
from crochet_ai.forward_initialization import PROFILE as INITIALIZATION_PROFILE
from crochet_ai.forward_initialization import ForwardInitialization
from crochet_ai.forward_inputs import ForwardInputs, admit_forward_inputs
from crochet_ai.forward_optimize import ForwardOptimizeError, optimize_stretch_prototype
from crochet_ai.forward_stretch import ForwardStretchTerms, StretchTerm


def _inputs(*, max_iterations: int = 20, max_energy: int = 100, max_trials: int = 8):
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
        name: {
            "value": 0.01, "unit": unit, "rationale": f"Fixture {name} threshold.",
            "owner": "fixture-owner", "validation_path_id": f"test-{name}",
        }
        for name, unit in units.items()
    }
    config = {
        "schema_version": "1.0.0", "config_id": "run-v1",
        "model_version": "F0_STRETCH_PROTOTYPE",
        "work_budgets": {
            "max_initializations": 2, "max_initialization_vertices": 20,
            "max_line_search_trials": max_trials, "max_optimizer_iterations": max_iterations,
            "max_energy_evaluations": max_energy, "max_linear_iterations": 20,
            "max_contact_pairs_evaluated": 20,
        },
        "tolerances": tolerances,
    }
    return admit_forward_inputs(loading, model, config)


def _artifacts(
    points: tuple[tuple[str, tuple[float, float, float]], ...],
    terms: tuple[StretchTerm, ...],
    *,
    inputs: ForwardInputs | None = None,
):
    admitted = _inputs() if inputs is None else inputs
    projection_hash = "1" * 64
    material_hash = "2" * 64
    prepared = ForwardStretchTerms(
        "EXPERIMENTAL_STRETCH_TERMS", projection_hash, material_hash,
        admitted.sha256, terms,
    )
    payload = {
        "profile": INITIALIZATION_PROFILE, "status": "EXPERIMENTAL_INITIALIZATION",
        "projection_sha256": projection_hash, "material_sha256": material_hash,
        "forward_inputs_sha256": admitted.sha256, "anchor_location_groups": [],
        "coordinates_mm": [
            {"attachment_location_id": key, "xyz_mm": list(point)}
            for key, point in points
        ],
    }
    encoded = jcs_bytes(payload)
    digest = sha256(
        b"Crochet.AI\0" + INITIALIZATION_PROFILE.encode("ascii") + b"\0" + encoded
    ).hexdigest()
    initialization = ForwardInitialization(
        "EXPERIMENTAL_INITIALIZATION", projection_hash, material_hash, admitted.sha256,
        (), points, encoded, digest,
    )
    return admitted, prepared, initialization


def _two_node():
    return _artifacts(
        (("a", (0.0, 0.0, 0.0)), ("b", (5.0, 0.0, 0.0))),
        (StretchTerm("COURSE", "a", "b", 3.0, 2.0, "response-ab"),),
    )


def test_two_node_reaches_experimental_force_balance_in_one_step() -> None:
    inputs, terms, initialization = _two_node()
    first = optimize_stretch_prototype(terms, initialization, inputs)
    second = optimize_stretch_prototype(terms, initialization, inputs)
    assert first.status == "EXPERIMENTAL_FORCE_BALANCED"
    assert first.coordinates_mm == (("a", (1.0, 0.0, 0.0)), ("b", (4.0, 0.0, 0.0)))
    assert first.maximum_force_n == 0.0
    assert first.optimizer_iterations == 1 and first.energy_evaluations == 2
    assert first.line_search_trials == 1
    assert first.canonical_bytes == second.canonical_bytes
    assert first.sha256 == second.sha256
    assert "CONVERGED" not in first.status


def test_run_evidence_binds_exact_initialization_bytes() -> None:
    spring = (StretchTerm("COURSE", "a", "b", 3.0, 2.0, "response-ab"),)
    first_inputs, first_terms, first_init = _artifacts(
        (("a", (0.0, 0.0, 0.0)), ("b", (5.0, 0.0, 0.0))), spring
    )
    second_inputs, second_terms, second_init = _artifacts(
        (("a", (0.0, 0.0, 0.0)), ("b", (5.25, 0.0, 0.0))), spring
    )
    first = optimize_stretch_prototype(first_terms, first_init, first_inputs)
    second = optimize_stretch_prototype(second_terms, second_init, second_inputs)
    assert first.projection_sha256 == second.projection_sha256
    assert first.material_sha256 == second.material_sha256
    assert first.forward_inputs_sha256 == second.forward_inputs_sha256
    assert first.initialization_sha256 == first_init.sha256
    assert second.initialization_sha256 == second_init.sha256
    assert first.initialization_sha256 != second.initialization_sha256
    assert first.sha256 != second.sha256


def test_global_iteration_budget_exhaustion_does_not_publish_coordinates() -> None:
    network = (
        StretchTerm("COURSE", "a", "b", 3.0, 2.0, "response-ab"),
        StretchTerm("WALE", "b", "c", 3.0, 2.0, "response-bc"),
    )
    inputs = _inputs(max_iterations=1)
    inputs, terms, initialization = _artifacts(
        (("a", (0.0, 0.0, 0.0)), ("b", (5.0, 0.0, 0.0)), ("c", (12.0, 0.0, 0.0))),
        network,
        inputs=inputs,
    )
    result = optimize_stretch_prototype(terms, initialization, inputs)
    assert result.status == "BUDGET_EXHAUSTED"
    assert result.coordinates_mm is None
    assert result.optimizer_iterations == 1
    assert result.energy_evaluations == 2
    assert result.line_search_trials == 1
    assert len(result.iterations) == 1


def test_energy_budget_is_global_while_line_search_limit_is_per_step() -> None:
    network = (
        StretchTerm("COURSE", "a", "b", 3.0, 2.0, "response-ab"),
        StretchTerm("WALE", "b", "c", 3.0, 2.0, "response-bc"),
    )
    inputs = _inputs(max_iterations=10, max_energy=4, max_trials=1)
    inputs, terms, initialization = _artifacts(
        (("a", (0.0, 0.0, 0.0)), ("b", (5.0, 0.0, 0.0)), ("c", (12.0, 0.0, 0.0))),
        network,
        inputs=inputs,
    )
    result = optimize_stretch_prototype(terms, initialization, inputs)
    assert result.status == "BUDGET_EXHAUSTED"
    assert result.coordinates_mm is None
    assert result.optimizer_iterations == 2
    assert result.energy_evaluations == 4
    assert result.line_search_trials == 2
    assert len(result.iterations) == 2
    assert result.iterations[0].line_search_trials == inputs.max_line_search_trials
    assert result.iterations[1].line_search_trials == inputs.max_line_search_trials
    assert result.maximum_force_n is not None


def test_baseline_only_energy_budget_exhaustion_keeps_force_diagnostic() -> None:
    inputs = _inputs(max_iterations=10, max_energy=1)
    inputs, terms, initialization = _artifacts(
        (("a", (0.0, 0.0, 0.0)), ("b", (5.0, 0.0, 0.0))),
        (StretchTerm("COURSE", "a", "b", 3.0, 2.0, "response-ab"),),
        inputs=inputs,
    )
    result = optimize_stretch_prototype(terms, initialization, inputs)
    assert result.status == "BUDGET_EXHAUSTED"
    assert result.coordinates_mm is None
    assert result.maximum_force_n == 4.0
    assert result.optimizer_iterations == 1
    assert result.energy_evaluations == 1 and result.line_search_trials == 0


def test_initial_force_balance_reports_only_experimental_stretch_status() -> None:
    inputs, terms, initialization = _artifacts(
        (("a", (0.0, 0.0, 0.0)), ("b", (3.0, 0.0, 0.0))),
        (StretchTerm("COURSE", "a", "b", 3.0, 2.0, "response-ab"),),
    )
    result = optimize_stretch_prototype(terms, initialization, inputs)
    assert result.status == "EXPERIMENTAL_FORCE_BALANCED"
    assert result.coordinates_mm == initialization.coordinates_mm
    assert result.optimizer_iterations == 1 and result.energy_evaluations == 1
    assert result.line_search_trials == 0


def test_zero_distance_and_hash_mismatch_are_rejected() -> None:
    inputs, terms, initialization = _artifacts(
        (("a", (1.0, 0.0, 0.0)), ("b", (1.0, 0.0, 0.0))),
        (StretchTerm("COURSE", "a", "b", 3.0, 2.0, "response-ab"),),
    )
    result = optimize_stretch_prototype(terms, initialization, inputs)
    assert result.status == "NUMERICAL_FAILURE"
    assert result.coordinates_mm is None
    assert result.energy_evaluations == 1

    inputs, terms, initialization = _two_node()
    with pytest.raises(ForwardOptimizeError, match=r"relax\.inputs_hash_mismatch"):
        optimize_stretch_prototype(terms, initialization, replace(inputs, sha256="f" * 64))


def test_target_coordinates_are_not_accepted_by_public_api() -> None:
    inputs, terms, initialization = _two_node()
    with pytest.raises(TypeError):
        optimize_stretch_prototype(terms, initialization, inputs, target_coordinates={})  # type: ignore[call-arg]
