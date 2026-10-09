from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from math import dist, hypot
from types import SimpleNamespace
from typing import cast

import pytest
from test_backend_numerical_delivery import f0_request
from test_forward_closed_f0 import _inputs

from crochet_ai.canonical import jcs_bytes
from crochet_ai.forward_closed_f0 import admit_closed_f0_recipe, run_closed_f0
from crochet_ai.forward_f0_audit import (
    F0AuditError,
    _Objective,
    _point_hash,
    _replay_start,
    audit_closed_f0,
)
from crochet_ai.physical_projection import PhysicalSemanticProjection
from crochet_ai.validation import SemanticValidator


def _policy() -> dict[str, object]:
    return {
        "profile": "FORWARD_F0_AUDIT_POLICY_V1",
        "max_replay_objective_evaluations": 5000,
        "max_contact_pair_evaluations": 500_000,
        "coordinate_abs_tolerance_mm": 0.0,
        "force_abs_tolerance_n": 0.0,
        "energy_abs_tolerance_n_mm": 0.0,
        "tolerance_owner": "synthetic test fixture",
        "tolerance_rationale": "exact deterministic replay assertion",
        "validation_path": "tests/test_forward_f0_audit.py",
    }


def _case() -> tuple[
    PhysicalSemanticProjection, dict[str, object], object, dict[str, object], SemanticValidator
]:
    request = f0_request()
    design = request["design_spec"]
    material = request["material_profile"]
    ir = request["crochet_ir"]
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={material["profile_id"]: material},
    )
    projection = PhysicalSemanticProjection(ir, material, validator=validator)
    recipe = admit_closed_f0_recipe(request["forward_run"])
    result = run_closed_f0(projection, material, recipe, validator=validator)
    assert result["status"] == "CONVERGED"
    return projection, material, recipe, result, validator


def _resign_result(result: dict[str, object]) -> None:
    payload = {key: value for key, value in result.items() if key != "sha256"}
    result["sha256"] = sha256(
        b"Crochet.AI\0FORWARD_CLOSED_F0_V1\0" + jcs_bytes(payload)
    ).hexdigest()


def test_complete_successful_f0_is_replayed_as_diagnostic_only() -> None:
    projection, material, recipe, result, validator = _case()
    audited = audit_closed_f0(
        projection,
        cast(dict[str, object], material),
        recipe,
        result,
        validator=validator,
        policy=_policy(),
    )
    assert audited["status"] == "PASS"
    assert audited["authenticity"] == "NOT_ESTABLISHED"
    assert audited["verification_state"] == "NOT_VERIFIED"
    assert audited["physical_status"] == "UNTESTED"
    assert audited["constitutive_status"] == "HYPOTHESIS"


@pytest.mark.parametrize("coordinate_tolerance", [0.0, 1e12])
@pytest.mark.parametrize("target", ["winner", "start"])
def test_rehashed_coordinate_tamper_fails_independent_replay(
    coordinate_tolerance: float, target: str
) -> None:
    projection, material, recipe, result, validator = _case()
    forged = deepcopy(result)
    container = forged if target == "winner" else cast(list[dict[str, object]], forged["starts"])[0]
    coordinates = cast(list[dict[str, object]], container["coordinates_mm"])
    position = cast(list[float], coordinates[0]["position_mm"])
    position[0] += 0.25
    _resign_result(forged)
    policy = _policy()
    policy["coordinate_abs_tolerance_mm"] = coordinate_tolerance
    audited = audit_closed_f0(
        projection,
        cast(dict[str, object], material),
        recipe,
        forged,
        validator=validator,
        policy=policy,
    )
    assert audited["status"] == "FAIL"
    assert str(audited["reason"]).startswith("evidence_mismatch:")


