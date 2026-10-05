"""Target-free experimental cell shear energy for the bounded quad strip.

This is a HYPOTHESIS term, not a complete F0 model or verification result.
Preparation and evaluation are O(number of cells) in time and storage.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import cast

from .canonical import jcs_bytes
from .forward_bending import ForwardBendingError, ForwardBendingTerms, evaluate_bending_terms
from .forward_cells import ForwardSurfaceCells
from .forward_forces import ForwardForceError, _evaluate_stretch_terms_at_coordinates
from .forward_initialization import ForwardInitialization
from .forward_inputs import ForwardInputs
from .forward_relax import ForwardRelaxError, _force_residual_limit, _validate_artifacts
from .forward_stretch import ForwardStretchTerms, StretchTerm
from .forward_triangulation import ForwardTriangulationError, triangulate_forward_surface_cells
from .json_types import JSONValue

PROFILE = "FORWARD_SHEAR_HYPOTHESIS_V1"
TERMS_PROFILE = "FORWARD_SHEAR_TERMS_V1"
INITIAL_ALPHA_MM_PER_N = 1.0
# Fixed optimizer parameter: 1.0 mm/N initial coordinate displacement per force.
# The backtracking search halves it until Armijo decrease; the shear optimizer owns this choice.
ARMIJO_C = 1e-4
BACKTRACK_FACTOR = 0.5


class ForwardShearError(ValueError):
    """Invalid, unsupported, or numerically undefined shear input."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ShearParameters:
    status: str
    provenance_id: str
    stiffness_n_mm: float
    rest_cosine: float
    canonical_bytes: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class ShearTerm:
    attachment_location_ids: tuple[str, str, str, str]
    rest_cosine: float
    stiffness_n_mm: float


@dataclass(frozen=True, slots=True)
class ForwardShearTerms:
    status: str
    projection_sha256: str
    material_sha256: str
    forward_inputs_sha256: str
    cells_sha256: str
    parameters_sha256: str
    terms: tuple[ShearTerm, ...]
    canonical_bytes: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class ShearEvaluation:
    energy_n_mm: float
    forces_n: tuple[tuple[str, tuple[float, float, float]], ...]
    maximum_force_n: float


@dataclass(frozen=True, slots=True)
class ShearOptimizeResult:
    """Bounded combined-force result; never an F0 or CONVERGED result."""

    status: str
    projection_sha256: str
    material_sha256: str
    forward_inputs_sha256: str
    stretch_terms_sha256: str
    shear_terms_sha256: str
    initialization_sha256: str
    coordinates_mm: tuple[tuple[str, tuple[float, float, float]], ...] | None
    maximum_force_n: float | None
    optimizer_iterations: int
    energy_evaluations: int
    line_search_trials: int
    canonical_bytes: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class ShearBendingOptimizeResult:
    """Experimental combined result binding every force-term artifact."""

    status: str
    projection_sha256: str
    material_sha256: str
    forward_inputs_sha256: str
    stretch_terms_sha256: str
    shear_terms_sha256: str
    bending_terms_sha256: str
    initialization_sha256: str
    coordinates_mm: tuple[tuple[str, tuple[float, float, float]], ...] | None
    maximum_force_n: float | None
    optimizer_iterations: int
    energy_evaluations: int
    line_search_trials: int
    canonical_bytes: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class _ArmijoResult:
    status: str
    coordinates: dict[str, tuple[float, float, float]] | None
    maximum_force_n: float | None
    optimizer_iterations: int
    energy_evaluations: int
    line_search_trials: int
    trace: tuple[dict[str, JSONValue], ...]


