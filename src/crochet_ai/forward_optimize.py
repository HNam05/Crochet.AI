"""Target-free multi-step driver for the experimental stretch prototype."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from .canonical import jcs_bytes
from .forward_initialization import ForwardInitialization
from .forward_inputs import ForwardInputs
from .forward_relax import (
    ForwardRelaxError,
    ForwardRelaxResult,
    _force_residual_limit,
    _relax_coordinates_one_step,
    _validate_artifacts,
)
from .forward_stretch import ForwardStretchTerms, StretchTerm
from .json_types import JSONValue

PROFILE = "FORWARD_STRETCH_OPTIMIZATION_V1"


class ForwardOptimizeError(ValueError):
    """Invalid or inconsistent multi-step stretch input."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ForwardOptimizeIteration:
    """One immutable local step trace, including rejected trial evaluations."""

    status: str
    baseline_energy_n_mm: float | None
    trial_energies_n_mm: tuple[float | None, ...]
    baseline_maximum_force_n: float | None
    trial_maximum_force_n: float | None
    accepted_alpha_mm_per_n: float | None
    alpha_trace_mm_per_n: tuple[float, ...]
    energy_evaluations: int
    line_search_trials: int


@dataclass(frozen=True, slots=True)
class ForwardOptimizeResult:
    """Immutable force-balance result; it does not assert F0 or physical validity."""

    status: str
    projection_sha256: str
    material_sha256: str
    forward_inputs_sha256: str
    initialization_sha256: str
    coordinates_mm: tuple[tuple[str, tuple[float, float, float]], ...] | None
    maximum_force_n: float | None
    iterations: tuple[ForwardOptimizeIteration, ...]
    optimizer_iterations: int
    energy_evaluations: int
    line_search_trials: int
    canonical_bytes: bytes
    sha256: str


def optimize_stretch_prototype(
    terms: ForwardStretchTerms,
    initialization: ForwardInitialization,
    inputs: ForwardInputs,
) -> ForwardOptimizeResult:
    """Run bounded stretch descent until force balance or explicit failure.

    The final EXPERIMENTAL_FORCE_BALANCED state means only that this
    prototype's stretch forces meet the declared force-residual tolerance. It
    does not evaluate contact, shear, bending, boundary, pressure, F0 validity,
    or physical accuracy.
    """

    try:
        _validate_artifacts(terms, initialization, inputs)
    except ForwardRelaxError as error:
        raise ForwardOptimizeError(error.reason) from error
    if not isinstance(terms.terms, tuple) or not terms.terms:
        raise ForwardOptimizeError("optimize.terms_required")
    if not all(isinstance(term, StretchTerm) for term in terms.terms):
        raise ForwardOptimizeError("optimize.term_invalid")
    current = dict(initialization.coordinates_mm)
    force_tolerance = _force_residual_limit(inputs)
    traces: list[ForwardOptimizeIteration] = []
    iterations = 0
    energy_evaluations = 0
    line_search_trials = 0
    maximum_force: float | None = None

    while True:
        remaining_iterations = inputs.max_optimizer_iterations - iterations
        remaining_energy = inputs.max_energy_evaluations - energy_evaluations
        if remaining_iterations <= 0 or remaining_energy <= 0:
            return _result(
                "BUDGET_EXHAUSTED", terms, None, maximum_force, traces,
                iterations, energy_evaluations, line_search_trials,
                initialization.sha256,
            )

        try:
            step = _relax_coordinates_one_step(
                terms, current, inputs, remaining_energy, inputs.max_line_search_trials,
                initialization.sha256,
            )
        except ForwardRelaxError as error:
            raise ForwardOptimizeError(error.reason) from error
        iterations += step.optimizer_iterations
        energy_evaluations += step.energy_evaluations
        line_search_trials += step.line_search_trials
        maximum_force = (
            step.trial_maximum_force_n
            if step.trial_maximum_force_n is not None
            else step.baseline_maximum_force_n
        )
        traces.append(_iteration_trace(step))

        if step.status == "EXPERIMENTAL_INITIAL_STATIONARY":
            return _result(
                "EXPERIMENTAL_FORCE_BALANCED", terms, current, maximum_force, traces,
                iterations, energy_evaluations, line_search_trials,
                initialization.sha256,
            )
        if step.status == "EXPERIMENTAL_STEP_ACCEPTED":
            if step.coordinates_mm is None:
                raise ForwardOptimizeError("optimize.accepted_coordinates_missing")
            current = dict(step.coordinates_mm)
            if (
                step.trial_maximum_force_n is not None
                and step.trial_maximum_force_n <= force_tolerance
            ):
                return _result(
                    "EXPERIMENTAL_FORCE_BALANCED", terms, current,
                    step.trial_maximum_force_n, traces, iterations,
                    energy_evaluations, line_search_trials,
                    initialization.sha256,
                )
            continue
        return _result(
            step.status, terms, None, maximum_force, traces,
            iterations, energy_evaluations, line_search_trials,
            initialization.sha256,
        )


