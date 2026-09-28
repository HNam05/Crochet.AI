"""One deterministic, target-free experimental stretch descent step.

This is a bounded prototype operation, not a complete F0 solver or a
convergence/geometry verification result.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from hashlib import sha256

from .canonical import jcs_bytes
from .forward_forces import (
    ForwardForceError,
    _evaluate_stretch_terms_at_coordinates,
    _validate_initialization_integrity,
    _validate_term,
)
from .forward_initialization import ForwardInitialization
from .forward_inputs import ForwardInputs, ForwardTolerance
from .forward_stretch import ForwardStretchTerms, StretchTerm
from .json_types import JSONValue

PROFILE = "FORWARD_RELAX_STEP_V1"
ARMIJO_C = 1e-4


class ForwardRelaxError(ValueError):
    """Invalid or inconsistent relaxation-step input."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ForwardRelaxResult:
    """Immutable result of one bounded experimental descent attempt."""

    status: str
    projection_sha256: str
    material_sha256: str
    forward_inputs_sha256: str
    initialization_sha256: str
    coordinates_mm: tuple[tuple[str, tuple[float, float, float]], ...] | None
    baseline_energy_n_mm: float | None
    trial_energies_n_mm: tuple[float | None, ...]
    baseline_maximum_force_n: float | None
    trial_maximum_force_n: float | None
    step_mm: float | None
    optimizer_iterations: int
    energy_evaluations: int
    line_search_trials: int
    alpha_initial_mm_per_n: float | None
    accepted_alpha_mm_per_n: float | None
    alpha_trace_mm_per_n: tuple[float, ...]
    armijo_c: float
    canonical_bytes: bytes
    sha256: str


def relax_one_stretch_step(
    terms: ForwardStretchTerms,
    initialization: ForwardInitialization,
    inputs: ForwardInputs,
) -> ForwardRelaxResult:
    """Attempt exactly one deterministic stretch-only step with Armijo search.

    The only coordinate source is the admitted target-free initialization.
    Each baseline or trial kernel evaluation consumes one energy-evaluation
    budget unit. A call consumes one optimizer-iteration unit.
    """

    _validate_artifacts(terms, initialization, inputs)
    return _relax_coordinates_one_step(
        terms,
        dict(initialization.coordinates_mm),
        inputs,
        inputs.max_energy_evaluations,
        inputs.max_line_search_trials,
        initialization.sha256,
    )


