from __future__ import annotations

from copy import deepcopy

import pytest

from crochet_ai.forward_inputs import ForwardInputError, admit_forward_inputs


def _documents() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    loading: dict[str, object] = {
        "schema_version": "1.0.0",
        "loading_profile_id": "loading-unloaded-v1",
        "state": "UNLOADED_UNPRESSURIZED",
    }
    model: dict[str, object] = {
        "schema_version": "1.0.0",
        "model_profile_id": "f0-hypothesis-v1",
        "status": "HYPOTHESIS",
        "source_provenance_id": "study-2026-01",
        "stiffness_course_n_per_mm": 0.8,
        "stiffness_wale_n_per_mm": 0.4,
    }
    units = {
        "force_residual_n": "N",
        "position_step_mm": "mm",
        "relative_energy_change": "dimensionless",
        "contact_penetration_mm": "mm",
        "volume_orientation_epsilon_mm3": "mm^3",
        "mode_equivalence_rms_mm": "mm",
    }
    tolerances = {
        name: {
            "value": 0.01,
            "unit": unit,
            "rationale": f"Declared {name} threshold.",
            "owner": "forward-model",
            "validation_path_id": f"fixture-{name}",
        }
        for name, unit in units.items()
    }
    config: dict[str, object] = {
        "schema_version": "1.0.0",
        "config_id": "f0-run-v1",
        "model_version": "F0_STRETCH_PROTOTYPE",
        "work_budgets": {
            "max_initializations": 2,
            "max_initialization_vertices": 100,
            "max_line_search_trials": 8,
            "max_optimizer_iterations": 100,
            "max_energy_evaluations": 200,
            "max_linear_iterations": 300,
            "max_contact_pairs_evaluated": 400,
        },
        "tolerances": tolerances,
    }
    return loading, model, config


def _reject(mutator: object, reason: str) -> None:
    loading, model, config = _documents()
    assert callable(mutator)
    mutator(loading, model, config)
    with pytest.raises(ForwardInputError) as error:
        admit_forward_inputs(loading, model, config)
    assert error.value.reason == reason


def test_admits_explicit_hypothesis_and_returns_immutable_target_free_result() -> None:
    loading, model, config = _documents()
    result = admit_forward_inputs(loading, model, config)
    assert result.loading_state == "UNLOADED_UNPRESSURIZED"
    assert result.stiffness_course_n_per_mm == 0.8
    assert result.stiffness_wale_n_per_mm == 0.4
    assert len(result.tolerances) == 6
    assert len(result.sha256) == 64
    with pytest.raises(AttributeError):
        result.loading_state = "GRAVITY"  # type: ignore[misc]


def test_hash_is_invariant_to_object_member_order() -> None:
    loading, model, config = _documents()
    first = admit_forward_inputs(loading, model, config)
    reversed_config = dict(reversed(list(config.items())))
    raw_budgets = config["work_budgets"]
    assert isinstance(raw_budgets, dict)
    reversed_config["work_budgets"] = dict(reversed(list(raw_budgets.items())))
    raw_tolerances = config["tolerances"]
    assert isinstance(raw_tolerances, dict)
    reversed_config["tolerances"] = dict(reversed(list(raw_tolerances.items())))
    second = admit_forward_inputs(dict(reversed(list(loading.items()))), model, reversed_config)
    assert first.canonical_bytes == second.canonical_bytes
    assert first.sha256 == second.sha256


def test_hash_binds_each_admitted_input() -> None:
    baseline = admit_forward_inputs(*_documents()).sha256
    loading, model, config = _documents()
    changed_model = deepcopy(model)
    changed_model["stiffness_course_n_per_mm"] = 0.9
    assert admit_forward_inputs(loading, changed_model, config).sha256 != baseline
    changed_loading = deepcopy(loading)
    changed_loading["loading_profile_id"] = "another-explicit-loading"
    assert admit_forward_inputs(changed_loading, model, config).sha256 != baseline
    changed_config = deepcopy(config)
    changed_config["config_id"] = "another-f0-config"
    assert admit_forward_inputs(loading, model, changed_config).sha256 != baseline
    changed_budget = deepcopy(config)
    changed_budget["work_budgets"]["max_initialization_vertices"] = 101
    assert admit_forward_inputs(loading, model, changed_budget).sha256 != baseline
    changed_budget["work_budgets"]["max_line_search_trials"] = 9
    assert admit_forward_inputs(loading, model, changed_budget).sha256 != baseline