def admit_shear_parameters(
    provenance_id: str, stiffness_n_mm: float, rest_cosine: float
) -> ShearParameters:
    """Admit explicit hypothesis parameters with N*mm and dimensionless units."""
    if not isinstance(provenance_id, str) or not provenance_id.strip():
        raise ForwardShearError("shear.provenance_invalid")
    stiffness = _finite_number(stiffness_n_mm, "stiffness_invalid")
    cosine = _finite_number(rest_cosine, "rest_cosine_invalid")
    if stiffness <= 0:
        raise ForwardShearError("shear.stiffness_invalid")
    if not -1.0 <= cosine <= 1.0:
        raise ForwardShearError("shear.rest_cosine_invalid")
    payload = {
        "profile": PROFILE,
        "status": "HYPOTHESIS",
        "provenance_id": provenance_id,
        "stiffness_n_mm": stiffness,
        "rest_cosine": cosine,
    }
    encoded = jcs_bytes(cast(JSONValue, payload))
    digest = sha256(b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + encoded).hexdigest()
    return ShearParameters("HYPOTHESIS", provenance_id, stiffness, cosine, encoded, digest)


def prepare_shear_terms(
    cells: ForwardSurfaceCells,
    parameters: ShearParameters,
    inputs: ForwardInputs,
) -> ForwardShearTerms:
    """Bind one shear term to each admitted plain 1:1 quad cell."""
    if not isinstance(cells, ForwardSurfaceCells) or cells.status != "EXPERIMENTAL_TOPOLOGY":
        raise ForwardShearError("shear.cells_invalid")
    try:
        triangulate_forward_surface_cells(cells)
    except ForwardTriangulationError as error:
        raise ForwardShearError(error.reason) from error
    if not isinstance(inputs, ForwardInputs):
        raise ForwardShearError("shear.inputs_invalid")
    _validate_parameters(parameters)
    if not cells.cells:
        raise ForwardShearError("shear.cells_empty")
    terms = tuple(
        ShearTerm(
            (
                cell.attachment_location_ids[0],
                cell.attachment_location_ids[1],
                cell.attachment_location_ids[2],
                cell.attachment_location_ids[3],
            ),
            parameters.rest_cosine,
            parameters.stiffness_n_mm,
        )
        for cell in cells.cells
    )
    payload = {
        "profile": TERMS_PROFILE,
        "status": "EXPERIMENTAL_SHEAR_TERMS",
        "projection_sha256": cells.projection_sha256,
        "material_sha256": cells.material_sha256,
        "forward_inputs_sha256": inputs.sha256,
        "cells_sha256": cells.sha256,
        "parameters_sha256": parameters.sha256,
        "terms": [
            {
                "attachment_location_ids": list(term.attachment_location_ids),
                "rest_cosine": term.rest_cosine,
                "stiffness_n_mm": term.stiffness_n_mm,
            }
            for term in terms
        ],
    }
    encoded = jcs_bytes(cast(JSONValue, payload))
    digest = sha256(b"Crochet.AI\0" + TERMS_PROFILE.encode("ascii") + b"\0" + encoded).hexdigest()
    return ForwardShearTerms(
        "EXPERIMENTAL_SHEAR_TERMS",
        cells.projection_sha256,
        cells.material_sha256,
        inputs.sha256,
        cells.sha256,
        parameters.sha256,
        terms,
        encoded,
        digest,
    )