def _relax_coordinates_one_step(
    terms: ForwardStretchTerms,
    base: dict[str, tuple[float, float, float]],
    inputs: ForwardInputs,
    max_energy_evaluations: int,
    max_line_search_trials: int,
    initialization_sha256: str,
) -> ForwardRelaxResult:
    """Private one-step kernel shared with the multi-step driver."""

    _validate_coordinates(base)
    if not terms.terms or not all(isinstance(term, StretchTerm) for term in terms.terms):
        raise ForwardRelaxError("relax.terms_invalid")
    for term in terms.terms:
        _validate_term(term)

    if max_energy_evaluations < 1:
        return _result("BUDGET_EXHAUSTED", terms, None, None, (), None, None, None, None,
                       initialization_sha256=initialization_sha256)

    try:
        baseline_energy, baseline_forces, baseline_max_force = (
            _evaluate_stretch_terms_at_coordinates(terms.terms, base)
        )
    except ForwardForceError as error:
        if error.reason == "forces.zero_distance":
            return _result("NUMERICAL_FAILURE", terms, None, None, (), None, None, None, None,
                           optimizer_iterations=1, energy_evaluations=1,
                           initialization_sha256=initialization_sha256)
        raise ForwardRelaxError(error.reason) from error

    force_limit = _force_residual_limit(inputs)
    if baseline_max_force <= force_limit:
        return _result(
            "EXPERIMENTAL_INITIAL_STATIONARY", terms, base, baseline_energy, (),
            baseline_max_force, baseline_max_force, 0.0, None,
            optimizer_iterations=1, energy_evaluations=1,
            initialization_sha256=initialization_sha256,
        )

    if max_line_search_trials < 1:
        return _result(
            "BUDGET_EXHAUSTED", terms, None, baseline_energy, (), baseline_max_force,
            None, None, None, optimizer_iterations=1, energy_evaluations=1,
            initialization_sha256=initialization_sha256,
        )

    incident: dict[str, list[float]] = {location_id: [] for location_id in base}
    for term in terms.terms:
        incident[term.source_location_id].append(float(term.stiffness_n_per_mm))
        incident[term.target_location_id].append(float(term.stiffness_n_per_mm))
    try:
        maximum_incident = max(math.fsum(values) for values in incident.values())
        alpha = 1.0 / (2.0 * maximum_incident)
    except (OverflowError, ZeroDivisionError) as error:
        raise ForwardRelaxError("relax.step_size_invalid") from error
    if not math.isfinite(alpha) or alpha <= 0:
        return _result(
            "NUMERICAL_FAILURE", terms, None, baseline_energy, (), baseline_max_force,
            None, None, None, optimizer_iterations=1, energy_evaluations=1,
            initialization_sha256=initialization_sha256,
        )
    initial_alpha = alpha
    force_map = dict(baseline_forces)
    trial_energies: list[float | None] = []
    alpha_trace: list[float] = []
    evaluations = 1

    for _ in range(max_line_search_trials):
        if evaluations >= max_energy_evaluations:
            return _result(
                "BUDGET_EXHAUSTED", terms, None, baseline_energy, tuple(trial_energies),
                baseline_max_force, None, None, initial_alpha, alpha_trace=tuple(alpha_trace),
                optimizer_iterations=1, energy_evaluations=evaluations,
                line_search_trials=len(alpha_trace),
                initialization_sha256=initialization_sha256,
            )
        candidate: dict[str, tuple[float, float, float]] = {}
        changed = False
        try:
            for location_id in sorted(base):
                old = base[location_id]
                force = force_map[location_id]
                point = (
                    old[0] + alpha * force[0],
                    old[1] + alpha * force[1],
                    old[2] + alpha * force[2],
                )
                if any(not math.isfinite(value) for value in point):
                    candidate.clear()
                    break
                candidate[location_id] = point
                changed = changed or point != old
        except OverflowError:
            candidate.clear()
        if len(candidate) != len(base):
            alpha_trace.append(alpha)
            evaluations += 1
            trial_energies.append(None)
            alpha *= 0.5
            continue
        if not changed:
            alpha_trace.append(alpha)
            return _result(
                "NUMERICAL_FAILURE", terms, None, baseline_energy, tuple(trial_energies),
                baseline_max_force, None, None, initial_alpha, alpha_trace=tuple(alpha_trace),
                optimizer_iterations=1, energy_evaluations=evaluations,
                line_search_trials=len(alpha_trace),
                initialization_sha256=initialization_sha256,
            )
        alpha_trace.append(alpha)
        try:
            trial_energy, _trial_forces, trial_max_force = (
                _evaluate_stretch_terms_at_coordinates(terms.terms, candidate)
            )
            evaluations += 1
            trial_energies.append(trial_energy)
        except ForwardForceError as error:
            evaluations += 1
            trial_energies.append(None)
            if error.reason != "forces.zero_distance":
                return _result(
                    "NUMERICAL_FAILURE", terms, None, baseline_energy,
                    tuple(trial_energies), baseline_max_force, None, None,
                    initial_alpha, alpha_trace=tuple(alpha_trace),
                    optimizer_iterations=1, energy_evaluations=evaluations,
                    line_search_trials=len(alpha_trace),
                    initialization_sha256=initialization_sha256,
                )
            alpha *= 0.5
            continue

        force_square_sum = _finite_fsum(
            [component * component for _, force in baseline_forces for component in force]
        )
        armijo_bound = baseline_energy - ARMIJO_C * alpha * force_square_sum
        if (
            math.isfinite(armijo_bound)
            and trial_energy < baseline_energy
            and trial_energy <= armijo_bound
        ):
            step = max(math.dist(base[key], candidate[key]) for key in base)
            return _result(
                "EXPERIMENTAL_STEP_ACCEPTED", terms, candidate, baseline_energy,
                tuple(trial_energies), baseline_max_force, trial_max_force, step,
                initial_alpha, accepted_alpha=alpha, alpha_trace=tuple(alpha_trace),
                optimizer_iterations=1, energy_evaluations=evaluations,
                line_search_trials=len(alpha_trace),
                initialization_sha256=initialization_sha256,
            )
        alpha *= 0.5

    return _result(
        "LINE_SEARCH_FAILED", terms, None, baseline_energy, tuple(trial_energies),
        baseline_max_force, None, None, initial_alpha, alpha_trace=tuple(alpha_trace),
        optimizer_iterations=1, energy_evaluations=evaluations,
        line_search_trials=len(alpha_trace),
        initialization_sha256=initialization_sha256,
    )