def _iteration_trace(step: ForwardRelaxResult) -> ForwardOptimizeIteration:
    return ForwardOptimizeIteration(
        step.status,
        step.baseline_energy_n_mm,
        step.trial_energies_n_mm,
        step.baseline_maximum_force_n,
        step.trial_maximum_force_n,
        step.accepted_alpha_mm_per_n,
        step.alpha_trace_mm_per_n,
        step.energy_evaluations,
        step.line_search_trials,
    )


def _result(
    status: str,
    terms: ForwardStretchTerms,
    coordinates: dict[str, tuple[float, float, float]] | None,
    maximum_force: float | None,
    iterations_trace: list[ForwardOptimizeIteration],
    optimizer_iterations: int,
    energy_evaluations: int,
    line_search_trials: int,
    initialization_sha256: str,
) -> ForwardOptimizeResult:
    coordinate_rows = None if coordinates is None else tuple(sorted(coordinates.items()))
    trace_payload: list[JSONValue] = [
        {
            "status": row.status,
            "baseline_energy_n_mm": row.baseline_energy_n_mm,
            "trial_energies_n_mm": list(row.trial_energies_n_mm),
            "baseline_maximum_force_n": row.baseline_maximum_force_n,
            "trial_maximum_force_n": row.trial_maximum_force_n,
            "accepted_alpha_mm_per_n": row.accepted_alpha_mm_per_n,
            "alpha_trace_mm_per_n": list(row.alpha_trace_mm_per_n),
            "energy_evaluations": row.energy_evaluations,
            "line_search_trials": row.line_search_trials,
        }
        for row in iterations_trace
    ]
    payload: dict[str, JSONValue] = {
        "profile": PROFILE,
        "status": status,
        "projection_sha256": terms.projection_sha256,
        "material_sha256": terms.material_sha256,
        "forward_inputs_sha256": terms.forward_inputs_sha256,
        "initialization_sha256": initialization_sha256,
        "coordinates_mm": None if coordinate_rows is None else [
            {"attachment_location_id": key, "xyz_mm": list(point)}
            for key, point in coordinate_rows
        ],
        "maximum_force_n": maximum_force,
        "iterations": trace_payload,
        "optimizer_iterations": optimizer_iterations,
        "energy_evaluations": energy_evaluations,
        "line_search_trials": line_search_trials,
    }
    encoded = jcs_bytes(payload)
    digest = sha256(b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + encoded).hexdigest()
    return ForwardOptimizeResult(
        status, terms.projection_sha256, terms.material_sha256,
        terms.forward_inputs_sha256, initialization_sha256, coordinate_rows, maximum_force,
        tuple(iterations_trace), optimizer_iterations, energy_evaluations,
        line_search_trials, encoded, digest,
    )
