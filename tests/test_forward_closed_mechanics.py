from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from test_forward_shaped import _recipe, _setup

import crochet_ai.forward_closed_mechanics as closed_mechanics
from crochet_ai.forward_closed_mechanics import (
    PROFILE,
    ForwardClosedMechanicsError,
    _evaluate,
    _perimeter_term,
    _pressure_geometry,
    admit_closed_mechanics_recipe,
    run_closed_mechanics,
)
from crochet_ai.forward_forces import ForwardForceError


def _value() -> dict[str, Any]:
    return {
        "profile": PROFILE,
        "elastic_recipe": _recipe(),
        "closure_parameters": {
            "schema_version": "1.0.0",
            "status": "HYPOTHESIS",
            "provenance_id": "synthetic-closure",
            "ring_rest_perimeter_mm": 1.0,
            "ring_stiffness_n_per_mm": 0.2,
            "close_rest_perimeter_mm": 1.0,
            "close_stiffness_n_per_mm": 0.2,
        },
        "pressure_loading": {
            "schema_version": "1.0.0",
            "status": "USER_DECLARED",
            "loading_profile_id": "synthetic-pressure",
            "provenance_id": "synthetic-load-record",
            "pressure_n_per_mm2": 0.001,
            "volume_limit_mm3": 100.0,
        },
    }


def _tetra() -> tuple[list[list[str]], dict[str, tuple[float, float, float]]]:
    # Outward-oriented unit right tetrahedron, independently stated oracle.
    return (
        [["a", "c", "b"], ["a", "b", "d"], ["a", "d", "c"], ["b", "c", "d"]],
        {
            "a": (0.0, 0.0, 0.0),
            "b": (1.0, 0.0, 0.0),
            "c": (0.0, 1.0, 0.0),
            "d": (0.0, 0.0, 1.0),
        },
    )


def test_pressure_volume_and_gradient_oracle_for_tetrahedron() -> None:
    faces, points = _tetra()
    volume, forces = _pressure_geometry(faces, points)
    assert volume == pytest.approx(1.0 / 6.0)
    assert forces["d"] == pytest.approx((0.0, 0.0, 1.0 / 6.0))
    pressure = 0.7
    assert sum(pressure * forces[key][0] for key in points) == pytest.approx(0.0, abs=1e-15)
    assert sum(pressure * forces[key][1] for key in points) == pytest.approx(0.0, abs=1e-15)
    assert sum(pressure * forces[key][2] for key in points) == pytest.approx(0.0, abs=1e-15)
    torque = [0.0, 0.0, 0.0]
    for key, point in points.items():
        force = tuple(pressure * part for part in forces[key])
        torque[0] += point[1] * force[2] - point[2] * force[1]
        torque[1] += point[2] * force[0] - point[0] * force[2]
        torque[2] += point[0] * force[1] - point[1] * force[0]
    assert torque == pytest.approx([0.0, 0.0, 0.0], abs=1e-15)
    h = 1e-6
    moved = dict(points)
    moved["d"] = (h, 0.0, 1.0)
    moved_volume, _ = _pressure_geometry(faces, moved)
    assert (moved_volume - volume) / h == pytest.approx(forces["d"][0], rel=1e-6)


def test_pressure_geometry_is_rigid_motion_invariant() -> None:
    faces, points = _tetra()
    volume, _ = _pressure_geometry(faces, points)
    moved = {
        key: (-point[1] + 8.0, point[0] - 3.0, point[2] + 4.0) for key, point in points.items()
    }
    assert _pressure_geometry(faces, moved)[0] == pytest.approx(volume)


def test_signed_volume_and_operational_limit_fail_closed() -> None:
    faces, points = _tetra()
    ring = _perimeter_term("RING_CLOSURE", ("a", "b", "c"), 0.0, 1.0)
    close = _perimeter_term("CLOSE_CLOSURE", ("a", "b", "c"), 0.0, 1.0)
    with pytest.raises(ForwardForceError, match=r"closed\.volume_invalid"):
        _evaluate((), ring, close, 0.0, [list(reversed(face)) for face in faces], points, 0.0, 1.0)
    with pytest.raises(ForwardForceError, match=r"closed\.volume_invalid"):
        _evaluate((), ring, close, 0.0, faces, points, 0.0, 0.1)
    collapsed = dict(points)
    collapsed["b"] = collapsed["a"]
    with pytest.raises(ForwardForceError, match=r"closed\.edge_zero_or_non_finite"):
        _evaluate((), ring, close, 0.0, faces, collapsed, 0.0, 1.0)


