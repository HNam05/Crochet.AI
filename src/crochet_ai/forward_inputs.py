"""Strict, target-free admission for versioned forward stretch-prototype inputs.

This module validates configuration only. It does not build a graph, run a
simulation, or make any F0 completeness, convergence, or physical-accuracy claim.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import cast

from .canonical import jcs_bytes
from .json_types import JSONValue

PROFILE = "FORWARD_RUN_INPUTS_V1"
_SAFE_INTEGER = 9_007_199_254_740_991
_BUDGETS = (
    "max_initializations",
    "max_initialization_vertices",
    "max_line_search_trials",
    "max_optimizer_iterations",
    "max_energy_evaluations",
    "max_linear_iterations",
    "max_contact_pairs_evaluated",
)
_TOLERANCES = {
    "force_residual_n": "N",
    "position_step_mm": "mm",
    "relative_energy_change": "dimensionless",
    "contact_penetration_mm": "mm",
    "volume_orientation_epsilon_mm3": "mm^3",
    "mode_equivalence_rms_mm": "mm",
}


class ForwardInputError(ValueError):
    """A rejected run input with a stable machine-readable reason."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ForwardTolerance:
    value: float
    unit: str
    rationale: str
    owner: str
    validation_path_id: str


@dataclass(frozen=True, slots=True)
class ForwardInputs:
    """Admitted stretch-prototype inputs; hash binds loading, model and config."""

    loading_profile_id: str
    loading_state: str
    model_profile_id: str
    source_provenance_id: str
    stiffness_course_n_per_mm: float
    stiffness_wale_n_per_mm: float
    max_initializations: int
    max_initialization_vertices: int
    max_line_search_trials: int
    max_optimizer_iterations: int
    max_energy_evaluations: int
    max_linear_iterations: int
    max_contact_pairs_evaluated: int
    tolerances: tuple[tuple[str, ForwardTolerance], ...]
    canonical_bytes: bytes
    sha256: str