def test_contact_budget_exhaustion_is_indeterminate() -> None:
    projection, material, recipe, result, validator = _case()
    policy = _policy()
    policy["max_contact_pair_evaluations"] = 1
    audited = audit_closed_f0(
        projection,
        cast(dict[str, object], material),
        recipe,
        result,
        validator=validator,
        policy=policy,
    )
    assert audited["status"] == "INDETERMINATE"
    assert audited["reason"] == "contact_work_budget_exhausted"
    assert audited["replay_work"]["objective_evaluations"] == 1
    assert audited["replay_work"]["contact_pair_evaluations"] == 1


def test_audit_objective_budget_retains_actual_consumed_work() -> None:
    projection, material, recipe, result, validator = _case()
    policy = _policy()
    policy["max_replay_objective_evaluations"] = 1
    audited = audit_closed_f0(
        projection, material, recipe, result, validator=validator, policy=policy
    )
    assert audited["status"] == "INDETERMINATE"
    assert audited["replay_work"]["objective_evaluations"] == 1
    assert audited["replay_work"]["contact_pair_evaluations"] > 0


def _accepted_step_fixture() -> tuple[
    dict[str, tuple[float, float, float]], list[dict[str, object]], object
]:
    initial = {"vertex": (1e-9, 0.0, 0.0)}
    inputs = _inputs()
    inputs = replace(
        inputs,
        tolerances=tuple(
            (name, replace(value, value=1e-12)) if name == "force_residual_n" else (name, value)
            for name, value in inputs.tolerances
        ),
    )
    moved = {"vertex": (0.0, 0.0, 0.0)}
    before_energy, after_energy = 0.5e-18, 0.0
    step, relative = dist(initial["vertex"], moved["vertex"]), before_energy
    trace: list[dict[str, object]] = [
        {
            "kind": "ACCEPTED_STEP",
            "alpha_mm_per_n": 1.0,
            "energy_before_n_mm": before_energy,
            "energy_after_n_mm": after_energy,
            "position_step_mm": step,
            "relative_energy_change": relative,
            "before_sha256": _point_hash(initial),
            "after_sha256": _point_hash(moved),
            "path_status": "SAFE",
            "path_reason": "fixture_clear",
        },
        {
            "kind": "STATIONARY_CHECK",
            "energy_n_mm": after_energy,
            "maximum_force_n": 0.0,
            "position_step_mm": step,
            "relative_energy_change": relative,
            "coordinates_sha256": _point_hash(moved),
        },
        {
            "kind": "STATIONARY_CHECK",
            "energy_n_mm": after_energy,
            "maximum_force_n": 0.0,
            "position_step_mm": step,
            "relative_energy_change": 0.0,
            "coordinates_sha256": _point_hash(moved),
        },
    ]
    return initial, trace, inputs


def test_auditor_replays_accepted_armijo_step_and_rejects_alpha_or_omission() -> None:
    initial, trace, inputs = _accepted_step_fixture()

    def evaluate(points: dict[str, tuple[float, float, float]]) -> _Objective:
        x = points["vertex"][0]
        energy = 0.5 * x * x
        forces = {"vertex": (-x, 0.0, 0.0)}
        return _Objective(energy, forces, hypot(*forces["vertex"]), {"energy_n_mm": energy})

    def certify(
        _start: dict[str, tuple[float, float, float]], _end: dict[str, tuple[float, float, float]]
    ) -> tuple[str, str]:
        return "SAFE", "fixture_clear"

    actual: dict[str, object] = {
        "status": "CONVERGED",
        "reason": "all_stationary_predicates_pass",
        "start_index": 0,
        "optimizer_iterations": 1,
        "energy_evaluations": 3,
        "line_search_trials": 1,
        "stationary_checks": 2,
        "last_step_mm": 1e-9,
        "relative_energy_change": 0.0,
        "maximum_force_n": 0.0,
        "energy_n_mm": 0.0,
        "coordinates_mm": [{"attachment_location_id": "vertex", "position_mm": [0.0, 0.0, 0.0]}],
        "trace": trace,
    }
    points, final, _stats = _replay_start(
        initial, actual, 0, evaluate, certify, inputs, _policy_object()
    )
    assert points == {"vertex": (0.0, 0.0, 0.0)}
    assert final.energy_n_mm == 0.0
    altered = deepcopy(actual)
    cast(list[dict[str, object]], altered["trace"])[0]["alpha_mm_per_n"] = 0.5
    with pytest.raises(F0AuditError, match="evidence_mismatch:trace/0"):
        _replay_start(initial, altered, 0, evaluate, certify, inputs, _policy_object())
    omitted = deepcopy(actual)
    omitted["trace"] = trace[1:]
    with pytest.raises(F0AuditError, match="evidence_mismatch:trace/0"):
        _replay_start(initial, omitted, 0, evaluate, certify, inputs, _policy_object())