def test_tension_only_closure_has_zero_inactive_energy_and_force() -> None:
    cycle = ("a", "b", "c")
    faces, vol_points = _tetra()
    ring = _perimeter_term("RING_CLOSURE", cycle, 10.0, 2.0)
    close = _perimeter_term("CLOSE_CLOSURE", cycle, 10.0, 3.0)
    state = _evaluate((), ring, close, 0.0, faces, vol_points, 0.0, 10.0)
    assert state[3]["closure_energy_n_mm"] == 0.0
    assert state[3]["ring_closure"]["tension_n"] == 0.0
    assert state[3]["close_closure"]["tension_n"] == 0.0
    assert all(force == (0.0, 0.0, 0.0) for force in state[1].values())

    active = _evaluate(
        (),
        _perimeter_term("RING_CLOSURE", cycle, 1.0, 2.0),
        close,
        0.0,
        faces,
        vol_points,
        0.0,
        10.0,
    )
    assert active[3]["ring_closure"]["tension_n"] > 0.0
    assert active[3]["closure_energy_n_mm"] > 0.0
    assert tuple(sum(force[i] for force in active[1].values()) for i in range(3)) == pytest.approx(
        (0.0, 0.0, 0.0), abs=1e-14
    )
    step = 1e-6
    shifted = dict(vol_points)
    shifted["a"] = (step, 0.0, 0.0)
    shifted_state = _evaluate(
        (),
        _perimeter_term("RING_CLOSURE", cycle, 1.0, 2.0),
        close,
        0.0,
        faces,
        shifted,
        0.0,
        10.0,
    )
    energy_gradient = (shifted_state[0] - active[0]) / step
    assert energy_gradient == pytest.approx(-active[1]["a"][0], rel=1e-6)


def test_admission_rejects_prohibited_fields_and_rechecks_replaced_hash() -> None:
    value = _value()
    admitted = admit_closed_mechanics_recipe(value)
    with pytest.raises(ForwardClosedMechanicsError):
        admit_closed_mechanics_recipe({**value, "coordinates_mm": []})
    replaced = type(admitted)(admitted.canonical_bytes, "0" * 64)
    projection, material, validator = _setup((3, 4, 3))
    with pytest.raises(ForwardClosedMechanicsError):
        run_closed_mechanics(projection, material, replaced, validator=validator)


@pytest.mark.parametrize("bad", [True, -1, float("inf")])
def test_pressure_and_closure_numbers_fail_closed(bad: object) -> None:
    value = _value()
    value["pressure_loading"]["pressure_n_per_mm2"] = bad
    with pytest.raises(ForwardClosedMechanicsError):
        admit_closed_mechanics_recipe(value)


def test_closed_mechanics_runs_deterministically_with_redacted_failure_geometry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projection, material, validator = _setup((3, 4, 3))
    raw = _value()
    raw["elastic_recipe"]["config"]["work_budgets"]["max_energy_evaluations"] = 1
    recipe = admit_closed_mechanics_recipe(raw)
    callback_evaluations = 0
    original_evaluate = closed_mechanics._evaluate_checked

    def count_evaluate(*args: Any, **kwargs: Any) -> Any:
        nonlocal callback_evaluations
        callback_evaluations += 1
        return original_evaluate(*args, **kwargs)

    monkeypatch.setattr(closed_mechanics, "_evaluate_checked", count_evaluate)
    one = run_closed_mechanics(projection, material, recipe, validator=validator)
    assert callback_evaluations == 1
    callback_evaluations = 0
    two = run_closed_mechanics(projection, material, recipe, validator=validator)
    assert callback_evaluations == 1
    assert one == two
    assert one["status"] == "BUDGET_EXHAUSTED"
    assert one["coordinates_mm"] is None
    assert one["faces"] is None
    assert one["energy_evaluations"] <= 1
    assert one["preparation_energy_evaluations"] == 1