def evaluate_shear_terms(
    terms: ForwardShearTerms, coordinates_mm: Mapping[str, tuple[float, float, float]]
) -> ShearEvaluation:
    """Evaluate E=.5*k*(cos(u,v)-c0)^2 and its negative-gradient forces."""
    _validate_terms(terms)
    if not isinstance(coordinates_mm, Mapping):
        raise ForwardShearError("shear.coordinates_invalid")
    force: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    energy_rows: list[float] = []
    for term in terms.terms:
        try:
            a, b, c, d = (coordinates_mm[key] for key in term.attachment_location_ids)
        except (KeyError, TypeError) as error:
            raise ForwardShearError("shear.coordinate_missing") from error
        points = (a, b, c, d)
        if any(not isinstance(point, tuple) or len(point) != 3 for point in points):
            raise ForwardShearError("shear.coordinate_invalid")
        if any(not math.isfinite(value) for point in points for value in point):
            raise ForwardShearError("shear.coordinate_non_finite")
        u = tuple(b[i] - a[i] for i in range(3))
        v = tuple(d[i] - a[i] for i in range(3))
        lu, lv = math.hypot(*u), math.hypot(*v)
        if not math.isfinite(lu) or not math.isfinite(lv) or lu == 0.0 or lv == 0.0:
            raise ForwardShearError("shear.degenerate_cell")
        uh, vh = tuple(x / lu for x in u), tuple(x / lv for x in v)
        cosine = math.fsum(uh[i] * vh[i] for i in range(3))
        delta = cosine - term.rest_cosine
        energy_rows.append(0.5 * term.stiffness_n_mm * delta * delta)
        gu = tuple((vh[i] - cosine * uh[i]) / lu for i in range(3))
        gv = tuple((uh[i] - cosine * vh[i]) / lv for i in range(3))
        fb = tuple(-term.stiffness_n_mm * delta * x for x in gu)
        fd = tuple(-term.stiffness_n_mm * delta * x for x in gv)
        fa = tuple(-(fb[i] + fd[i]) for i in range(3))
        for key, vector in zip(
            term.attachment_location_ids, (fa, fb, (0.0, 0.0, 0.0), fd), strict=True
        ):
            for axis in range(3):
                force[key][axis] += vector[axis]
    try:
        energy = math.fsum(energy_rows)
    except OverflowError as error:
        raise ForwardShearError("shear.energy_non_finite") from error
    rows = tuple((key, (values[0], values[1], values[2])) for key, values in sorted(force.items()))
    if not math.isfinite(energy) or any(not math.isfinite(x) for _, row in rows for x in row):
        raise ForwardShearError("shear.result_non_finite")
    maximum = max((math.hypot(*row) for _, row in rows), default=0.0)
    if not math.isfinite(maximum):
        raise ForwardShearError("shear.result_non_finite")
    return ShearEvaluation(energy, rows, maximum)


def optimize_stretch_shear_prototype(
    stretch: ForwardStretchTerms,
    shear: ForwardShearTerms,
    initialization: ForwardInitialization,
    inputs: ForwardInputs,
) -> ShearOptimizeResult:
    """Bounded target-free Armijo descent over stretch plus shear energies.

    Every baseline and candidate costs one global energy evaluation. A result
    can only be EXPERIMENTAL_FORCE_BALANCED, BUDGET_EXHAUSTED, or a numerical
    line-search failure. Initialization is the only coordinate source.
    """
    try:
        _validate_artifacts(stretch, initialization, inputs)
    except ForwardRelaxError as error:
        raise ForwardShearError(error.reason) from error
    _validate_terms(shear)
    if (
        shear.projection_sha256 != stretch.projection_sha256
        or shear.material_sha256 != stretch.material_sha256
        or shear.forward_inputs_sha256 != stretch.forward_inputs_sha256
    ):
        raise ForwardShearError("shear.combined_provenance_mismatch")
    outcome = _run_armijo(
        dict(initialization.coordinates_mm),
        inputs,
        lambda coordinates: _evaluate_stretch_shear(stretch, shear, coordinates),
        recoverable_trial_error=lambda error: (
            (isinstance(error, ForwardForceError) and error.reason == "forces.zero_distance")
            or isinstance(error, ForwardShearError)
        ),
    )
    return _optimization_result(outcome, shear, initialization, stretch)