def _policy_object():
    from crochet_ai.forward_f0_audit import _admit_policy

    return _admit_policy(_policy())


def test_replay_rejects_claimed_success_beyond_per_start_objective_budget() -> None:
    initial, trace, inputs = _accepted_step_fixture()
    inputs = replace(inputs, max_energy_evaluations=1)

    def evaluate(points: dict[str, tuple[float, float, float]]) -> _Objective:
        x = points["vertex"][0]
        forces = {"vertex": (-x, 0.0, 0.0)}
        return _Objective(0.5 * x * x, forces, hypot(*forces["vertex"]), {})

    with pytest.raises(F0AuditError, match="trace_claimed_success_after_objective_budget"):
        _replay_start(
            initial,
            {"trace": trace},
            0,
            evaluate,
            lambda _start, _end: ("SAFE", "fixture_clear"),
            inputs,
            _policy_object(),
        )


def test_audit_rejects_oversize_recipe_before_parsing() -> None:
    projection, material, _recipe, result, validator = _case()
    recipe = SimpleNamespace(canonical_bytes=b" " * 2_000_001, sha256="a" * 64)
    audited = audit_closed_f0(
        projection, material, recipe, result, validator=validator, policy=_policy()
    )
    assert audited["status"] == "FAIL"
    assert audited["reason"] == "recipe_byte_budget_exceeded"
    assert audited["replay_work"]["objective_evaluations"] == 0


@pytest.mark.parametrize("kind", ["deep", "wide", "cyclic"])
def test_audit_rejects_excessive_result_complexity_before_hashing(kind: str) -> None:
    projection, material, recipe, result, validator = _case()
    if kind == "wide":
        result["untrusted"] = [0] * 100_001
    elif kind == "cyclic":
        result["untrusted"] = result
    else:
        nested: list[object] = []
        for _index in range(65):
            nested = [nested]
        result["untrusted"] = nested
    audited = audit_closed_f0(
        projection, material, recipe, result, validator=validator, policy=_policy()
    )
    assert audited["status"] == "FAIL"
    assert audited["reason"] == "audit_input_complexity_exceeded"
    assert audited["replay_work"]["objective_evaluations"] == 0


def test_audit_rejects_unsafe_integer_tolerance_without_secondary_exception() -> None:
    projection, material, recipe, result, validator = _case()
    policy = _policy()
    policy["coordinate_abs_tolerance_mm"] = 2**10_000
    audited = audit_closed_f0(
        projection, material, recipe, result, validator=validator, policy=policy
    )
    assert audited["status"] == "FAIL"
    assert audited["reason"] == "audit_policy_tolerance_invalid"


def test_rehashed_unsupported_release_claim_is_rejected() -> None:
    projection, material, recipe, result, validator = _case()
    result["release_verified"] = True
    _resign_result(result)
    audited = audit_closed_f0(
        projection, material, recipe, result, validator=validator, policy=_policy()
    )
    assert audited["status"] == "FAIL"
    assert audited["reason"] == "result_fields_invalid"
