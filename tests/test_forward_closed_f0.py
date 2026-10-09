from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from inspect import signature
from math import hypot
from typing import Any, cast

import pytest
from test_forward_closed_mechanics import _value as _closed_value
from test_forward_shaped import _recipe as _elastic_recipe
from test_forward_shaped import _setup

from crochet_ai.forward_closed_f0 import (
    INITIALIZATION_RULE,
    PROFILE,
    Objective,
    _gauge,
    _optimize,
    _validate_recipe,
    admit_closed_f0_recipe,
    run_closed_f0,
)
from crochet_ai.forward_inputs import ForwardInputs, admit_forward_inputs


def _recipe() -> dict[str, Any]:
    closed = deepcopy(_closed_value())
    elastic = closed["elastic_recipe"]
    budgets = elastic["config"]["work_budgets"]
    budgets.update(
        max_energy_evaluations=2,
        max_optimizer_iterations=2,
        max_line_search_trials=2,
        max_contact_pairs_evaluated=100_000,
    )
    # Tight synthetic fixture tolerances keep this module's convergence claim
    # separate from any physical calibration claim.
    for name in elastic["config"]["tolerances"]:
        elastic["config"]["tolerances"][name]["value"] = 1e-6
    return {
        "profile": PROFILE,
        "closed_recipe": closed,
        "shell_parameters": {
            "schema_version": "1.0.0",
            "status": "HYPOTHESIS",
            "provenance_id": "synthetic-shell-test",
            "rest_corner_angle_rad": 1.2,
            "shear_stiffness_n_mm": 0.2,
            "rest_dihedral_rad": 0.0,
            "bending_stiffness_n_mm": 0.1,
        },
        "contact_parameters": {
            "schema_version": 1,
            "status": "HYPOTHESIS",
            "provenance_id": "synthetic-contact-test",
            "activation_distance_mm": 0.2,
            "minimum_clearance_mm": 0.01,
            "stiffness_n_per_mm": 0.5,
            "max_pair_evaluations": 100_000,
        },
        "solver_parameters": {
            "schema_version": "1.0.0",
            "initialization_rule": INITIALIZATION_RULE,
            "start_count": 2,
            "perturbation_mm": 0.01,
            "seed": 7,
        },
    }


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(target_mesh={}),
        lambda d: d.update(target_correspondence=[]),
        lambda d: d.update(profile="FORWARD_CLOSED_F0_V0"),
        lambda d: d["solver_parameters"].update(schema_version="2.0.0"),
        lambda d: d["solver_parameters"].update(start_count=True),
        lambda d: d["solver_parameters"].update(seed=4_294_967_296),
        lambda d: d["solver_parameters"].update(perturbation_mm=float("inf")),
        lambda d: d["shell_parameters"].update(shear_stiffness_n_mm=True),
        lambda d: d["closed_recipe"]["pressure_loading"].update(
            pressure_n_per_mm2=9_007_199_254_740_992
        ),
    ],
)
def test_recipe_admission_rejects_tampering_target_fields_and_non_native_finite_values(
    mutation: Any,
) -> None:
    raw = _recipe()
    mutation(raw)
    with pytest.raises(ValueError):
        admit_closed_f0_recipe(raw)


def test_recipe_hash_is_recomputed_and_runtime_has_no_target_argument() -> None:
    admitted = admit_closed_f0_recipe(_recipe())
    forged = replace(admitted, sha256="0" * 64)
    with pytest.raises(ValueError):
        _validate_recipe(forged)
    assert "target_mesh" not in signature(run_closed_f0).parameters


def test_real_closed_ir_failure_is_deterministic_redacted_and_counts_all_starts() -> None:
    projection, material, validator = _setup((3, 4, 3))
    raw = _recipe()
    raw["closed_recipe"]["elastic_recipe"]["config"]["work_budgets"]["max_energy_evaluations"] = 1
    recipe = admit_closed_f0_recipe(raw)
    first: dict[str, Any] = run_closed_f0(projection, material, recipe, validator=validator)
    second: dict[str, Any] = run_closed_f0(projection, material, recipe, validator=validator)
    assert first == second
    assert first["profile"] == PROFILE
    assert first["status"] in {"DIVERGED", "BUDGET_EXHAUSTED"}
    assert first["comparison_eligible"] is False
    assert first["physical_status"] == "UNTESTED"
    assert first["coordinates_mm"] is None
    assert first["faces"] is None
    assert first["final_mechanics"] is None
    assert len(first["starts"]) == 2
    assert all(record["coordinates_mm"] is None for record in first["starts"])
    assert all(record["energy_evaluations"] <= 1 for record in first["starts"])


def _inputs(*, energy_budget: int = 64, iterations: int = 8, trials: int = 8) -> ForwardInputs:
    raw = _elastic_recipe()
    budgets = raw["config"]["work_budgets"]
    budgets.update(
        max_energy_evaluations=energy_budget,
        max_optimizer_iterations=iterations,
        max_line_search_trials=trials,
    )
    for key, limit in (
        ("force_residual_n", 1e-4),
        ("position_step_mm", 1e-8),
        ("relative_energy_change", 1e-12),
    ):
        raw["config"]["tolerances"][key]["value"] = limit
    return admit_forward_inputs(raw["loading"], raw["model_profile"], raw["config"])