def optimize_stretch_shear_bending_prototype(
    stretch: ForwardStretchTerms,
    shear: ForwardShearTerms,
    bending: ForwardBendingTerms,
    initialization: ForwardInitialization,
    inputs: ForwardInputs,
) -> ShearBendingOptimizeResult:
    """Bounded target-free Armijo descent over stretch, shear, and bending."""
    try:
        _validate_artifacts(stretch, initialization, inputs)
    except ForwardRelaxError as error:
        raise ForwardShearError(error.reason) from error
    _validate_terms(shear)
    if (
        shear.projection_sha256 != initialization.projection_sha256
        or shear.material_sha256 != initialization.material_sha256
        or shear.forward_inputs_sha256 != inputs.sha256
        or not isinstance(bending, ForwardBendingTerms)
        or bending.projection_sha256 != initialization.projection_sha256
        or bending.material_sha256 != initialization.material_sha256
        or bending.forward_inputs_sha256 != inputs.sha256
        or bending.initialization_sha256 != initialization.sha256
    ):
        raise ForwardShearError("shear.bending_provenance_mismatch")
    outcome = _run_armijo(
        dict(initialization.coordinates_mm),
        inputs,
        lambda coordinates: _evaluate_stretch_shear_bending(stretch, shear, bending, coordinates),
        recoverable_trial_error=lambda _error: False,
    )
    return _bending_optimization_result(outcome, stretch, shear, bending, initialization)


def _evaluate_stretch_shear(
    stretch: ForwardStretchTerms,
    shear: ForwardShearTerms,
    coordinates: Mapping[str, tuple[float, float, float]],
) -> tuple[float, dict[str, tuple[float, float, float]], float]:
    stretch_energy, stretch_forces, _ = _evaluate_stretch_terms_at_coordinates(
        stretch.terms, dict(coordinates)
    )
    shear_evaluation = evaluate_shear_terms(shear, coordinates)
    return _merge_evaluations(
        (stretch_energy, stretch_forces),
        (shear_evaluation.energy_n_mm, shear_evaluation.forces_n),
    )


def _evaluate_stretch_shear_bending(
    stretch: ForwardStretchTerms,
    shear: ForwardShearTerms,
    bending: ForwardBendingTerms,
    coordinates: Mapping[str, tuple[float, float, float]],
) -> tuple[float, dict[str, tuple[float, float, float]], float]:
    stretch_energy, stretch_forces, _ = _evaluate_stretch_terms_at_coordinates(
        stretch.terms, dict(coordinates)
    )
    shear_evaluation = evaluate_shear_terms(shear, coordinates)
    bending_evaluation = evaluate_bending_terms(bending, coordinates)
    return _merge_evaluations(
        (stretch_energy, stretch_forces),
        (shear_evaluation.energy_n_mm, shear_evaluation.forces_n),
        (bending_evaluation.energy_n_mm, bending_evaluation.forces_n),
    )


def _merge_evaluations(
    *evaluations: tuple[float, tuple[tuple[str, tuple[float, float, float]], ...]],
) -> tuple[float, dict[str, tuple[float, float, float]], float]:
    energy_rows: list[float] = []
    force: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    for term_energy, term_forces in evaluations:
        energy_rows.append(term_energy)
        for key, vector in term_forces:
            for axis in range(3):
                force[key][axis] += vector[axis]
    try:
        energy = (
            energy_rows[0] + energy_rows[1]
            if len(energy_rows) == 2
            else math.fsum(energy_rows)
        )
    except OverflowError as error:
        raise ForwardShearError("shear.combined_non_finite") from error
    rows = {key: (vector[0], vector[1], vector[2]) for key, vector in force.items()}
    maximum = max((math.hypot(*vector) for vector in rows.values()), default=0.0)
    if not math.isfinite(energy) or not math.isfinite(maximum):
        raise ForwardShearError("shear.combined_non_finite")
    return energy, rows, maximum