def _validate_artifacts(
    terms: ForwardStretchTerms,
    initialization: ForwardInitialization,
    inputs: ForwardInputs,
) -> None:
    if not isinstance(terms, ForwardStretchTerms):
        raise ForwardRelaxError("relax.terms_type")
    if not isinstance(initialization, ForwardInitialization):
        raise ForwardRelaxError("relax.initialization_type")
    if not isinstance(inputs, ForwardInputs):
        raise ForwardRelaxError("relax.inputs_type")
    if terms.status != "EXPERIMENTAL_STRETCH_TERMS":
        raise ForwardRelaxError("relax.terms_status")
    if initialization.status != "EXPERIMENTAL_INITIALIZATION":
        raise ForwardRelaxError("relax.initialization_status")
    for digest in (terms.projection_sha256, terms.material_sha256, terms.forward_inputs_sha256,
                   initialization.projection_sha256, initialization.material_sha256,
                   initialization.forward_inputs_sha256, inputs.sha256):
        if not isinstance(digest, str) or len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise ForwardRelaxError("relax.hash_invalid")
    if terms.projection_sha256 != initialization.projection_sha256:
        raise ForwardRelaxError("relax.projection_hash_mismatch")
    if terms.material_sha256 != initialization.material_sha256:
        raise ForwardRelaxError("relax.material_hash_mismatch")
    if (
        terms.forward_inputs_sha256 != initialization.forward_inputs_sha256
        or inputs.sha256 != terms.forward_inputs_sha256
    ):
        raise ForwardRelaxError("relax.inputs_hash_mismatch")
    expected_inputs = sha256(
        b"Crochet.AI\0FORWARD_RUN_INPUTS_V1\0" + inputs.canonical_bytes
    ).hexdigest()
    if expected_inputs != inputs.sha256:
        raise ForwardRelaxError("relax.inputs_integrity")
    try:
        _validate_initialization_integrity(initialization)
    except ForwardForceError as error:
        raise ForwardRelaxError(error.reason) from error
    for name in ("max_optimizer_iterations", "max_energy_evaluations", "max_line_search_trials"):
        value = getattr(inputs, name)
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
            or value > 9_007_199_254_740_991
        ):
            raise ForwardRelaxError("relax.budget_invalid")


def _force_residual_limit(inputs: ForwardInputs) -> float:
    matches = [value for name, value in inputs.tolerances if name == "force_residual_n"]
    if len(matches) != 1 or not isinstance(matches[0], ForwardTolerance):
        raise ForwardRelaxError("relax.force_tolerance_missing")
    tolerance = matches[0]
    if tolerance.unit != "N" or not math.isfinite(tolerance.value) or tolerance.value <= 0:
        raise ForwardRelaxError("relax.force_tolerance_invalid")
    return tolerance.value


def _validate_coordinates(coordinates: dict[str, tuple[float, float, float]]) -> None:
    if not coordinates or any(
        not isinstance(key, str)
        or not key
        or len(point) != 3
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in point
        )
        for key, point in coordinates.items()
    ):
        raise ForwardRelaxError("relax.coordinates_invalid")


def _finite_fsum(values: list[float]) -> float:
    try:
        result = math.fsum(values)
    except OverflowError as error:
        raise ForwardRelaxError("relax.force_norm_non_finite") from error
    if not math.isfinite(result):
        raise ForwardRelaxError("relax.force_norm_non_finite")
    return result


def _result(
    status: str,
    terms: ForwardStretchTerms,
    coordinates: dict[str, tuple[float, float, float]] | None,
    baseline_energy: float | None,
    trial_energies: tuple[float | None, ...] | None,
    baseline_max_force: float | None,
    trial_max_force: float | None,
    step_mm: float | None,
    initial_alpha: float | None,
    accepted_alpha: float | None = None,
    alpha_trace: tuple[float, ...] = (),
    optimizer_iterations: int = 0,
    energy_evaluations: int = 0,
    line_search_trials: int = 0,
    *,
    initialization_sha256: str,
) -> ForwardRelaxResult:
    coordinate_rows = None if coordinates is None else tuple(sorted(coordinates.items()))
    energies = () if trial_energies is None else trial_energies
    payload: dict[str, JSONValue] = {
        "profile": PROFILE,
        "status": status,
        "projection_sha256": terms.projection_sha256,
        "material_sha256": terms.material_sha256,
        "forward_inputs_sha256": terms.forward_inputs_sha256,
        "initialization_sha256": initialization_sha256,
        "coordinates_mm": None if coordinate_rows is None else [
            {"attachment_location_id": key, "xyz_mm": list(point)} for key, point in coordinate_rows
        ],
        "baseline_energy_n_mm": baseline_energy,
        "trial_energies_n_mm": list(energies),
        "baseline_maximum_force_n": baseline_max_force,
        "trial_maximum_force_n": trial_max_force,
        "step_mm": step_mm,
        "optimizer_iterations": optimizer_iterations,
        "energy_evaluations": energy_evaluations,
        "line_search_trials": line_search_trials,
        "alpha_initial_mm_per_n": initial_alpha,
        "accepted_alpha_mm_per_n": accepted_alpha,
        "alpha_trace_mm_per_n": list(alpha_trace),
        "armijo_c": ARMIJO_C,
    }
    encoded = jcs_bytes(payload)
    digest = sha256(b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + encoded).hexdigest()
    return ForwardRelaxResult(
        status, terms.projection_sha256, terms.material_sha256, terms.forward_inputs_sha256,
        initialization_sha256,
        coordinate_rows, baseline_energy, energies, baseline_max_force, trial_max_force,
        step_mm, optimizer_iterations, energy_evaluations, line_search_trials,
        initial_alpha, accepted_alpha, alpha_trace, ARMIJO_C, encoded, digest,
    )