def _quadratic(points: dict[str, tuple[float, float, float]]) -> Objective:
    forces = {
        key: cast(tuple[float, float, float], tuple(-v for v in point))
        for key, point in points.items()
    }
    energy = 0.5 * sum(v * v for point in points.values() for v in point)
    maximum = max(hypot(*force) for force in forces.values())
    return Objective(energy, forces, maximum, {"oracle": "exact_quadratic"})


def test_optimizer_matches_exact_quadratic_oracle_and_counts_every_objective() -> None:
    initial = {"p": (0.2, -0.1, 0.05)}
    evaluated: list[dict[str, tuple[float, float, float]]] = []

    def evaluate(points: dict[str, tuple[float, float, float]]) -> Objective:
        evaluated.append(dict(points))
        return _quadratic(points)

    result = _optimize(initial, _inputs(), evaluate, lambda _a, _b: ("SAFE", "oracle-safe"))
    assert result.status == "CONVERGED"
    assert result.evaluations == len(evaluated)
    assert result.evaluations <= 64
    accepted = [event for event in cast(Any, result.trace) if event["kind"] == "ACCEPTED_STEP"]
    assert accepted
    assert result.final is not None
    assert result.final.energy_n_mm == pytest.approx(
        0.5 * sum(v * v for point in result.points.values() for v in point)
    )
    assert result.final.energy_n_mm < _quadratic(initial).energy_n_mm
    assert result.final.maximum_force_n <= dict(_inputs().tolerances)["force_residual_n"].value
    assert result.last_step_mm is not None
    assert result.last_step_mm <= dict(_inputs().tolerances)["position_step_mm"].value
    assert result.relative_energy_change is not None
    assert (
        result.relative_energy_change <= dict(_inputs().tolerances)["relative_energy_change"].value
    )
    assert result.stationary_checks >= 2
    assert result.iterations <= 8
    assert result.trials <= 8 * 8


def test_optimizer_backtracks_indeterminate_path_without_objective_call() -> None:
    calls: list[dict[str, tuple[float, float, float]]] = []
    certificates: list[
        tuple[dict[str, tuple[float, float, float]], dict[str, tuple[float, float, float]]]
    ] = []

    def evaluate(points: dict[str, tuple[float, float, float]]) -> Objective:
        calls.append(dict(points))
        return _quadratic(points)

    def certify(
        start: dict[str, tuple[float, float, float]], end: dict[str, tuple[float, float, float]]
    ) -> tuple[str, str]:
        certificates.append((dict(start), dict(end)))
        return (
            ("INDETERMINATE", "certificate_inconclusive")
            if len(certificates) == 1
            else ("SAFE", "proved")
        )

    result = _optimize({"p": (0.2, 0.0, 0.0)}, _inputs(), evaluate, certify)
    trace: list[Any] = cast(Any, result.trace)
    trials = [event for event in trace if event["kind"] == "TRIAL"]
    assert trials and trials[0]["cause"] == "certificate_inconclusive"
    assert len(certificates) >= 2
    assert len(calls) == result.evaluations
    accepted_count = len([e for e in trace if e["kind"] == "ACCEPTED_STEP"])
    assert len(calls) == 1 + accepted_count + max(0, result.stationary_checks - 1)
    assert trace.index(trials[0]) < next(
        i for i, event in enumerate(trace) if event["kind"] == "ACCEPTED_STEP"
    )


def test_optimizer_rejects_unsafe_endpoint_without_final_hidden_evaluation() -> None:
    calls = 0

    def evaluate(points: dict[str, tuple[float, float, float]]) -> Objective:
        nonlocal calls
        calls += 1
        return _quadratic(points)

    result = _optimize(
        {"p": (0.2, 0.0, 0.0)},
        _inputs(iterations=1, trials=1),
        evaluate,
        lambda _a, _b: ("UNRESOLVED_COLLISION", "unsafe_endpoint"),
    )
    assert result.status == "DIVERGED"
    assert result.reason == "line_search_exhausted"
    assert calls == result.evaluations == 1
    assert result.iterations == 0
    assert cast(Any, result.trace)[0]["cause"] == "unsafe_endpoint"


def test_gauge_is_equivariant_under_proper_rigid_motion() -> None:
    points = {
        "a": (0.0, 0.0, 0.0),
        "b": (2.0, 0.0, 0.0),
        "c": (0.0, 1.0, 0.0),
        "d": (0.25, 0.25, 1.0),
    }
    face = ("a", "b", "c")
    rotated = {
        key: (-point[1] + 8.0, point[0] - 3.0, point[2] + 4.0) for key, point in points.items()
    }
    gauged, transformed = _gauge(points, face), _gauge(rotated, face)
    assert transformed == pytest.approx(gauged)


def test_optimizer_rejects_forged_residual_and_does_not_publish_convergence() -> None:
    def lying_objective(points: dict[str, tuple[float, float, float]]) -> Objective:
        actual = _quadratic(points)
        return replace(actual, maximum_force_n=0.0)

    result = _optimize(
        {"p": (1.0, 0.0, 0.0)}, _inputs(), lying_objective, lambda _a, _b: ("SAFE", "oracle-safe")
    )
    assert result.status == "NUMERICAL_FAILURE"
    assert result.reason == "f0.force_residual_assertion_mismatch"
    assert result.evaluations == 1
    assert result.stationary_checks == 0
