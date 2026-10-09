"""Independent replay audit for the experimental closed F0 result.

This module deliberately does not import the F0 optimizer, runner, gauge, or
initializer. Energy and exact contact constitutive kernels are shared with the
producer and therefore remain an explicit common-mode limitation.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import cast

from .canonical import (
    SAFE_INTEGER,
    CanonicalizationError,
    CanonicalProfile,
    canonical_hash,
    jcs_bytes,
    parse_json,
)
from .forward_closed_cells import build_closed_surface_cells
from .forward_closed_mechanics import (
    _closure_cycles,
    _coordinates,
    _evaluate_checked,
    _finite_fsum,
    _perimeter_term,
    _spring_terms,
    admit_closed_mechanics_recipe,
)
from .forward_forces import ForwardForceError
from .forward_graph import ForwardGraph, lower_forward_graph
from .forward_inputs import ForwardInputs, admit_forward_inputs
from .forward_shaped import (
    _coordinates as initialize_shaped_coordinates,
)
from .forward_shaped import (
    _terms as derive_shaped_terms,
)
from .forward_shaped import (
    admit_shaped_forward_recipe,
    inspect_shaped_forward_model,
)
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
from .material_scenarios import (
    GaugeScenario,
    MaterialScenarioError,
    validate_gauge_scenario,
)
from .physical_projection import PhysicalSemanticProjection
from .validation import SemanticValidator

PROFILE = "FORWARD_CLOSED_F0_AUDIT_V1"
_F0_PROFILE = "FORWARD_CLOSED_F0_V1"
_INITIALIZATION_RULE = "CANONICAL_LABEL_SINE_PERTURBATION_V1"
_ARMijo_C = 1e-4
_BACKTRACK = 0.5
_INITIAL_ALPHA = 1.0
_MAX_REPLAY_OBJECTIVES = 20_000
_MAX_REPLAY_CONTACT_PAIRS = 2_000_000
_MAX_INPUT_BYTES = 2_000_000
_MAX_INPUT_NODES = 100_000
_MAX_INPUT_DEPTH = 64
Vec3 = tuple[float, float, float]
Points = dict[str, Vec3]
ObjectiveEvaluator = Callable[[Points], "_Objective"]
PathCertifier = Callable[[Points, Points], tuple[str, str]]


class F0AuditError(ValueError):
    """Invalid evidence or unsupported audit input."""


@dataclass(frozen=True, slots=True)
class _Policy:
    max_objectives: int
    max_contact_pairs: int
    coordinate_tolerance_mm: float
    force_tolerance_n: float
    energy_tolerance_n_mm: float


@dataclass(frozen=True, slots=True)
class _Objective:
    energy_n_mm: float
    forces_n: Points
    maximum_force_n: float
    terms: dict[str, JSONValue]


def audit_closed_f0(
    projection: PhysicalSemanticProjection,
    material: dict[str, JSONValue],
    recipe: object,
    result: object,
    *,
    validator: SemanticValidator,
    policy: object,
    gauge_scenario: GaugeScenario | None = None,
    gauge_policy: object | None = None,
) -> dict[str, JSONValue]:
    """Reconstruct and replay a claimed successful closed-F0 result.

    The audit is target-free. It independently replays initialization and the
    optimizer decisions, while explicitly sharing force/energy and contact
    kernels. It establishes computational replay only, not physical accuracy.
    """
    observed_work: dict[str, JSONValue] = {
        "objective_evaluations": 0,
        "contact_pair_evaluations": 0,
        "preparation_energy_evaluations": 0,
    }
    try:
        admitted = _admit_policy(policy)
        if not isinstance(projection, PhysicalSemanticProjection):
            raise F0AuditError("projection_type_invalid")
        if not isinstance(validator, SemanticValidator):
            raise F0AuditError("validator_type_invalid")
        if (gauge_scenario is None) != (gauge_policy is None):
            raise F0AuditError("gauge_scenario_requires_policy")
        raw_recipe, recipe_hash = _read_recipe(recipe)
        if not isinstance(result, dict):
            raise F0AuditError("result_type_invalid")
        _preflight_json_value(result)
        _verify_result_hash(result)
        if result.get("status") != "CONVERGED" or result.get("comparison_eligible") is not True:
            raise F0AuditError("result_not_successful")
        if result.get("projection_sha256") != projection.sha256:
            raise F0AuditError("projection_hash_mismatch")
        if result.get("material_sha256") != canonical_hash(
            material, CanonicalProfile.MATERIAL_PROFILE
        ):
            raise F0AuditError("material_hash_mismatch")
        if result.get("recipe_sha256") != recipe_hash:
            raise F0AuditError("recipe_hash_mismatch")
        if result.get("gauge_scenario_sha256") != (
            None if gauge_scenario is None else gauge_scenario.scenario_sha256
        ):
            raise F0AuditError("gauge_scenario_hash_mismatch")
        _validate_recipe_payload(raw_recipe)
        replayed = _replay(
            projection,
            material,
            raw_recipe,
            cast(dict[str, object], result),
            validator,
            admitted,
            gauge_scenario,
            gauge_policy,
            observed_work,
        )
        _compare_result(result, replayed, admitted)
        return {
            "profile": PROFILE,
            "status": "PASS",
            "outcome_scope": "TARGET_FREE_F0_COMPUTATIONAL_REPLAY",
            "authenticity": "NOT_ESTABLISHED",
            "verification_state": "NOT_VERIFIED",
            "physical_status": "UNTESTED",
            "constitutive_status": "HYPOTHESIS",
            "projection_sha256": projection.sha256,
            "material_sha256": cast(str, result["material_sha256"]),
            "recipe_sha256": recipe_hash,
            "producer_result_sha256": cast(str, result["sha256"]),
            "gauge_scenario_sha256": cast(str | None, result["gauge_scenario_sha256"]),
            "replay_work": replayed["work"],
            "common_mode_limitations": [
                "shared constitutive energy, shell, and exact contact kernels",
                "the same Python binary64 and math library",
                "source authentication and physical accuracy are not established",
            ],
        }
    except ContactError as error:
        if error.code == "contact.budget_exhausted":
            return _failure("INDETERMINATE", "contact_work_budget_exhausted", policy, observed_work)
        return _failure("FAIL", error.reason, policy, observed_work)
    except _AuditBudget as error:
        return _failure("INDETERMINATE", str(error), policy, observed_work)
    except F0AuditError as error:
        return _failure("FAIL", str(error), policy, observed_work)
    except MaterialScenarioError as error:
        return _failure("FAIL", str(error), policy, observed_work)
    except (
        CanonicalizationError,
        ForwardForceError,
        ShellTermsError,
        ValueError,
        OverflowError,
        RecursionError,
        KeyError,
        TypeError,
    ) as error:
        return _failure("FAIL", f"{type(error).__name__}:{error}", policy, observed_work)


def _admit_policy(value: object) -> _Policy:
    required = {
        "profile",
        "max_replay_objective_evaluations",
        "max_contact_pair_evaluations",
        "coordinate_abs_tolerance_mm",
        "force_abs_tolerance_n",
        "energy_abs_tolerance_n_mm",
        "tolerance_owner",
        "tolerance_rationale",
        "validation_path",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise F0AuditError("audit_policy_fields_invalid")
    if value["profile"] != "FORWARD_F0_AUDIT_POLICY_V1":
        raise F0AuditError("audit_policy_profile_unsupported")
    for key, maximum in (
        ("max_replay_objective_evaluations", _MAX_REPLAY_OBJECTIVES),
        ("max_contact_pair_evaluations", _MAX_REPLAY_CONTACT_PAIRS),
    ):
        count = value[key]
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= maximum:
            raise F0AuditError("audit_policy_work_budget_invalid")
    for key in ("tolerance_owner", "tolerance_rationale", "validation_path"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise F0AuditError("audit_policy_tolerance_provenance_missing")
    tolerances: list[float] = []
    for key in (
        "coordinate_abs_tolerance_mm",
        "force_abs_tolerance_n",
        "energy_abs_tolerance_n_mm",
    ):
        number = value[key]
        if not isinstance(number, (int, float)) or isinstance(number, bool):
            raise F0AuditError("audit_policy_tolerance_invalid")
        if isinstance(number, int) and abs(number) > SAFE_INTEGER:
            raise F0AuditError("audit_policy_tolerance_invalid")
        as_float = float(number)
        if not math.isfinite(as_float) or as_float < 0:
            raise F0AuditError("audit_policy_tolerance_invalid")
        tolerances.append(as_float)
    return _Policy(
        int(value["max_replay_objective_evaluations"]),
        int(value["max_contact_pair_evaluations"]),
        tolerances[0],
        tolerances[1],
        tolerances[2],
    )


def _read_recipe(recipe: object) -> tuple[dict[str, JSONValue], str]:
    encoded = getattr(recipe, "canonical_bytes", None)
    claimed_hash = getattr(recipe, "sha256", None)
    if not isinstance(encoded, bytes) or not isinstance(claimed_hash, str):
        raise F0AuditError("recipe_binding_missing")
    if len(encoded) > _MAX_INPUT_BYTES:
        raise F0AuditError("recipe_byte_budget_exceeded")
    raw = parse_json(encoded)
    _preflight_json_value(raw)
    if not isinstance(raw, dict) or jcs_bytes(raw) != encoded:
        raise F0AuditError("recipe_not_canonical")
    digest = _f0_digest(encoded)
    if digest != claimed_hash:
        raise F0AuditError("recipe_hash_mismatch")
    return raw, digest


def _validate_recipe_payload(raw: dict[str, JSONValue]) -> None:
    required = {
        "profile",
        "closed_recipe",
        "shell_parameters",
        "contact_parameters",
        "solver_parameters",
    }
    if set(raw) != required or raw["profile"] != _F0_PROFILE:
        raise F0AuditError("recipe_fields_or_profile_invalid")
    admit_closed_mechanics_recipe(raw["closed_recipe"])
    admit_shell_parameters(raw["shell_parameters"])
    admit_contact_parameters(raw["contact_parameters"])
    solver = raw["solver_parameters"]
    if not isinstance(solver, dict) or set(solver) != {
        "schema_version",
        "initialization_rule",
        "start_count",
        "perturbation_mm",
        "seed",
    }:
        raise F0AuditError("solver_parameters_invalid")
    if solver["initialization_rule"] != _INITIALIZATION_RULE:
        raise F0AuditError("initialization_rule_unsupported")
    if solver["schema_version"] != "1.0.0":
        raise F0AuditError("solver_schema_unsupported")
    start_count, seed, amplitude = solver["start_count"], solver["seed"], solver["perturbation_mm"]
    if (
        not isinstance(start_count, int)
        or isinstance(start_count, bool)
        or not 2 <= start_count <= 4
    ):
        raise F0AuditError("solver_start_count_invalid")
    if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed <= 4_294_967_295:
        raise F0AuditError("solver_seed_invalid")
    if (
        not isinstance(amplitude, (int, float))
        or isinstance(amplitude, bool)
        or not math.isfinite(float(amplitude))
        or float(amplitude) <= 0
    ):
        raise F0AuditError("solver_perturbation_invalid")


def _f0_digest(encoded: bytes) -> str:
    return sha256(b"Crochet.AI\0FORWARD_CLOSED_F0_V1\0" + encoded).hexdigest()


def _preflight_json_value(value: object) -> None:
    """Bound untrusted audit evidence before recursive conversion/canonicalization."""
    pending: list[tuple[object, int]] = [(value, 0)]
    visited = text_characters = 0
    while pending:
        node, depth = pending.pop()
        visited += 1
        if depth > _MAX_INPUT_DEPTH or visited > _MAX_INPUT_NODES:
            raise F0AuditError("audit_input_complexity_exceeded")
        if isinstance(node, str):
            text_characters += len(node)
        elif isinstance(node, dict):
            if visited + len(pending) + len(node) > _MAX_INPUT_NODES:
                raise F0AuditError("audit_input_complexity_exceeded")
            for key, item in node.items():
                if not isinstance(key, str):
                    raise F0AuditError("audit_input_key_invalid")
                text_characters += len(key)
                pending.append((item, depth + 1))
        elif isinstance(node, list):
            if visited + len(pending) + len(node) > _MAX_INPUT_NODES:
                raise F0AuditError("audit_input_complexity_exceeded")
            pending.extend((item, depth + 1) for item in node)
        elif node is not None and type(node) not in (bool, int, float):
            raise F0AuditError("audit_input_type_invalid")
        if text_characters > _MAX_INPUT_BYTES:
            raise F0AuditError("audit_input_text_budget_exceeded")


def _verify_result_hash(result: dict[str, object]) -> None:
    if not isinstance(result.get("sha256"), str):
        raise F0AuditError("result_hash_missing")
    payload = {key: _json_value(value) for key, value in result.items() if key != "sha256"}
    if _f0_digest(jcs_bytes(payload)) != result["sha256"]:
        raise F0AuditError("result_hash_invalid")


def _failure(
    status: str, reason: str, policy: object, observed_work: dict[str, JSONValue]
) -> dict[str, JSONValue]:
    try:
        admitted = _admit_policy(policy)
        work: dict[str, JSONValue] = {
            "max_replay_objective_evaluations": admitted.max_objectives,
            "max_contact_pair_evaluations": admitted.max_contact_pairs,
            **observed_work,
        }
    except F0AuditError:
        work = {"policy_admitted": False, **observed_work}
    return {
        "profile": PROFILE,
        "status": status,
        "reason": reason,
        "outcome_scope": "TARGET_FREE_F0_COMPUTATIONAL_REPLAY",
        "authenticity": "NOT_ESTABLISHED",
        "verification_state": "NOT_VERIFIED",
        "physical_status": "UNTESTED",
        "constitutive_status": "HYPOTHESIS",
        "replay_work": work,
    }


def _replay(
    projection: PhysicalSemanticProjection,
    material: dict[str, JSONValue],
    raw_recipe: dict[str, JSONValue],
    producer_result: dict[str, object],
    validator: SemanticValidator,
    policy: _Policy,
    gauge_scenario: GaugeScenario | None,
    gauge_policy: object | None,
    observed_work: dict[str, JSONValue],
) -> dict[str, JSONValue]:
    closed = cast(dict[str, JSONValue], raw_recipe["closed_recipe"])
    elastic_recipe = admit_shaped_forward_recipe(closed["elastic_recipe"])
    elastic = inspect_shaped_forward_model(
        projection, material, elastic_recipe, validator=validator
    )
    observed_work["preparation_energy_evaluations"] = 1
    cells = build_closed_surface_cells(projection, max_vertices=2048, max_faces=4096)
    cell_data = cells.to_dict()
    vertices = tuple(cast(list[str], cell_data["vertices"]))
    face_rows = cast(
        tuple[tuple[str, str, str], ...],
        tuple(tuple(cast(list[str], row)) for row in cast(list[JSONValue], cell_data["faces"])),
    )
    if any(len(face) != 3 for face in face_rows):
        raise F0AuditError("surface_triangle_invalid")
    original = _coordinates(elastic)
    elastic_raw = cast(dict[str, JSONValue], closed["elastic_recipe"])
    inputs = admit_forward_inputs(
        cast(Mapping[str, object], elastic_raw["loading"]),
        cast(Mapping[str, object], elastic_raw["model_profile"]),
        cast(Mapping[str, object], elastic_raw["config"]),
    )
    stretch = _spring_terms(elastic)
    if gauge_scenario is not None:
        if gauge_policy is None:
            raise F0AuditError("gauge_policy_missing")
        graph = lower_forward_graph(
            projection,
            material,
            cast(str, elastic_raw["tension_profile_id"]),
            cast(str, elastic_raw["fabric_state"]),
            validator=validator,
        )
        validate_gauge_scenario(
            graph, gauge_scenario, material_profile=material, policy=gauge_policy
        )
        derived_graph = _scenario_graph(graph, gauge_scenario)
        rest = cast(dict[str, JSONValue], elastic_raw["rest_parameters"])
        original = initialize_shaped_coordinates(projection.to_dict(), derived_graph, rest)
        stretch = derive_shaped_terms(derived_graph, inputs, rest)
    if set(vertices) != set(original):
        raise F0AuditError("surface_vertex_set_mismatch")
    shell = prepare_shell_terms(
        vertices, face_rows, admit_shell_parameters(raw_recipe["shell_parameters"])
    )
    ordered = tuple(sorted(vertices))
    index = {key: i for i, key in enumerate(ordered)}
    integer_faces = tuple(
        cast(tuple[int, int, int], tuple(index[key] for key in face)) for face in face_rows
    )
    contact_surface = prepare_surface_contact(
        tuple(original[key] for key in ordered), integer_faces
    )
    contact_parameters = admit_contact_parameters(raw_recipe["contact_parameters"])
    contact_parameters = replace(
        contact_parameters,
        max_pair_evaluations=min(contact_parameters.max_pair_evaluations, policy.max_contact_pairs),
    )
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
    objective_count = 0

    def record_work() -> None:
        observed_work.update(
            {
                "objective_evaluations": objective_count,
                "contact_pair_evaluations": budget.pair_evaluations,
                "contact_exact_distance_evaluations": budget.exact_distance_evaluations,
                "contact_path_pair_proofs": budget.path_pair_proofs,
                "contact_indeterminate_pair_proofs": budget.indeterminate_pair_proofs,
                "contact_broadphase_candidate_tests": budget.broadphase_candidate_tests,
                "contact_exact_pair_tests": budget.exact_pair_tests,
            }
        )

    def evaluate_objective(points: Points) -> _Objective:
        nonlocal objective_count
        if objective_count >= policy.max_objectives:
            raise _AuditBudget("objective_budget_exhausted")
        objective_count += 1
        contact = evaluate_contact(
            contact_surface,
            tuple(points[key] for key in ordered),
            contact_parameters,
            budget,
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
        shell_forces, contact_forces = dict(shell_value.forces_n), dict(contact.forces_n)
        forces: Points = {
            key: cast(
                Vec3,
                tuple(
                    _finite_fsum(
                        (
                            mechanical[1][key][axis],
                            shell_forces[key][axis],
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
        return _Objective(energy, forces, max(math.hypot(*row) for row in forces.values()), terms)

    def objective(points: Points) -> _Objective:
        try:
            return evaluate_objective(points)
        finally:
            record_work()

    def certify(start: Points, end: Points) -> tuple[str, str]:
        try:
            certificate = certify_contact_path(
                contact_surface,
                tuple(start[key] for key in ordered),
                tuple(end[key] for key in ordered),
                contact_parameters,
                budget,
            )
        finally:
            record_work()
        return certificate.status, certificate.reason

    solver = cast(dict[str, JSONValue], raw_recipe["solver_parameters"])
    start_count = cast(int, solver["start_count"])
    actual_starts = producer_result.get("starts")
    if not isinstance(actual_starts, list) or len(actual_starts) != start_count:
        raise F0AuditError("start_count_mismatch")
    seed = cast(int, solver["seed"])
    amplitude = cast(float, solver["perturbation_mm"])
    first_face = face_rows[0]
    start_replays: list[dict[str, JSONValue]] = []
    final_points: list[Points] = []
    final_objectives: list[_Objective] = []
    for start_index in range(start_count):
        initial = _independent_gauge(
            _independent_initialize(original, start_index, seed, amplitude), first_face
        )
        points, final, stats = _replay_start(
            initial,
            cast(dict[str, object], actual_starts[start_index]),
            start_index,
            objective,
            certify,
            inputs,
            policy,
        )
        start_replays.append(stats)
        final_points.append(points)
        final_objectives.append(final)
    gauged = [_independent_gauge(points, first_face) for points in final_points]
    rms = max(
        math.sqrt(_finite_fsum(math.dist(a[key], b[key]) ** 2 for key in ordered) / len(ordered))
        for i, a in enumerate(gauged)
        for b in gauged[i + 1 :]
    )
    tolerance = dict(inputs.tolerances)["mode_equivalence_rms_mm"].value
    if rms > tolerance:
        raise F0AuditError("replayed_starts_are_multimodal")
    winner_index = min(
        range(len(final_objectives)), key=lambda ordinal: final_objectives[ordinal].energy_n_mm
    )
    winner = final_points[winner_index]
    winner_objective = final_objectives[winner_index]
    return {
        "coordinates_mm": _point_rows(winner),
        "faces": [cast(JSONValue, list(face)) for face in face_rows],
        "final_mechanics": winner_objective.terms,
        "mode_equivalence_rms_mm": rms,
        "starts": [cast(JSONValue, row) for row in start_replays],
        "surface_cells_sha256": cells.sha256,
        "shell_terms_sha256": shell.sha256,
        "contact_surface_sha256": contact_surface.topology_sha256,
        "initial_bundle_sha256": elastic["sha256"],
        "initial_coordinates_sha256": _point_hash(original),
        "forward_inputs_sha256": inputs.sha256,
        "solver_parameters": solver,
        "optimizer_policy": {
            "armijo_c": _ARMijo_C,
            "backtracking_factor": _BACKTRACK,
            "initial_alpha_mm_per_n": _INITIAL_ALPHA,
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
        "work_budget_scopes": {
            "max_initializations": "ELASTIC_PREPARATION_ONLY_EXACTLY_ONE",
            "start_count": "ALL_REQUIRED_F0_STARTS_EXACT_DECLARED_COUNT",
            "max_initialization_vertices": "EVERY_START",
            "max_contact_pairs_evaluated": "CUMULATIVE_ALL_STARTS_AND_TRIALS",
            "max_linear_iterations": "NOT_APPLICABLE_NO_LINEAR_SOLVER",
        },
        "preparation_energy_evaluations": 1,
        "profile": _F0_PROFILE,
        "reason": "all_starts_converged",
        "verification_state": "NOT_VERIFIED",
        "physical_status": "UNTESTED",
        "constitutive_status": "HYPOTHESIS",
        "v6_status": "NOT_RUN",
        "comparison_eligible": True,
        "contact_work": {
            "pair_evaluations": budget.pair_evaluations,
            "exact_distance_evaluations": budget.exact_distance_evaluations,
            "path_pair_proofs": budget.path_pair_proofs,
            "indeterminate_pair_proofs": budget.indeterminate_pair_proofs,
            "broadphase_candidate_tests": budget.broadphase_candidate_tests,
            "exact_pair_tests": budget.exact_pair_tests,
        },
        "work": {
            "objective_evaluations": objective_count,
            "contact_pair_evaluations": budget.pair_evaluations,
            "contact_exact_distance_evaluations": budget.exact_distance_evaluations,
            "contact_path_pair_proofs": budget.path_pair_proofs,
            "contact_indeterminate_pair_proofs": budget.indeterminate_pair_proofs,
            "contact_broadphase_candidate_tests": budget.broadphase_candidate_tests,
            "contact_exact_pair_tests": budget.exact_pair_tests,
        },
    }


class _AuditBudget(ValueError):
    pass


def _scenario_graph(graph: object, scenario: GaugeScenario) -> ForwardGraph:
    if not isinstance(graph, ForwardGraph):
        raise F0AuditError("graph_type_invalid")
    endpoints = {endpoint.response_id: endpoint for endpoint in scenario.endpoints}
    responses = []
    for response in graph.material_responses:
        endpoint = endpoints.get(response.response_id)
        responses.append(
            response
            if endpoint is None
            else replace(
                response,
                effective_stitch_pitch_mm=endpoint.stitch_pitch_mm,
                effective_course_pitch_mm=endpoint.course_pitch_mm,
            )
        )
    return replace(graph, material_responses=tuple(responses))


def _independent_initialize(points: Points, start: int, seed: int, amplitude: float) -> Points:
    if start == 0:
        return dict(points)
    perturbed: Points = {}
    for index, (label, point) in enumerate(sorted(points.items())):
        moved: list[float] = []
        for axis in range(3):
            phase_numerator = (seed + 104729 * start + 8191 * (index + 1) + 127 * axis) % 1048576
            phase = phase_numerator * math.tau / 1048576
            moved.append(point[axis] + amplitude * math.sin(phase))
        perturbed[label] = cast(Vec3, tuple(moved))
    return perturbed


def _independent_gauge(points: Mapping[str, Vec3], face: tuple[str, str, str]) -> Points:
    labels = sorted(points)
    origin: Vec3 = cast(
        Vec3,
        tuple(
            math.fsum(points[label][axis] for label in labels) / len(labels) for axis in range(3)
        ),
    )
    first, second, third = (points[label] for label in face)
    edge = tuple(second[axis] - first[axis] for axis in range(3))
    edge_length = math.hypot(*edge)
    if not math.isfinite(edge_length) or edge_length == 0:
        raise F0AuditError("replay_gauge_degenerate")
    x_axis: Vec3 = cast(Vec3, tuple(value / edge_length for value in edge))
    to_third = tuple(third[axis] - first[axis] for axis in range(3))
    projection = math.fsum(x_axis[axis] * to_third[axis] for axis in range(3))
    rejected = tuple(to_third[axis] - projection * x_axis[axis] for axis in range(3))
    rejected_length = math.hypot(*rejected)
    if not math.isfinite(rejected_length) or rejected_length == 0:
        raise F0AuditError("replay_gauge_degenerate")
    y_axis: Vec3 = cast(Vec3, tuple(value / rejected_length for value in rejected))
    z_axis: Vec3 = (
        x_axis[1] * y_axis[2] - x_axis[2] * y_axis[1],
        x_axis[2] * y_axis[0] - x_axis[0] * y_axis[2],
        x_axis[0] * y_axis[1] - x_axis[1] * y_axis[0],
    )
    axes = (x_axis, y_axis, z_axis)
    return {
        label: cast(
            Vec3,
            tuple(
                math.fsum((points[label][axis] - origin[axis]) * basis[axis] for axis in range(3))
                for basis in axes
            ),
        )
        for label in labels
    }


def _point_rows(points: Points) -> list[JSONValue]:
    return [
        {"attachment_location_id": label, "position_mm": list(position)}
        for label, position in sorted(points.items())
    ]


def _point_hash(points: Points) -> str:
    return sha256(
        b"Crochet.AI\0FORWARD_CLOSED_F0_V1\0" + jcs_bytes(_point_rows(points))
    ).hexdigest()


def _replay_start(
    initial: Points,
    actual: dict[str, object],
    start_index: int,
    evaluate: ObjectiveEvaluator,
    certify: PathCertifier,
    inputs: ForwardInputs,
    policy: _Policy,
) -> tuple[Points, _Objective, dict[str, JSONValue]]:
    trace = actual.get("trace")
    if not isinstance(trace, list):
        raise F0AuditError("start_trace_missing")
    cursor = 0
    iterations = trials = stationary = objective_count = 0
    last_step, relative_change = 0.0, 0.0
    points = dict(initial)

    def objective(at: Points) -> _Objective:
        nonlocal objective_count
        if objective_count >= inputs.max_energy_evaluations:
            raise F0AuditError("trace_claimed_success_after_objective_budget")
        objective_count += 1
        return evaluate(at)

    final = objective(points)
    tolerances = dict(inputs.tolerances)

    def consume(expected: dict[str, JSONValue]) -> None:
        nonlocal cursor
        if cursor >= len(trace):
            raise F0AuditError("trace_event_missing")
        _compare_value(trace[cursor], expected, policy, f"trace/{cursor}")
        cursor += 1

    while True:
        if (
            final.maximum_force_n <= tolerances["force_residual_n"].value
            and last_step <= tolerances["position_step_mm"].value
            and relative_change <= tolerances["relative_energy_change"].value
        ):
            stationary += 1
            consume(
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
                break
            repeated = objective(points)
            relative_change = abs(repeated.energy_n_mm - final.energy_n_mm) / max(
                abs(final.energy_n_mm), abs(repeated.energy_n_mm), 1.0
            )
            final = repeated
            continue

        stationary = 0
        if iterations >= inputs.max_optimizer_iterations:
            raise F0AuditError("trace_claimed_success_after_iteration_budget")
        norm_squared = _finite_fsum(
            value * value for row in final.forces_n.values() for value in row
        )
        if not math.isfinite(norm_squared) or norm_squared < 0:
            raise F0AuditError("replay_force_norm_invalid")
        accepted = False
        alpha = 1.0
        for local_trial in range(inputs.max_line_search_trials):
            trials += 1
            proposed: Points = {
                key: cast(
                    Vec3,
                    tuple(
                        points[key][axis] + alpha * final.forces_n[key][axis] for axis in range(3)
                    ),
                )
                for key in sorted(points)
            }
            if any(not math.isfinite(value) for row in proposed.values() for value in row):
                consume(
                    {
                        "kind": "TRIAL",
                        "alpha_mm_per_n": alpha,
                        "cause": "NON_FINITE_COORDINATES",
                        "accepted": False,
                    }
                )
                alpha *= 0.5
                continue
            path_status, path_reason = certify(points, proposed)
            if path_status == "BUDGET_EXHAUSTED":
                raise _AuditBudget("contact_path_work_budget_exhausted")
            if path_status != "SAFE":
                consume(
                    {
                        "kind": "TRIAL",
                        "alpha_mm_per_n": alpha,
                        "cause": path_reason,
                        "accepted": False,
                    }
                )
                alpha *= 0.5
                continue
            try:
                trial = objective(proposed)
            except (ContactError, ShellTermsError, ForwardForceError) as error:
                if isinstance(error, ContactError) and error.code == "contact.budget_exhausted":
                    raise _AuditBudget("contact_work_budget_exhausted") from error
                reason = (
                    error.reason
                    if isinstance(error, (ContactError, ForwardForceError))
                    else str(error)
                )
                consume(
                    {
                        "kind": "TRIAL",
                        "alpha_mm_per_n": alpha,
                        "cause": reason,
                        "accepted": False,
                    }
                )
                alpha *= _BACKTRACK
                continue
            armijo_decrease = _ARMijo_C * alpha * norm_squared
            if not math.isfinite(armijo_decrease):
                raise F0AuditError("armijo_decrease_nonfinite")
            if trial.energy_n_mm <= final.energy_n_mm - armijo_decrease:
                last_step = max(math.dist(points[key], proposed[key]) for key in points)
                relative_change = abs(trial.energy_n_mm - final.energy_n_mm) / max(
                    abs(final.energy_n_mm), abs(trial.energy_n_mm), 1.0
                )
                consume(
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
            consume(
                {
                    "kind": "TRIAL",
                    "trial": local_trial,
                    "alpha_mm_per_n": alpha,
                    "cause": "ARMIJO_DECREASE_FAILED",
                    "accepted": False,
                }
            )
            alpha *= _BACKTRACK
        if not accepted:
            raise F0AuditError("trace_claimed_success_after_line_search_exhaustion")

    if cursor != len(trace):
        raise F0AuditError("trace_contains_unreplayed_events")
    if (
        actual.get("status") != "CONVERGED"
        or actual.get("reason") != "all_stationary_predicates_pass"
    ):
        raise F0AuditError("start_terminal_status_invalid")
    expected_stats: dict[str, JSONValue] = {
        "start_index": start_index,
        "status": "CONVERGED",
        "reason": "all_stationary_predicates_pass",
        "optimizer_iterations": iterations,
        "energy_evaluations": objective_count,
        "line_search_trials": trials,
        "stationary_checks": stationary,
        "last_step_mm": last_step,
        "relative_energy_change": relative_change,
        "maximum_force_n": final.maximum_force_n,
        "energy_n_mm": final.energy_n_mm,
        "coordinates_mm": _point_rows(points),
        "trace": trace,
    }
    _compare_start_summary(actual, expected_stats, policy)
    return points, final, expected_stats


def _compare_result(
    actual: dict[str, object], expected: dict[str, JSONValue], policy: _Policy
) -> None:
    _compare_coordinates(actual.get("coordinates_mm"), expected["coordinates_mm"], "coordinates_mm")
    fields = (
        "coordinates_mm",
        "faces",
        "final_mechanics",
        "mode_equivalence_rms_mm",
        "starts",
        "surface_cells_sha256",
        "shell_terms_sha256",
        "contact_surface_sha256",
        "initial_bundle_sha256",
        "initial_coordinates_sha256",
        "forward_inputs_sha256",
        "contact_work",
        "solver_parameters",
        "optimizer_policy",
        "work_budget_scopes",
        "preparation_energy_evaluations",
        "profile",
        "reason",
        "verification_state",
        "physical_status",
        "constitutive_status",
        "v6_status",
        "comparison_eligible",
    )
    if set(actual) != set(fields) | {
        "status",
        "projection_sha256",
        "material_sha256",
        "recipe_sha256",
        "gauge_scenario_sha256",
        "sha256",
        "limitations",
    }:
        raise F0AuditError("result_fields_invalid")
    _compare_value(
        actual["limitations"],
        [
            "uniform_constitutive_hypothesis",
            "bounded_observed_multistart",
            "independent_v6_admission_required",
            "physical_calibration_required",
        ],
        policy,
        "limitations",
    )
    for field in fields:
        if field not in actual or field not in expected:
            raise F0AuditError(f"result_field_missing:{field}")
        _compare_value(actual[field], expected[field], policy, field)


def _compare_start_summary(
    actual: dict[str, object], expected: dict[str, JSONValue], policy: _Policy
) -> None:
    if set(actual) != set(expected):
        raise F0AuditError("start_fields_invalid")
    _compare_coordinates(
        actual.get("coordinates_mm"), expected["coordinates_mm"], "start/coordinates_mm"
    )
    for field, expected_value in expected.items():
        if field not in actual:
            raise F0AuditError(f"start_field_missing:{field}")
        _compare_value(actual[field], expected_value, policy, field)


def _compare_coordinates(actual: object, expected: JSONValue, path: str) -> None:
    # The replayed prediction is authoritative. A diagnostic comparison tolerance
    # cannot authorize substituting different geometry for the subsequent V7 run.
    if jcs_bytes(_json_value(actual)) != jcs_bytes(expected):
        raise F0AuditError(f"evidence_mismatch:{path}")


def _compare_value(actual: object, expected: object, policy: _Policy, path: str) -> None:
    if isinstance(expected, bool) or expected is None or isinstance(expected, (str, int)):
        if type(actual) is not type(expected) or actual != expected:
            raise F0AuditError(f"evidence_mismatch:{path}")
        return
    if isinstance(expected, float):
        if not isinstance(actual, (float, int)) or isinstance(actual, bool):
            raise F0AuditError(f"evidence_type_mismatch:{path}")
        if not math.isfinite(float(actual)):
            raise F0AuditError(f"evidence_nonfinite:{path}")
        tolerance = (
            policy.coordinate_tolerance_mm
            if "position_mm" in path
            or path.endswith("coordinates_mm")
            or "position_step_mm" in path
            else policy.force_tolerance_n
            if "force" in path or "residual" in path
            else policy.energy_tolerance_n_mm
            if "energy_n_mm" in path
            else 0.0
        )
        if abs(float(actual) - expected) > tolerance:
            raise F0AuditError(f"evidence_mismatch:{path}")
        return
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise F0AuditError(f"evidence_mismatch:{path}")
        for index, (observed_item, expected_item) in enumerate(zip(actual, expected, strict=True)):
            _compare_value(observed_item, expected_item, policy, f"{path}/{index}")
        return
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(actual) != set(expected):
            raise F0AuditError(f"evidence_mismatch:{path}")
        for key, expected_value in expected.items():
            _compare_value(actual[key], expected_value, policy, f"{path}/{key}")
        return
    raise F0AuditError(f"evidence_type_unsupported:{path}")


def _json_value(value: object) -> JSONValue:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise F0AuditError("result_nonfinite")
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise F0AuditError("result_key_invalid")
        return {key: _json_value(item) for key, item in value.items()}
    raise F0AuditError("result_value_invalid")
