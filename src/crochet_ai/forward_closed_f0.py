"""Bounded target-free closed SC shell equilibrium with certified linear steps."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
from hashlib import sha256
from typing import cast

from .canonical import CanonicalizationError, jcs_bytes, parse_json
from .forward_closed_cells import build_closed_surface_cells
from .forward_closed_mechanics import (
    _closure_cycles,
    _coordinates,
    _evaluate_checked,
    _finite_fsum,
    _perimeter_term,
    _spring_terms,
    _validate_optimizer_force_norm,
    admit_closed_mechanics_recipe,
)
from .forward_forces import ForwardForceError
from .forward_graph import lower_forward_graph
from .forward_inputs import ForwardInputs, admit_forward_inputs
from .forward_shaped import (
    _coordinates as initialize_shaped_coordinates,
)
from .forward_shaped import (
    _terms as derive_shaped_terms,
)
from .forward_shaped import admit_shaped_forward_recipe, inspect_shaped_forward_model
from .forward_shear import ARMIJO_C, BACKTRACK_FACTOR, INITIAL_ALPHA_MM_PER_N
from .forward_shell_terms import (
    ShellTermsError,
    admit_shell_parameters,
    evaluate_shell_terms,
    prepare_shell_terms,
)
from .forward_surface_contact import (
    ContactBudgetContext,
    ContactError,
    admit_contact_parameters,
    certify_contact_path,
    evaluate_contact,
    prepare_surface_contact,
)
from .json_types import JSONValue
from .material_scenarios import GaugeScenario, apply_gauge_scenario
from .physical_projection import PhysicalSemanticProjection
from .validation import SemanticValidator

PROFILE = "FORWARD_CLOSED_F0_V1"
INITIALIZATION_RULE = "CANONICAL_LABEL_SINE_PERTURBATION_V1"
Vec3 = tuple[float, float, float]
Points = dict[str, Vec3]


class ClosedF0Error(ValueError):
    """Invalid recipe or unsupported construction, before numerical execution."""

    def __init__(self, code: str, reason: str) -> None:
        self.code, self.reason = code, reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ClosedF0Recipe:
    canonical_bytes: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class Objective:
    energy_n_mm: float
    forces_n: Points
    maximum_force_n: float
    terms: dict[str, JSONValue]


@dataclass(slots=True)
class StartResult:
    status: str
    reason: str
    points: Points
    final: Objective | None
    iterations: int
    evaluations: int
    trials: int
    last_step_mm: float | None
    relative_energy_change: float | None
    stationary_checks: int
    trace: list[JSONValue]


def _object(value: object, keys: set[str], path: str) -> dict[str, JSONValue]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ClosedF0Error("E_SCHEMA", f"{path}.fields_invalid")
    return cast(dict[str, JSONValue], value)


def admit_closed_f0_recipe(value: object) -> ClosedF0Recipe:
    raw = _object(
        value,
        {"profile", "closed_recipe", "shell_parameters", "contact_parameters", "solver_parameters"},
        "recipe",
    )
    if raw["profile"] != PROFILE:
        raise ClosedF0Error("E_UNSUPPORTED_FEATURE", "recipe.profile_invalid")
    closed = admit_closed_mechanics_recipe(raw["closed_recipe"])
    admit_shell_parameters(raw["shell_parameters"])
    contact = admit_contact_parameters(raw["contact_parameters"])
    closed_raw = cast(dict[str, JSONValue], parse_json(closed.canonical_bytes))
    elastic_raw = cast(dict[str, JSONValue], closed_raw["elastic_recipe"])
    admitted_inputs = admit_forward_inputs(
        cast(Mapping[str, object], elastic_raw["loading"]),
        cast(Mapping[str, object], elastic_raw["model_profile"]),
        cast(Mapping[str, object], elastic_raw["config"]),
    )
    if contact.max_pair_evaluations > admitted_inputs.max_contact_pairs_evaluated:
        raise ClosedF0Error("E_INPUT", "contact_parameters.exceeds_config_pair_budget")
    solver = _object(
        raw["solver_parameters"],
        {"schema_version", "initialization_rule", "start_count", "perturbation_mm", "seed"},
        "solver_parameters",
    )
    if solver["schema_version"] != "1.0.0" or solver["initialization_rule"] != INITIALIZATION_RULE:
        raise ClosedF0Error("E_INPUT", "solver_parameters.version_or_initialization_invalid")
    count, seed, amplitude = solver["start_count"], solver["seed"], solver["perturbation_mm"]
    if type(count) is not int or not 2 <= count <= 4:
        raise ClosedF0Error("E_INPUT", "solver_parameters.start_count_invalid")
    if type(seed) is not int or not 0 <= seed <= 4_294_967_295:
        raise ClosedF0Error("E_INPUT", "solver_parameters.seed_invalid")
    if type(amplitude) not in (int, float):
        raise ClosedF0Error("E_INPUT", "solver_parameters.perturbation_invalid")
    if isinstance(amplitude, int) and abs(amplitude) > 9_007_199_254_740_991:
        raise ClosedF0Error("E_INPUT", "solver_parameters.perturbation_invalid")
    amplitude_f = float(cast(int | float, amplitude))
    if not math.isfinite(amplitude_f) or amplitude_f <= 0:
        raise ClosedF0Error("E_INPUT", "solver_parameters.perturbation_invalid")
    # Parameter admission already checks every scalar and field; retain explicit snapshots.
    shell_raw = cast(dict[str, JSONValue], raw["shell_parameters"])
    contact_raw: dict[str, JSONValue] = {
        field.name: cast(JSONValue, getattr(contact, field.name)) for field in fields(contact)
    }
    normalized: dict[str, JSONValue] = {
        "profile": PROFILE,
        "closed_recipe": closed_raw,
        "shell_parameters": shell_raw,
        "contact_parameters": contact_raw,
        "solver_parameters": {**solver, "perturbation_mm": amplitude_f},
    }
    try:
        encoded = jcs_bytes(normalized)
    except CanonicalizationError as error:
        raise ClosedF0Error("E_INPUT", "recipe.noncanonical") from error
    return ClosedF0Recipe(encoded, _digest(encoded))


def _validate_recipe(recipe: ClosedF0Recipe) -> dict[str, JSONValue]:
    if not isinstance(recipe, ClosedF0Recipe):
        raise ClosedF0Error("E_INPUT", "recipe.type_invalid")
    raw = parse_json(recipe.canonical_bytes)
    admitted = admit_closed_f0_recipe(raw)
    if admitted != recipe:
        raise ClosedF0Error("E_INPUT", "recipe.integrity_invalid")
    return cast(dict[str, JSONValue], raw)


def _gauge(points: Mapping[str, Vec3], face: tuple[str, str, str]) -> Points:
    """Remove proper rigid modes using construction labels, never target alignment."""
    keys = sorted(points)
    center = tuple(_finite_fsum(points[key][i] for key in keys) / len(keys) for i in range(3))
    a, b, c = (points[key] for key in face)
    u = tuple(b[i] - a[i] for i in range(3))
    length = math.hypot(*u)
    if not math.isfinite(length) or length <= 0:
        raise ForwardForceError("f0.gauge_degenerate")
    x = cast(Vec3, tuple(value / length for value in u))
    v = tuple(c[i] - a[i] for i in range(3))
    dot = _finite_fsum(x[i] * v[i] for i in range(3))
    y_raw = tuple(v[i] - dot * x[i] for i in range(3))
    y_length = math.hypot(*y_raw)
    if not math.isfinite(y_length) or y_length <= 0:
        raise ForwardForceError("f0.gauge_degenerate")
    y = cast(Vec3, tuple(value / y_length for value in y_raw))
    z: Vec3 = (x[1] * y[2] - x[2] * y[1], x[2] * y[0] - x[0] * y[2], x[0] * y[1] - x[1] * y[0])
    result = {
        key: cast(
            Vec3,
            tuple(
                _finite_fsum((points[key][i] - center[i]) * axis[i] for i in range(3))
                for axis in (x, y, z)
            ),
        )
        for key in keys
    }
    if any(not math.isfinite(v) for row in result.values() for v in row):
        raise ForwardForceError("f0.gauge_non_finite")
    return result


def _initialize(points: Points, start: int, seed: int, amplitude: float) -> Points:
    if start == 0:
        return dict(points)
    # Bounded phase in radians, with exact integer arithmetic before the binary64 division.
    # The fixed rule is reproducible on the pinned Python/math runtime, not a cross-libm promise.
    return {
        key: cast(
            Vec3,
            tuple(
                point[axis]
                + amplitude
                * math.sin(
                    ((seed + 104729 * start + 8191 * (index + 1) + 127 * axis) % 1048576)
                    * math.tau
                    / 1048576
                )
                for axis in range(3)
            ),
        )
        for index, (key, point) in enumerate(sorted(points.items()))
    }


def _error_status(error: Exception) -> tuple[str, str]:
    if isinstance(error, ContactError):
        if error.code == "contact.budget_exhausted":
            return "BUDGET_EXHAUSTED", error.reason
        if error.code == "contact.unresolved_collision":
            return "UNRESOLVED_COLLISION", error.reason
        return "NUMERICAL_FAILURE", error.reason
    return "NUMERICAL_FAILURE", str(error)


def _optimize(
    initial: Points,
    inputs: ForwardInputs,
    evaluate: Callable[[Points], Objective],
    certify: Callable[[Points, Points], tuple[str, str]],
) -> StartResult:
    """Armijo descent; every accepted movement has a continuous-path certificate."""
    points = dict(initial)
    evaluations = trials = iterations = stationary = 0
    trace: list[JSONValue] = []
    final: Objective | None = None
    last_step: float | None = None
    relative_change: float | None = None
    tolerance = dict(inputs.tolerances)

    def result(status: str, reason: str) -> StartResult:
        return StartResult(
            status,
            reason,
            points,
            final,
            iterations,
            evaluations,
            trials,
            last_step,
            relative_change,
            stationary,
            trace,
        )

    def objective(at: Points) -> Objective:
        nonlocal evaluations
        if evaluations >= inputs.max_energy_evaluations:
            raise ContactError("contact.budget_exhausted", "objective_budget_exhausted")
        evaluations += 1
        value = evaluate(at)
        _validate_optimizer_force_norm(value.forces_n)
        if (
            set(value.forces_n) != set(at)
            or not math.isfinite(value.energy_n_mm)
            or not math.isfinite(value.maximum_force_n)
        ):
            raise ForwardForceError("f0.objective_invalid")
        actual_maximum = max(math.hypot(*row) for row in value.forces_n.values())
        if actual_maximum != value.maximum_force_n:
            raise ForwardForceError("f0.force_residual_assertion_mismatch")
        return value

    try:
        final = objective(points)
        # No accepted movement yet: a stationary initialization has explicitly zero update.
        last_step, relative_change = 0.0, 0.0
        while True:
            force_ok = final.maximum_force_n <= tolerance["force_residual_n"].value
            step_ok = last_step <= tolerance["position_step_mm"].value
            energy_ok = relative_change <= tolerance["relative_energy_change"].value
            if force_ok and step_ok and energy_ok:
                stationary += 1
                trace.append(
                    {
                        "kind": "STATIONARY_CHECK",
                        "energy_n_mm": final.energy_n_mm,
                        "maximum_force_n": final.maximum_force_n,
                        "position_step_mm": last_step,
                        "relative_energy_change": relative_change,
                        "coordinates_sha256": _point_hash(points),
                    }
                )
                if stationary >= 2:
                    return result("CONVERGED", "all_stationary_predicates_pass")
                repeated = objective(points)
                relative_change = abs(repeated.energy_n_mm - final.energy_n_mm) / max(
                    abs(final.energy_n_mm), abs(repeated.energy_n_mm), 1.0
                )
                final = repeated
                continue
            stationary = 0
            if iterations >= inputs.max_optimizer_iterations:
                return result("BUDGET_EXHAUSTED", "optimizer_iteration_budget_exhausted")
            norm_sq = _finite_fsum(v * v for row in final.forces_n.values() for v in row)
            if norm_sq < 0:
                return result("NUMERICAL_FAILURE", "negative_force_norm")
            accepted = False
            alpha = INITIAL_ALPHA_MM_PER_N
            for local_trial in range(inputs.max_line_search_trials):
                trials += 1
                proposed = {
                    key: cast(
                        Vec3,
                        tuple(points[key][i] + alpha * final.forces_n[key][i] for i in range(3)),
                    )
                    for key in sorted(points)
                }
                if any(not math.isfinite(v) for row in proposed.values() for v in row):
                    trace.append(
                        {
                            "kind": "TRIAL",
                            "alpha_mm_per_n": alpha,
                            "cause": "NON_FINITE_COORDINATES",
                            "accepted": False,
                        }
                    )
                    alpha *= BACKTRACK_FACTOR
                    continue
                path_status, path_reason = certify(points, proposed)
                if path_status == "BUDGET_EXHAUSTED":
                    return result("BUDGET_EXHAUSTED", path_reason)
                if path_status != "SAFE":
                    trace.append(
                        {
                            "kind": "TRIAL",
                            "alpha_mm_per_n": alpha,
                            "cause": path_reason,
                            "accepted": False,
                        }
                    )
                    alpha *= BACKTRACK_FACTOR
                    continue
                try:
                    trial = objective(proposed)
                except (ContactError, ShellTermsError, ForwardForceError) as error:
                    status, reason = _error_status(error)
                    if status == "BUDGET_EXHAUSTED":
                        return result(status, reason)
                    trace.append(
                        {
                            "kind": "TRIAL",
                            "alpha_mm_per_n": alpha,
                            "cause": reason,
                            "accepted": False,
                        }
                    )
                    alpha *= BACKTRACK_FACTOR
                    continue
                decrease = ARMIJO_C * alpha * norm_sq
                if not math.isfinite(decrease):
                    raise ForwardForceError("f0.armijo_non_finite")
                if trial.energy_n_mm <= final.energy_n_mm - decrease:
                    last_step = max(math.dist(points[key], proposed[key]) for key in points)
                    relative_change = abs(trial.energy_n_mm - final.energy_n_mm) / max(
                        abs(final.energy_n_mm), abs(trial.energy_n_mm), 1.0
                    )
                    trace.append(
                        {
                            "kind": "ACCEPTED_STEP",
                            "alpha_mm_per_n": alpha,
                            "energy_before_n_mm": final.energy_n_mm,
                            "energy_after_n_mm": trial.energy_n_mm,
                            "position_step_mm": last_step,
                            "relative_energy_change": relative_change,
                            "before_sha256": _point_hash(points),
                            "after_sha256": _point_hash(proposed),
                            "path_status": path_status,
                            "path_reason": path_reason,
                        }
                    )
                    points, final = proposed, trial
                    iterations += 1
                    accepted = True
                    break
                trace.append(
                    {
                        "kind": "TRIAL",
                        "trial": local_trial,
                        "alpha_mm_per_n": alpha,
                        "cause": "ARMIJO_DECREASE_FAILED",
                        "accepted": False,
                    }
                )
                alpha *= BACKTRACK_FACTOR
            if not accepted:
                return result("DIVERGED", "line_search_exhausted")
    except (ContactError, ShellTermsError, ForwardForceError, OverflowError, ValueError) as error:
        status, reason = _error_status(error)
        return result(status, reason)


def run_closed_f0(
    projection: PhysicalSemanticProjection,
    material: dict[str, JSONValue],
    recipe: ClosedF0Recipe,
    *,
    validator: SemanticValidator,
    gauge_scenario: GaugeScenario | None = None,
    gauge_policy: object | None = None,
) -> dict[str, JSONValue]:
    """Run all declared starts. The caller cannot supply target or initial coordinates."""
    if not isinstance(projection, PhysicalSemanticProjection):
        raise ClosedF0Error("E_INPUT", "projection.type_invalid")
    raw = _validate_recipe(recipe)
    if (gauge_scenario is None) != (gauge_policy is None):
        raise ClosedF0Error("E_INPUT", "gauge_scenario.requires_bound_policy")
    closed = cast(dict[str, JSONValue], raw["closed_recipe"])
    elastic_recipe = admit_shaped_forward_recipe(closed["elastic_recipe"])
    elastic = inspect_shaped_forward_model(
        projection, material, elastic_recipe, validator=validator
    )
    cells = build_closed_surface_cells(projection, max_vertices=2048, max_faces=4096)
    cell_value = cells.to_dict()
    vertices = tuple(cast(list[str], cell_value["vertices"]))
    faces = tuple(tuple(cast(list[str], f)) for f in cast(list[JSONValue], cell_value["faces"]))
    face_rows = cast(tuple[tuple[str, str, str], ...], faces)
    original = _coordinates(elastic)
    elastic_raw = cast(dict[str, JSONValue], closed["elastic_recipe"])
    inputs = admit_forward_inputs(
        cast(Mapping[str, object], elastic_raw["loading"]),
        cast(Mapping[str, object], elastic_raw["model_profile"]),
        cast(Mapping[str, object], elastic_raw["config"]),
    )
    stretch = _spring_terms(elastic)
    if gauge_scenario is not None:
        graph = lower_forward_graph(
            projection, material, cast(str, elastic_raw["tension_profile_id"]),
            cast(str, elastic_raw["fabric_state"]), validator=validator,
        )
        derived = apply_gauge_scenario(
            graph, gauge_scenario, material_profile=material, policy=gauge_policy
        )
        rest = cast(dict[str, JSONValue], elastic_raw["rest_parameters"])
        original = initialize_shaped_coordinates(projection.to_dict(), derived.graph, rest)
        stretch = derive_shaped_terms(derived.graph, inputs, rest)
    if set(vertices) != set(original):
        raise ClosedF0Error("E_INPUT", "surface.vertex_set_mismatch")
    shell_parameters = admit_shell_parameters(raw["shell_parameters"])
    shell = prepare_shell_terms(vertices, face_rows, shell_parameters)
    ordered = tuple(sorted(vertices))
    index = {key: i for i, key in enumerate(ordered)}
    contact_surface = prepare_surface_contact(
        tuple(original[key] for key in ordered),
        tuple(cast(tuple[int, int, int], tuple(index[key] for key in face)) for face in face_rows),
    )
    contact_parameters = admit_contact_parameters(raw["contact_parameters"])
    budget = ContactBudgetContext()
    closure = cast(dict[str, JSONValue], closed["closure_parameters"])
    pressure = cast(dict[str, JSONValue], closed["pressure_loading"])
    ring_cycle, close_cycle = _closure_cycles(projection.to_dict())
    ring = _perimeter_term(
        "RING_CLOSURE",
        ring_cycle,
        cast(float, closure["ring_rest_perimeter_mm"]),
        cast(float, closure["ring_stiffness_n_per_mm"]),
    )
    close = _perimeter_term(
        "CLOSE_CLOSURE",
        close_cycle,
        cast(float, closure["close_rest_perimeter_mm"]),
        cast(float, closure["close_stiffness_n_per_mm"]),
    )

    def evaluate(points: Points) -> Objective:
        contact = evaluate_contact(
            contact_surface, tuple(points[key] for key in ordered), contact_parameters, budget
        )
        mechanical = _evaluate_checked(
            stretch,
            ring,
            close,
            cast(float, pressure["pressure_n_per_mm2"]),
            [list(face) for face in face_rows],
            points,
            dict(inputs.tolerances)["volume_orientation_epsilon_mm3"].value,
            cast(float, pressure["volume_limit_mm3"]),
        )
        shell_value = evaluate_shell_terms(shell, points)
        shear_forces, contact_forces = dict(shell_value.forces_n), dict(contact.forces_n)
        forces = {
            key: cast(
                Vec3,
                tuple(
                    _finite_fsum(
                        (
                            mechanical[1][key][axis],
                            shear_forces[key][axis],
                            contact_forces.get(index[key], (0.0, 0.0, 0.0))[axis],
                        )
                    )
                    for axis in range(3)
                ),
            )
            for key in ordered
        }
        energy = _finite_fsum((mechanical[0], shell_value.total_n_mm, contact.energy_n_mm))
        terms: dict[str, JSONValue] = {
            **cast(dict[str, JSONValue], mechanical[3]),
            "shear_energy_n_mm": shell_value.shear_n_mm,
            "bending_energy_n_mm": shell_value.bending_n_mm,
            "contact_energy_n_mm": contact.energy_n_mm,
            "energy_n_mm": energy,
        }
        return Objective(energy, forces, max(math.hypot(*row) for row in forces.values()), terms)

    def certify(start: Points, end: Points) -> tuple[str, str]:
        certificate = certify_contact_path(
            contact_surface,
            tuple(start[key] for key in ordered),
            tuple(end[key] for key in ordered),
            contact_parameters,
            budget,
        )
        return certificate.status, certificate.reason

    solver = cast(dict[str, JSONValue], raw["solver_parameters"])
    results: list[StartResult] = []
    for start in range(cast(int, solver["start_count"])):
        try:
            initial = _gauge(
                _initialize(
                    original,
                    start,
                    cast(int, solver["seed"]),
                    cast(float, solver["perturbation_mm"]),
                ),
                face_rows[0],
            )
            results.append(_optimize(initial, inputs, evaluate, certify))
        except (
            ForwardForceError,
            ContactError,
            ShellTermsError,
            OverflowError,
            ValueError,
        ) as error:
            status, reason = _error_status(error)
            results.append(StartResult(status, reason, {}, None, 0, 0, 0, None, None, 0, []))
    failed = next((result for result in results if result.status != "CONVERGED"), None)
    status, reason = (
        (failed.status, failed.reason) if failed else ("CONVERGED", "all_starts_converged")
    )
    rms: float | None = None
    winner: StartResult | None = None
    if failed is None:
        gauged = [_gauge(result.points, face_rows[0]) for result in results]
        rms = max(
            math.sqrt(
                _finite_fsum(math.dist(a[key], b[key]) ** 2 for key in ordered) / len(ordered)
            )
            for i, a in enumerate(gauged)
            for b in gauged[i + 1 :]
        )
        if rms > dict(inputs.tolerances)["mode_equivalence_rms_mm"].value:
            status, reason = "DIVERGED", "observed_multimodality"
        else:
            winner = min(results, key=lambda result: cast(Objective, result.final).energy_n_mm)
    success = status == "CONVERGED" and winner is not None
    records: list[JSONValue] = []
    for i, result in enumerate(results):
        records.append(
            {
                "start_index": i,
                "status": result.status,
                "reason": result.reason,
                "optimizer_iterations": result.iterations,
                "energy_evaluations": result.evaluations,
                "line_search_trials": result.trials,
                "stationary_checks": result.stationary_checks,
                "last_step_mm": result.last_step_mm,
                "relative_energy_change": result.relative_energy_change,
                "maximum_force_n": None if result.final is None else result.final.maximum_force_n,
                "energy_n_mm": None if result.final is None else result.final.energy_n_mm,
                "coordinates_mm": _point_rows(result.points) if success else None,
                "trace": result.trace,
            }
        )
    payload: dict[str, JSONValue] = {
        "profile": PROFILE,
        "status": status,
        "reason": reason,
        "verification_state": "NOT_VERIFIED",
        "physical_status": "UNTESTED",
        "constitutive_status": "HYPOTHESIS",
        "v6_status": "NOT_RUN",
        "comparison_eligible": success,
        "projection_sha256": projection.sha256,
        "material_sha256": elastic["material_sha256"],
        "recipe_sha256": recipe.sha256,
        "forward_inputs_sha256": inputs.sha256,
        "surface_cells_sha256": cells.sha256,
        "shell_terms_sha256": shell.sha256,
        "contact_surface_sha256": contact_surface.topology_sha256,
        "initial_bundle_sha256": elastic["sha256"],
        "initial_coordinates_sha256": _point_hash(original),
        "gauge_scenario_sha256": None if gauge_scenario is None else gauge_scenario.scenario_sha256,
        "coordinates_mm": _point_rows(cast(StartResult, winner).points) if success else None,
        "faces": [list(face) for face in face_rows] if success else None,
        "final_mechanics": cast(Objective, cast(StartResult, winner).final).terms
        if success
        else None,
        "mode_equivalence_rms_mm": rms,
        "starts": records,
        "solver_parameters": solver,
        "contact_work": {
            field.name: cast(JSONValue, getattr(budget, field.name)) for field in fields(budget)
        },
        "preparation_energy_evaluations": 1,
        "work_budget_scopes": {
            "max_initializations": "ELASTIC_PREPARATION_ONLY_EXACTLY_ONE",
            "start_count": "ALL_REQUIRED_F0_STARTS_EXACT_DECLARED_COUNT",
            "max_initialization_vertices": "EVERY_START",
            "max_contact_pairs_evaluated": "CUMULATIVE_ALL_STARTS_AND_TRIALS",
            "max_linear_iterations": "NOT_APPLICABLE_NO_LINEAR_SOLVER",
        },
        "optimizer_policy": {
            "armijo_c": ARMIJO_C,
            "backtracking_factor": BACKTRACK_FACTOR,
            "initial_alpha_mm_per_n": INITIAL_ALPHA_MM_PER_N,
            "stationary_window": 2,
            "relative_energy_floor_n_mm": 1.0,
            "relative_energy_floor_policy": {
                "unit": "N*mm",
                "owner": "FORWARD_CLOSED_F0_V1",
                "rationale": "Finite relative-change normalization near zero signed energy.",
                "validation_path": "closed_f0_scale_and_equilibrium_fixtures",
            },
            "tolerances": parse_json(inputs.canonical_bytes),
        },
        "limitations": [
            "uniform_constitutive_hypothesis",
            "bounded_observed_multistart",
            "independent_v6_admission_required",
            "physical_calibration_required",
        ],
    }
    payload["sha256"] = _digest(jcs_bytes(payload))
    return payload


def _point_rows(points: Points) -> list[JSONValue]:
    return [
        {"attachment_location_id": key, "position_mm": list(point)}
        for key, point in sorted(points.items())
    ]


def _point_hash(points: Points) -> str:
    return _digest(jcs_bytes(_point_rows(points)))


def _digest(encoded: bytes) -> str:
    return sha256(b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + encoded).hexdigest()