def test_invalid_initial_mechanics_is_structured_and_geometry_is_redacted() -> None:
    projection, material, validator = _setup((3, 4, 3))
    raw = _value()
    raw["pressure_loading"]["volume_limit_mm3"] = 0.02
    raw["elastic_recipe"]["config"]["work_budgets"]["max_energy_evaluations"] = 1
    result = run_closed_mechanics(
        projection, material, admit_closed_mechanics_recipe(raw), validator=validator
    )
    assert result["status"] == "NUMERICAL_FAILURE"
    assert result["energy_evaluations"] == 1
    assert result["initial_mechanics"] is None
    assert result["final_mechanics"] is None
    assert result["coordinates_mm"] is None
    assert result["faces"] is None


def test_huge_finite_pressure_force_norm_fails_inside_counted_callback() -> None:
    projection, material, validator = _setup((3, 4, 3))
    raw = _value()
    raw["pressure_loading"]["pressure_n_per_mm2"] = 1.1e154
    raw["elastic_recipe"]["config"]["work_budgets"]["max_energy_evaluations"] = 1
    result = run_closed_mechanics(
        projection, material, admit_closed_mechanics_recipe(raw), validator=validator
    )
    assert result["status"] == "NUMERICAL_FAILURE"
    assert result["energy_evaluations"] == 1
    assert result["initial_mechanics"] is None
    assert result["coordinates_mm"] is None
    assert result["faces"] is None


def test_published_geometry_uses_optimizer_coordinates(monkeypatch: pytest.MonkeyPatch) -> None:
    projection, material, validator = _setup((3, 4, 3))
    expected_rows: list[dict[str, Any]] = []

    def accept_translated(
        initial: dict[str, tuple[float, float, float]],
        _inputs: Any,
        evaluate: Any,
        *,
        recoverable_trial_error: Any,
    ) -> Any:
        nonlocal expected_rows
        translated = {
            key: (point[0] + 0.25, point[1] - 0.5, point[2] + 0.75)
            for key, point in initial.items()
        }
        _energy, _force, maximum = evaluate(translated)
        expected_rows = [
            {"attachment_location_id": key, "position_mm": list(point)}
            for key, point in sorted(translated.items())
        ]
        return SimpleNamespace(
            status="EXPERIMENTAL_FORCE_BALANCED",
            coordinates=translated,
            maximum_force_n=maximum,
            optimizer_iterations=1,
            energy_evaluations=1,
            line_search_trials=0,
            trace=(),
        )

    monkeypatch.setattr(closed_mechanics, "_run_armijo", accept_translated)
    result = run_closed_mechanics(
        projection, material, admit_closed_mechanics_recipe(_value()), validator=validator
    )
    rows = result["coordinates_mm"]
    assert rows == expected_rows


def test_optimizer_returns_only_force_balanced_lower_energy_debug_geometry() -> None:
    projection, material, validator = _setup((3, 4, 3))
    raw = _value()
    budgets = raw["elastic_recipe"]["config"]["work_budgets"]
    budgets.update(
        max_energy_evaluations=512, max_optimizer_iterations=128, max_line_search_trials=32
    )
    recipe = admit_closed_mechanics_recipe(raw)
    result = run_closed_mechanics(projection, material, recipe, validator=validator)
    assert result["status"] == "EXPERIMENTAL_FORCE_BALANCED"
    assert result["comparison_eligible"] is False
    assert result["v6_status"] == "NOT_RUN"
    assert result["coordinates_mm"] is not None
    assert result["faces"] is not None
    initial = result["initial_mechanics"]["energy_n_mm"]
    final = result["final_mechanics"]["energy_n_mm"]
    assert final < initial
    assert result["energy_evaluations"] <= 512
    assert result["line_search_trials"] <= 32 * result["optimizer_iterations"]