def _run_armijo(
    initial_coordinates: dict[str, tuple[float, float, float]],
    inputs: ForwardInputs,
    evaluate: Callable[
        [Mapping[str, tuple[float, float, float]]],
        tuple[float, dict[str, tuple[float, float, float]], float],
    ],
    *,
    recoverable_trial_error: Callable[[Exception], bool],
) -> _ArmijoResult:
    """Shared bounded descent core; a callback call consumes one energy unit."""
    current = dict(initial_coordinates)
    force_limit = _force_residual_limit(inputs)
    iterations = evaluations = trials = 0
    maximum: float | None = None
    alpha = INITIAL_ALPHA_MM_PER_N
    trace: list[dict[str, JSONValue]] = []
    while iterations < inputs.max_optimizer_iterations:
        if evaluations >= inputs.max_energy_evaluations:
            return _armijo_result(
                "BUDGET_EXHAUSTED", None, maximum, iterations, evaluations, trials, trace
            )
        evaluations += 1
        try:
            energy, force_map, maximum = evaluate(current)
        except (ForwardForceError, ForwardShearError, ForwardBendingError):
            return _armijo_result(
                "NUMERICAL_FAILURE",
                None,
                maximum,
                iterations + 1,
                evaluations,
                trials,
                trace,
            )
        if not math.isfinite(energy) or not math.isfinite(maximum):
            return _armijo_result(
                "NUMERICAL_FAILURE",
                None,
                maximum,
                iterations + 1,
                evaluations,
                trials,
                trace,
            )
        iterations += 1
        if maximum <= force_limit:
            return _armijo_result(
                "EXPERIMENTAL_FORCE_BALANCED",
                current,
                maximum,
                iterations,
                evaluations,
                trials,
                trace,
            )
        force_square = math.fsum(
            component * component for vector in force_map.values() for component in vector
        )
        accepted = False
        for _ in range(
            min(inputs.max_line_search_trials, inputs.max_energy_evaluations - evaluations)
        ):
            candidate = {
                key: (
                    point[0] + alpha * force_map.get(key, (0.0, 0.0, 0.0))[0],
                    point[1] + alpha * force_map.get(key, (0.0, 0.0, 0.0))[1],
                    point[2] + alpha * force_map.get(key, (0.0, 0.0, 0.0))[2],
                )
                for key, point in current.items()
            }
            trials += 1
            if any(not math.isfinite(value) for point in candidate.values() for value in point):
                return _armijo_result(
                    "NUMERICAL_FAILURE",
                    None,
                    maximum,
                    iterations,
                    evaluations,
                    trials,
                    trace,
                )
            evaluations += 1
            try:
                trial_energy, _, _ = evaluate(candidate)
            except (ForwardForceError, ForwardShearError, ForwardBendingError) as error:
                if not recoverable_trial_error(error):
                    return _armijo_result(
                        "NUMERICAL_FAILURE",
                        None,
                        maximum,
                        iterations,
                        evaluations,
                        trials,
                        trace,
                    )
                trial_energy = math.inf
            trace.append(
                {
                    "energy_n_mm": trial_energy if math.isfinite(trial_energy) else None,
                    "alpha_mm_per_n": alpha,
                }
            )
            if (
                math.isfinite(trial_energy)
                and trial_energy < energy
                and trial_energy <= energy - ARMIJO_C * alpha * force_square
            ):
                current = candidate
                accepted = True
                alpha = min(INITIAL_ALPHA_MM_PER_N, alpha * 2.0)
                break
            alpha *= BACKTRACK_FACTOR
            if evaluations >= inputs.max_energy_evaluations:
                break
        if not accepted:
            status = (
                "BUDGET_EXHAUSTED"
                if evaluations >= inputs.max_energy_evaluations
                else "LINE_SEARCH_FAILED"
            )
            return _armijo_result(status, None, maximum, iterations, evaluations, trials, trace)
    return _armijo_result("BUDGET_EXHAUSTED", None, maximum, iterations, evaluations, trials, trace)


def _armijo_result(
    status: str,
    coordinates: dict[str, tuple[float, float, float]] | None,
    maximum: float | None,
    iterations: int,
    evaluations: int,
    trials: int,
    trace: list[dict[str, JSONValue]],
) -> _ArmijoResult:
    return _ArmijoResult(
        status, coordinates, maximum, iterations, evaluations, trials, tuple(trace)
    )