def admit_forward_inputs(
    loading: Mapping[str, object],
    model_profile: Mapping[str, object],
    config: Mapping[str, object],
) -> ForwardInputs:
    """Admit one unloaded, unpressurized forward stretch-prototype configuration.

    Each document is closed and versioned. Callers must state the loading and
    both anisotropic stiffness coefficients explicitly; no defaults are used.
    """

    loading_value = _object(loading, "loading")
    model_value = _object(model_profile, "model_profile")
    config_value = _object(config, "config")
    _closed(loading_value, {"schema_version", "loading_profile_id", "state"}, "loading")
    _closed(
        model_value,
        {
            "schema_version",
            "model_profile_id",
            "status",
            "source_provenance_id",
            "stiffness_course_n_per_mm",
            "stiffness_wale_n_per_mm",
        },
        "model_profile",
    )
    _closed(
        config_value,
        {"schema_version", "config_id", "model_version", "work_budgets", "tolerances"},
        "config",
    )

    _version(loading_value, "loading")
    _version(model_value, "model_profile")
    _version(config_value, "config")
    loading_id = _identifier(loading_value.get("loading_profile_id"), "loading.profile_id")
    loading_state = loading_value.get("state")
    if loading_state != "UNLOADED_UNPRESSURIZED":
        raise ForwardInputError("loading.unsupported_state")

    model_id = _identifier(model_value.get("model_profile_id"), "model_profile.profile_id")
    provenance_id = _identifier(
        model_value.get("source_provenance_id"), "model_profile.source_provenance_id"
    )
    if model_value.get("status") != "HYPOTHESIS":
        raise ForwardInputError("model_profile.status_must_be_hypothesis")
    course_stiffness = _positive_number(
        model_value.get("stiffness_course_n_per_mm"), "model_profile.stiffness_course_n_per_mm"
    )
    wale_stiffness = _positive_number(
        model_value.get("stiffness_wale_n_per_mm"), "model_profile.stiffness_wale_n_per_mm"
    )
    _identifier(config_value.get("config_id"), "config.config_id")
    if config_value.get("model_version") != "F0_STRETCH_PROTOTYPE":
        raise ForwardInputError("config.unsupported_model_version")
    raw_budgets = _object(config_value.get("work_budgets"), "config.work_budgets")
    _closed(raw_budgets, set(_BUDGETS), "config.work_budgets")
    budgets = {
        name: _positive_integer(raw_budgets.get(name), f"work_budgets.{name}") for name in _BUDGETS
    }

    raw_tolerances = _object(config_value.get("tolerances"), "config.tolerances")
    _closed(raw_tolerances, set(_TOLERANCES), "config.tolerances")
    tolerances: dict[str, ForwardTolerance] = {}
    admitted_tolerances: dict[str, dict[str, object]] = {}
    for name, expected_unit in _TOLERANCES.items():
        raw = _object(raw_tolerances.get(name), f"tolerances.{name}")
        _closed(
            raw,
            {"value", "unit", "rationale", "owner", "validation_path_id"},
            f"tolerances.{name}",
        )
        value = _positive_number(raw.get("value"), f"tolerances.{name}.value")
        unit = raw.get("unit")
        if unit != expected_unit:
            raise ForwardInputError(f"tolerances.{name}.unit_mismatch")
        rationale = _description(raw.get("rationale"), f"tolerances.{name}.rationale")
        owner = _identifier(raw.get("owner"), f"tolerances.{name}.owner")
        path_id = _identifier(
            raw.get("validation_path_id"), f"tolerances.{name}.validation_path_id"
        )
        tolerances[name] = ForwardTolerance(value, expected_unit, rationale, owner, path_id)
        admitted_tolerances[name] = {
            "value": value,
            "unit": expected_unit,
            "rationale": rationale,
            "owner": owner,
            "validation_path_id": path_id,
        }

    admitted: dict[str, object] = {
        "profile": PROFILE,
        "loading": {
            "schema_version": "1.0.0",
            "loading_profile_id": loading_id,
            "state": loading_state,
        },
        "model_profile": {
            "schema_version": "1.0.0",
            "model_profile_id": model_id,
            "status": "HYPOTHESIS",
            "source_provenance_id": provenance_id,
            "stiffness_course_n_per_mm": course_stiffness,
            "stiffness_wale_n_per_mm": wale_stiffness,
        },
        "config": {
            "schema_version": "1.0.0",
            "config_id": _identifier(config_value.get("config_id"), "config.config_id"),
            "model_version": "F0_STRETCH_PROTOTYPE",
            "work_budgets": budgets,
            "tolerances": admitted_tolerances,
        },
    }
    encoded = jcs_bytes(cast(JSONValue, admitted))  # validates I-JSON and safe numeric forms.
    digest = sha256(b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + encoded).hexdigest()
    return ForwardInputs(
        loading_id,
        "UNLOADED_UNPRESSURIZED",
        model_id,
        provenance_id,
        course_stiffness,
        wale_stiffness,
        budgets["max_initializations"],
        budgets["max_initialization_vertices"],
        budgets["max_line_search_trials"],
        budgets["max_optimizer_iterations"],
        budgets["max_energy_evaluations"],
        budgets["max_linear_iterations"],
        budgets["max_contact_pairs_evaluated"],
        tuple(tolerances.items()),
        encoded,
        digest,
    )


def _object(value: object, path: str) -> dict[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ForwardInputError(f"{path}.must_be_object")
    return dict(value)


def _closed(value: dict[str, object], expected: set[str], path: str) -> None:
    unknown = set(value) - expected
    if unknown:
        key = min(unknown)
        if any(token in key.casefold() for token in ("target", "embedding", "correspondence")):
            raise ForwardInputError("input.prohibited_target_field")
        raise ForwardInputError(f"{path}.unknown_field")
    if set(value) != expected:
        raise ForwardInputError(f"{path}.missing_field")


def _version(value: dict[str, object], path: str) -> None:
    if value.get("schema_version") != "1.0.0":
        raise ForwardInputError(f"{path}.unsupported_version")


def _identifier(value: object, path: str) -> str:
    if not isinstance(value, str) or not value or not value.strip():
        raise ForwardInputError(f"{path}.invalid_identifier")
    return value


def _description(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ForwardInputError(f"{path}.missing_provenance")
    return value


def _positive_number(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ForwardInputError(f"{path}.must_be_positive_number")
    if isinstance(value, int) and abs(value) > _SAFE_INTEGER:
        raise ForwardInputError(f"{path}.unsafe_integer")
    number = float(value)
    if not math.isfinite(number):
        raise ForwardInputError(f"{path}.non_finite")
    if number <= 0:
        raise ForwardInputError(f"{path}.must_be_positive_number")
    return number


def _positive_integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ForwardInputError(f"{path}.must_be_positive_integer")
    if value > _SAFE_INTEGER:
        raise ForwardInputError(f"{path}.unsafe_integer")
    if value <= 0:
        raise ForwardInputError(f"{path}.must_be_positive_integer")
    return value