def test_equal_stiffness_values_remain_separate_admitted_coefficients() -> None:
    loading, model, config = _documents()
    model["stiffness_wale_n_per_mm"] = model["stiffness_course_n_per_mm"]
    result = admit_forward_inputs(loading, model, config)
    assert result.stiffness_course_n_per_mm == 0.8
    assert result.stiffness_wale_n_per_mm == 0.8
    assert b"stiffness_course_n_per_mm" in result.canonical_bytes
    assert b"stiffness_wale_n_per_mm" in result.canonical_bytes


@pytest.mark.parametrize(
    ("mutator", "reason"),
    [
        (
            lambda loading_doc, model_doc, config_doc: loading_doc.update(state="GRAVITY"),
            "loading.unsupported_state",
        ),
        (
            lambda loading_doc, model_doc, config_doc: model_doc.update(status="CALIBRATED"),
            "model_profile.status_must_be_hypothesis",
        ),
        (
            lambda loading_doc, model_doc, config_doc: model_doc.pop("source_provenance_id"),
            "model_profile.missing_field",
        ),
        (
            lambda loading_doc, model_doc, config_doc: loading_doc.update(target_mesh={}),
            "input.prohibited_target_field",
        ),
        (
            lambda loading_doc, model_doc, config_doc: config_doc.update(embedding={}),
            "input.prohibited_target_field",
        ),
        (
            lambda loading_doc, model_doc, config_doc: model_doc.update(extra="unsupported"),
            "model_profile.unknown_field",
        ),
        (
            lambda loading_doc, model_doc, config_doc: loading_doc.update(schema_version="2.0.0"),
            "loading.unsupported_version",
        ),
        (
            lambda loading_doc, model_doc, config_doc: config_doc["work_budgets"].update(
                max_linear_iterations=True
            ),
            "work_budgets.max_linear_iterations.must_be_positive_integer",
        ),
        (
            lambda loading_doc, model_doc, config_doc: config_doc["work_budgets"].update(
                max_linear_iterations=0
            ),
            "work_budgets.max_linear_iterations.must_be_positive_integer",
        ),
        (
            lambda loading_doc, model_doc, config_doc: config_doc["work_budgets"].update(
                max_linear_iterations=9_007_199_254_740_992
            ),
            "work_budgets.max_linear_iterations.unsafe_integer",
        ),
        (
            lambda loading_doc, model_doc, config_doc: config_doc["work_budgets"].update(
                max_initialization_vertices=0
            ),
            "work_budgets.max_initialization_vertices.must_be_positive_integer",
        ),
        (
            lambda loading_doc, model_doc, config_doc: config_doc["work_budgets"].update(
                max_line_search_trials=True
            ),
            "work_budgets.max_line_search_trials.must_be_positive_integer",
        ),
        (
            lambda loading_doc, model_doc, config_doc: model_doc.update(
                stiffness_course_n_per_mm=True
            ),
            "model_profile.stiffness_course_n_per_mm.must_be_positive_number",
        ),
        (
            lambda loading_doc, model_doc, config_doc: model_doc.update(
                stiffness_course_n_per_mm=float("nan")
            ),
            "model_profile.stiffness_course_n_per_mm.non_finite",
        ),
        (
            lambda loading_doc, model_doc, config_doc: model_doc.update(
                stiffness_course_n_per_mm=0
            ),
            "model_profile.stiffness_course_n_per_mm.must_be_positive_number",
        ),
        (
            lambda loading_doc, model_doc, config_doc: config_doc["tolerances"][
                "force_residual_n"
            ].update(value=float("inf")),
            "tolerances.force_residual_n.value.non_finite",
        ),
        (
            lambda loading_doc, model_doc, config_doc: config_doc["tolerances"][
                "force_residual_n"
            ].update(unit="mm"),
            "tolerances.force_residual_n.unit_mismatch",
        ),
        (
            lambda loading_doc, model_doc, config_doc: config_doc["tolerances"][
                "force_residual_n"
            ].pop("validation_path_id"),
            "tolerances.force_residual_n.missing_field",
        ),
        (
            lambda loading_doc, model_doc, config_doc: config_doc["tolerances"][
                "force_residual_n"
            ].update(rationale=" "),
            "tolerances.force_residual_n.rationale.missing_provenance",
        ),
    ],
)
def test_rejects_unsupported_or_ambiguous_inputs(mutator: object, reason: str) -> None:
    _reject(mutator, reason)