def _optimization_result(
    outcome: _ArmijoResult,
    shear: ForwardShearTerms,
    initialization: ForwardInitialization,
    stretch: ForwardStretchTerms,
) -> ShearOptimizeResult:
    stretch_sha256 = _stretch_terms_sha256(stretch)
    rows = None if outcome.coordinates is None else tuple(sorted(outcome.coordinates.items()))
    payload = {
        "profile": "FORWARD_STRETCH_SHEAR_OPTIMIZATION_V1",
        "status": outcome.status,
        "projection_sha256": shear.projection_sha256,
        "material_sha256": shear.material_sha256,
        "forward_inputs_sha256": shear.forward_inputs_sha256,
        "shear_terms_sha256": shear.sha256,
        "stretch_terms_sha256": stretch_sha256,
        "initialization_sha256": initialization.sha256,
        "initial_alpha_mm_per_n": INITIAL_ALPHA_MM_PER_N,
        "armijo_c": ARMIJO_C,
        "coordinates_mm": None
        if rows is None
        else [{"attachment_location_id": key, "xyz_mm": list(point)} for key, point in rows],
        "maximum_force_n": outcome.maximum_force_n,
        "optimizer_iterations": outcome.optimizer_iterations,
        "energy_evaluations": outcome.energy_evaluations,
        "line_search_trials": outcome.line_search_trials,
        "trace": list(outcome.trace),
    }
    encoded = jcs_bytes(cast(JSONValue, payload))
    digest = sha256(b"Crochet.AI\0FORWARD_STRETCH_SHEAR_OPTIMIZATION_V1\0" + encoded).hexdigest()
    return ShearOptimizeResult(
        outcome.status,
        shear.projection_sha256,
        shear.material_sha256,
        shear.forward_inputs_sha256,
        stretch_sha256,
        shear.sha256,
        initialization.sha256,
        rows,
        outcome.maximum_force_n,
        outcome.optimizer_iterations,
        outcome.energy_evaluations,
        outcome.line_search_trials,
        encoded,
        digest,
    )


def _bending_optimization_result(
    outcome: _ArmijoResult,
    stretch: ForwardStretchTerms,
    shear: ForwardShearTerms,
    bending: ForwardBendingTerms,
    initialization: ForwardInitialization,
) -> ShearBendingOptimizeResult:
    stretch_digest = _stretch_terms_sha256(stretch)
    coordinates = (
        None if outcome.coordinates is None else tuple(sorted(outcome.coordinates.items()))
    )
    payload: dict[str, JSONValue] = {
        "profile": "FORWARD_STRETCH_SHEAR_BENDING_OPTIMIZATION_V1",
        "status": outcome.status,
        "projection_sha256": initialization.projection_sha256,
        "material_sha256": initialization.material_sha256,
        "forward_inputs_sha256": initialization.forward_inputs_sha256,
        "stretch_terms_sha256": stretch_digest,
        "shear_terms_sha256": shear.sha256,
        "bending_terms_sha256": bending.sha256,
        "initialization_sha256": initialization.sha256,
        "initial_alpha_mm_per_n": INITIAL_ALPHA_MM_PER_N,
        "armijo_c": ARMIJO_C,
        "backtracking_factor": BACKTRACK_FACTOR,
        "coordinates_mm": None
        if coordinates is None
        else [{"attachment_location_id": key, "xyz_mm": list(point)} for key, point in coordinates],
        "maximum_force_n": outcome.maximum_force_n,
        "optimizer_iterations": outcome.optimizer_iterations,
        "energy_evaluations": outcome.energy_evaluations,
        "line_search_trials": outcome.line_search_trials,
        "trace": list(outcome.trace),
    }
    encoded = jcs_bytes(payload)
    digest = sha256(
        b"Crochet.AI\0FORWARD_STRETCH_SHEAR_BENDING_OPTIMIZATION_V1\0" + encoded
    ).hexdigest()
    return ShearBendingOptimizeResult(
        outcome.status,
        initialization.projection_sha256,
        initialization.material_sha256,
        initialization.forward_inputs_sha256,
        stretch_digest,
        shear.sha256,
        bending.sha256,
        initialization.sha256,
        coordinates,
        outcome.maximum_force_n,
        outcome.optimizer_iterations,
        outcome.energy_evaluations,
        outcome.line_search_trials,
        encoded,
        digest,
    )


def _validate_parameters(parameters: ShearParameters) -> None:
    if not isinstance(parameters, ShearParameters) or parameters.status != "HYPOTHESIS":
        raise ForwardShearError("shear.parameters_invalid")
    expected = admit_shear_parameters(
        parameters.provenance_id, parameters.stiffness_n_mm, parameters.rest_cosine
    )
    if (
        parameters.canonical_bytes != expected.canonical_bytes
        or parameters.sha256 != expected.sha256
    ):
        raise ForwardShearError("shear.parameters_integrity")


def _stretch_terms_sha256(stretch: ForwardStretchTerms) -> str:
    """Canonicalize every stretch coefficient and endpoint for result binding."""
    term_rows: list[JSONValue] = []
    for term in stretch.terms:
        if not isinstance(term, StretchTerm):
            raise ForwardShearError("shear.stretch_terms_invalid")
        term_rows.append(
            {
                "edge_type": term.edge_type,
                "source_location_id": term.source_location_id,
                "target_location_id": term.target_location_id,
                "rest_length_mm": term.rest_length_mm,
                "stiffness_n_per_mm": term.stiffness_n_per_mm,
                "response_id": term.response_id,
            }
        )
    payload: dict[str, JSONValue] = {
        "profile": "FORWARD_STRETCH_TERMS_BINDING_V1",
        "status": stretch.status,
        "projection_sha256": stretch.projection_sha256,
        "material_sha256": stretch.material_sha256,
        "forward_inputs_sha256": stretch.forward_inputs_sha256,
        "terms": term_rows,
    }
    encoded = jcs_bytes(payload)
    return sha256(b"Crochet.AI\0FORWARD_STRETCH_TERMS_BINDING_V1\0" + encoded).hexdigest()


def _validate_terms(terms: ForwardShearTerms) -> None:
    if not isinstance(terms, ForwardShearTerms) or terms.status != "EXPERIMENTAL_SHEAR_TERMS":
        raise ForwardShearError("shear.terms_invalid")
    for digest in (
        terms.projection_sha256,
        terms.material_sha256,
        terms.forward_inputs_sha256,
        terms.cells_sha256,
        terms.parameters_sha256,
        terms.sha256,
    ):
        if not _is_digest(digest):
            raise ForwardShearError("shear.hash_invalid")
    payload = {
        "profile": TERMS_PROFILE,
        "status": terms.status,
        "projection_sha256": terms.projection_sha256,
        "material_sha256": terms.material_sha256,
        "forward_inputs_sha256": terms.forward_inputs_sha256,
        "cells_sha256": terms.cells_sha256,
        "parameters_sha256": terms.parameters_sha256,
        "terms": [
            {
                "attachment_location_ids": list(term.attachment_location_ids),
                "rest_cosine": term.rest_cosine,
                "stiffness_n_mm": term.stiffness_n_mm,
            }
            for term in terms.terms
        ],
    }
    encoded = jcs_bytes(cast(JSONValue, payload))
    expected = sha256(b"Crochet.AI\0" + TERMS_PROFILE.encode("ascii") + b"\0" + encoded).hexdigest()
    if encoded != terms.canonical_bytes or expected != terms.sha256:
        raise ForwardShearError("shear.terms_integrity")


def _finite_number(value: float, reason: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ForwardShearError(f"shear.{reason}")
    return float(value)


def _is_digest(value: str) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )
