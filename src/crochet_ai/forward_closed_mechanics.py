"""Experimental pressure and tension-only closure mechanics for closed SC cells."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, NoReturn, cast

from .canonical import SAFE_INTEGER, CanonicalizationError, jcs_bytes, parse_json
from .forward_closed_cells import build_closed_surface_cells
from .forward_forces import ForwardForceError, _evaluate_stretch_terms_at_coordinates
from .forward_inputs import ForwardInputError, admit_forward_inputs
from .forward_shaped import (
    ForwardShapedError,
    admit_shaped_forward_recipe,
    inspect_shaped_forward_model,
)
from .forward_shear import (
    ARMIJO_C,
    BACKTRACK_FACTOR,
    INITIAL_ALPHA_MM_PER_N,
    _run_armijo,
)
from .forward_stretch import StretchTerm
from .json_types import JSONValue
from .physical_projection import PhysicalSemanticProjection
from .surface_topology import SurfaceTopologyInputError, audit_surface_topology
from .validation import SemanticValidator

PROFILE = "FORWARD_CLOSED_MECHANICS_PROTOTYPE_V1"
_CLOSURE_FIELDS = {
    "schema_version",
    "status",
    "provenance_id",
    "ring_rest_perimeter_mm",
    "ring_stiffness_n_per_mm",
    "close_rest_perimeter_mm",
    "close_stiffness_n_per_mm",
}
_PRESSURE_FIELDS = {
    "schema_version",
    "status",
    "loading_profile_id",
    "provenance_id",
    "pressure_n_per_mm2",
    "volume_limit_mm3",
}


class ForwardClosedMechanicsError(ValueError):
    """Stable fail-closed error for closed mechanics input or numerical failures."""

    def __init__(self, code: str, reason: str) -> None:
        self.code = code
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ClosedMechanicsRecipe:
    canonical_bytes: bytes
    sha256: str


def admit_closed_mechanics_recipe(value: object) -> ClosedMechanicsRecipe:
    raw = _closed(
        value, {"profile", "elastic_recipe", "closure_parameters", "pressure_loading"}, "recipe"
    )
    if raw["profile"] != PROFILE:
        _fail("E_UNSUPPORTED_FEATURE", "recipe.unsupported_profile")
    try:
        elastic = admit_shaped_forward_recipe(raw["elastic_recipe"])
        elastic_value = parse_json(elastic.canonical_bytes)
        if not isinstance(elastic_value, dict):
            _fail("E_INPUT", "elastic_recipe.payload")
        loading = _as_mapping(elastic_value["loading"], "elastic_recipe.loading")
        model = _as_mapping(elastic_value["model_profile"], "elastic_recipe.model_profile")
        config = _as_mapping(elastic_value["config"], "elastic_recipe.config")
        inputs = admit_forward_inputs(loading, model, config)
    except (ForwardShapedError, ForwardInputError, CanonicalizationError) as error:
        _fail("E_INPUT", f"elastic_recipe.invalid:{error}")
    if (
        inputs.max_initializations != 1
        or inputs.max_initialization_vertices > 2048
        or inputs.max_optimizer_iterations > 128
        or inputs.max_energy_evaluations > 512
        or inputs.max_line_search_trials > 32
    ):
        _fail("E_INPUT", "recipe.work_budget_exceeded")
    closure = _closed(raw["closure_parameters"], _CLOSURE_FIELDS, "closure_parameters")
    if closure["schema_version"] != "1.0.0" or closure["status"] != "HYPOTHESIS":
        _fail("E_INPUT", "closure_parameters.version_or_status")
    _identifier(closure["provenance_id"], "closure_parameters.provenance_id")
    ring_rest = _number(
        closure["ring_rest_perimeter_mm"], "closure_parameters.ring_rest_perimeter_mm", minimum=0
    )
    ring_k = _number(
        closure["ring_stiffness_n_per_mm"],
        "closure_parameters.ring_stiffness_n_per_mm",
        minimum=0,
        strict=True,
    )
    close_rest = _number(
        closure["close_rest_perimeter_mm"], "closure_parameters.close_rest_perimeter_mm", minimum=0
    )
    close_k = _number(
        closure["close_stiffness_n_per_mm"],
        "closure_parameters.close_stiffness_n_per_mm",
        minimum=0,
        strict=True,
    )
    pressure = _closed(raw["pressure_loading"], _PRESSURE_FIELDS, "pressure_loading")
    if pressure["schema_version"] != "1.0.0" or pressure["status"] != "USER_DECLARED":
        _fail("E_INPUT", "pressure_loading.version_or_status")
    _identifier(pressure["loading_profile_id"], "pressure_loading.loading_profile_id")
    _identifier(pressure["provenance_id"], "pressure_loading.provenance_id")
    pressure_value = _number(
        pressure["pressure_n_per_mm2"], "pressure_loading.pressure_n_per_mm2", minimum=0
    )
    volume_limit = _number(
        pressure["volume_limit_mm3"], "pressure_loading.volume_limit_mm3", minimum=0, strict=True
    )
    input_map = dict(inputs.tolerances)
    orientation_epsilon = input_map["volume_orientation_epsilon_mm3"].value
    if orientation_epsilon >= volume_limit:
        _fail("E_INPUT", "pressure_loading.volume_limit_not_above_orientation_epsilon")
    normalized: dict[str, JSONValue] = {
        "profile": PROFILE,
        "elastic_recipe": cast(JSONValue, elastic_value),
        "closure_parameters": {
            "schema_version": "1.0.0",
            "status": "HYPOTHESIS",
            "provenance_id": closure["provenance_id"],
            "ring_rest_perimeter_mm": ring_rest,
            "ring_stiffness_n_per_mm": ring_k,
            "close_rest_perimeter_mm": close_rest,
            "close_stiffness_n_per_mm": close_k,
        },
        "pressure_loading": {
            "schema_version": "1.0.0",
            "status": "USER_DECLARED",
            "loading_profile_id": pressure["loading_profile_id"],
            "provenance_id": pressure["provenance_id"],
            "pressure_n_per_mm2": pressure_value,
            "volume_limit_mm3": volume_limit,
        },
    }
    try:
        encoded = jcs_bytes(normalized)
    except CanonicalizationError as error:
        _fail("E_INPUT", f"recipe.noncanonical:{error}")
    return ClosedMechanicsRecipe(encoded, _digest(encoded))


def run_closed_mechanics(
    projection: PhysicalSemanticProjection,
    material: dict[str, Any],
    recipe: ClosedMechanicsRecipe,
    *,
    validator: SemanticValidator,
) -> dict[str, JSONValue]:
    if not isinstance(projection, PhysicalSemanticProjection):
        _fail("E_INPUT", "projection.type")
    raw = _validate_recipe(recipe)
    elastic_recipe = admit_shaped_forward_recipe(raw["elastic_recipe"])
    elastic = inspect_shaped_forward_model(
        projection, material, elastic_recipe, validator=validator
    )
    cells = build_closed_surface_cells(projection, max_vertices=2048, max_faces=4096)
    cell_value = cells.to_dict()
    faces = cast(list[list[str]], cell_value["faces"])
    vertices = cast(list[str], cell_value["vertices"])
    coordinates = _coordinates(elastic)
    if set(coordinates) != set(vertices):
        _fail("E_INPUT", "mechanics.vertex_set_mismatch")
    _audit_closed_oriented_faces(faces, vertices)
    projection_value = projection.to_dict()
    ring_cycle, close_cycle = _closure_cycles(projection_value)
    closure = cast(dict[str, Any], raw["closure_parameters"])
    pressure = cast(dict[str, Any], raw["pressure_loading"])
    ring = _perimeter_term(
        "RING_CLOSURE",
        ring_cycle,
        closure["ring_rest_perimeter_mm"],
        closure["ring_stiffness_n_per_mm"],
    )
    close = _perimeter_term(
        "CLOSE_CLOSURE",
        close_cycle,
        closure["close_rest_perimeter_mm"],
        closure["close_stiffness_n_per_mm"],
    )
    input_obj = admit_forward_inputs(
        raw["elastic_recipe"]["loading"],
        raw["elastic_recipe"]["model_profile"],
        raw["elastic_recipe"]["config"],
    )
    epsilon = dict(input_obj.tolerances)["volume_orientation_epsilon_mm3"].value
    terms = _spring_terms(elastic)

    cache_key: tuple[tuple[str, tuple[float, float, float]], ...] | None = None
    cache_value: (
        tuple[float, dict[str, tuple[float, float, float]], float, dict[str, Any]] | None
    ) = None
    initial_mechanics: dict[str, Any] | None = None

    def evaluate(
        points: Mapping[str, tuple[float, float, float]],
    ) -> tuple[float, dict[str, tuple[float, float, float]], float]:
        nonlocal cache_key, cache_value, initial_mechanics
        ordered = tuple(sorted(points.items()))
        if ordered == cache_key and cache_value is not None:
            e, f, maximum, _ = cache_value
            return e, f, maximum
        mechanics = _evaluate_checked(
            terms,
            ring,
            close,
            pressure["pressure_n_per_mm2"],
            faces,
            points,
            epsilon,
            pressure["volume_limit_mm3"],
        )
        _validate_optimizer_force_norm(mechanics[1])
        cache_key = ordered
        cache_value = mechanics
        if ordered == tuple(sorted(coordinates.items())):
            initial_mechanics = mechanics[3]
        return mechanics[0], mechanics[1], mechanics[2]

    result = _run_armijo(
        coordinates,
        input_obj,
        evaluate,
        recoverable_trial_error=lambda error: (
            isinstance(error, ForwardForceError)
            and str(error) in {"closed.volume_invalid", "closed.edge_zero_or_non_finite"}
        ),
    )
    final = (
        cache_value
        if result.coordinates is not None and cache_key == tuple(sorted(result.coordinates.items()))
        else None
    )
    balanced = result.status == "EXPERIMENTAL_FORCE_BALANCED" and final is not None
    payload: dict[str, JSONValue] = {
        "profile": PROFILE,
        "status": result.status,
        "geometry_role": "EXPERIMENTAL_DEBUG_ONLY" if balanced else "NONE",
        "comparison_eligible": False,
        "verification_state": "NOT_VERIFIED",
        "physical_status": "UNTESTED",
        "v6_status": "NOT_RUN",
        "projection_sha256": projection.sha256,
        "material_sha256": elastic["material_sha256"],
        "forward_inputs_sha256": input_obj.sha256,
        "recipe_sha256": recipe.sha256,
        "surface_cells_sha256": cells.sha256,
        "initial_bundle_sha256": elastic["sha256"],
        "initial_mechanics": None
        if initial_mechanics is None
        else _mechanics_record(initial_mechanics),
        "final_mechanics": None if not balanced or final is None else _mechanics_record(final[3]),
        "coordinates_mm": None
        if not balanced or final is None or result.coordinates is None
        else [
            {"attachment_location_id": key, "position_mm": list(point)}
            for key, point in sorted(result.coordinates.items())
        ],
        "faces": None if not balanced else cast(JSONValue, faces),
        "optimizer_iterations": result.optimizer_iterations,
        "energy_evaluations": result.energy_evaluations,
        "line_search_trials": result.line_search_trials,
        "preparation_energy_evaluations": 1,
        "maximum_force_n": result.maximum_force_n,
        "optimizer_policy": {
            "initial_alpha_mm_per_n": INITIAL_ALPHA_MM_PER_N,
            "armijo_c": ARMIJO_C,
            "backtracking_factor": BACKTRACK_FACTOR,
            "force_residual_n": dict(input_obj.tolerances)["force_residual_n"].value,
        },
        "trace": list(result.trace),
        "missing_checks": [
            "closure_yarn_and_cap_material_model",
            "shaped_shear_bending",
            "contact_response_and_path_safety",
            "multistart_and_v6",
            "physical_calibration",
        ],
    }
    encoded = jcs_bytes(payload)
    payload["sha256"] = _digest(encoded)
    return payload


def _evaluate(
    terms: tuple[StretchTerm, ...],
    ring: tuple[Any, ...],
    close: tuple[Any, ...],
    pressure: float,
    faces: list[list[str]],
    points: Mapping[str, tuple[float, float, float]],
    epsilon: float,
    volume_limit: float,
) -> tuple[float, dict[str, tuple[float, float, float]], float, dict[str, Any]]:
    spring_energy, spring_rows, _ = _evaluate_stretch_terms_at_coordinates(terms, dict(points))
    forces: dict[str, list[list[float]]] = defaultdict(lambda: [[], [], []])
    for key, row in spring_rows:
        for axis in range(3):
            forces[key][axis].append(row[axis])
    closure_energy = 0.0
    closure_rows: list[dict[str, Any]] = []
    for kind, cycle, rest, stiffness in (ring, close):
        perimeter = _finite_fsum(
            math.dist(points[a], points[b])
            for a, b in zip(cycle, (*cycle[1:], cycle[0]), strict=True)
        )
        if not math.isfinite(perimeter):
            raise ForwardForceError("closed.perimeter_non_finite")
        tension = stiffness * max(perimeter - rest, 0.0)
        energy = 0.5 * stiffness * max(perimeter - rest, 0.0) ** 2
        if not math.isfinite(tension) or not math.isfinite(energy):
            raise ForwardForceError("closed.closure_non_finite")
        closure_energy = _finite_fsum((closure_energy, energy))
        for a, b in zip(cycle, (*cycle[1:], cycle[0]), strict=True):
            delta = tuple(points[b][i] - points[a][i] for i in range(3))
            distance = math.hypot(*delta)
            if not math.isfinite(distance) or distance == 0.0:
                raise ForwardForceError("closed.edge_zero_or_non_finite")
            scale = tension / distance
            for i in range(3):
                forces[a][i].append(scale * delta[i])
                forces[b][i].append(-scale * delta[i])
        closure_rows.append(
            {
                "kind": kind,
                "perimeter_mm": perimeter,
                "rest_perimeter_mm": rest,
                "tension_n": tension,
                "energy_n_mm": energy,
            }
        )
    volume, pressure_forces = _pressure_geometry(faces, points)
    if not math.isfinite(volume) or volume <= epsilon or volume > volume_limit:
        raise ForwardForceError("closed.volume_invalid")
    pressure_energy = -pressure * volume
    for key, value in pressure_forces.items():
        for axis in range(3):
            forces[key][axis].append(pressure * value[axis])
    force_map: dict[str, tuple[float, float, float]] = {
        key: (
            _finite_fsum(axes[0]),
            _finite_fsum(axes[1]),
            _finite_fsum(axes[2]),
        )
        for key, axes in forces.items()
    }
    for key in points:
        force_map.setdefault(key, (0.0, 0.0, 0.0))
    maximum = max((math.hypot(*value) for value in force_map.values()), default=0.0)
    total = _finite_fsum((spring_energy, closure_energy, pressure_energy))
    if (
        not math.isfinite(total)
        or not math.isfinite(maximum)
        or any(not math.isfinite(v) for row in force_map.values() for v in row)
    ):
        raise ForwardForceError("closed.result_non_finite")
    record = {
        "energy_n_mm": total,
        "elastic_energy_n_mm": spring_energy,
        "closure_energy_n_mm": closure_energy,
        "pressure_energy_n_mm": pressure_energy,
        "volume_mm3": volume,
        "ring_closure": closure_rows[0],
        "close_closure": closure_rows[1],
    }
    return total, force_map, maximum, record


def _evaluate_checked(
    terms: tuple[StretchTerm, ...],
    ring: tuple[Any, ...],
    close: tuple[Any, ...],
    pressure: float,
    faces: list[list[str]],
    points: Mapping[str, tuple[float, float, float]],
    epsilon: float,
    volume_limit: float,
) -> tuple[float, dict[str, tuple[float, float, float]], float, dict[str, Any]]:
    try:
        return _evaluate(terms, ring, close, pressure, faces, points, epsilon, volume_limit)
    except OverflowError as error:
        raise ForwardForceError("closed.arithmetic_overflow") from error


def _validate_optimizer_force_norm(
    force_map: Mapping[str, tuple[float, float, float]],
) -> None:
    try:
        square_sum = math.fsum(
            component * component for force in force_map.values() for component in force
        )
    except OverflowError as error:
        raise ForwardForceError("closed.force_square_overflow") from error
    if not math.isfinite(square_sum):
        raise ForwardForceError("closed.force_square_non_finite")


def _pressure_geometry(
    faces: list[list[str]], points: Mapping[str, tuple[float, float, float]]
) -> tuple[float, dict[str, tuple[float, float, float]]]:
    reference = tuple(
        _finite_fsum(point[i] for point in points.values()) / len(points) for i in range(3)
    )
    contributions: list[float] = []
    parts: dict[str, list[list[float]]] = defaultdict(lambda: [[], [], []])
    for face in faces:
        a, b, c = (points[key] for key in face)
        ar, br, cr = (_sub(point, reference) for point in (a, b, c))
        contributions.append(_dot(ar, _cross(br, cr)) / 6.0)
        area = _cross(_sub(b, a), _sub(c, a))
        for key in face:
            for axis in range(3):
                parts[key][axis].append(area[axis] / 6.0)
    volume = _finite_fsum(contributions)
    return volume, {
        key: (_finite_fsum(axes[0]), _finite_fsum(axes[1]), _finite_fsum(axes[2]))
        for key, axes in parts.items()
    }


def _audit_closed_oriented_faces(faces: list[list[str]], vertices: list[str]) -> None:
    try:
        audit = audit_surface_topology(vertices, faces, max_vertices=2048, max_faces=4096)
    except SurfaceTopologyInputError as error:
        _fail("E_INPUT", f"cells.topology_audit_input:{error}")
    if audit.status != "PASS":
        _fail("E_INPUT", "cells.topology_audit_failed")


def _closure_cycles(value: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    operations = {row["operation_type"]: row for row in value["construction_operations"]}
    frontiers = {row["frontier_id"]: row for row in value["frontiers"]}
    ring = tuple(operations["MAGIC_RING"]["attachment_location_ids"])
    close_op = operations["CLOSE"]
    if len(close_op["input_frontier_ids"]) != 1:
        _fail("E_INPUT", "closure.close_input")
    close = tuple(frontiers[close_op["input_frontier_ids"][0]]["attachment_location_ids"])
    if len(ring) < 3 or len(close) < 3:
        _fail("E_INPUT", "closure.cycle_too_short")
    return ring, close


def _perimeter_term(
    kind: str, cycle: tuple[str, ...], rest: float, stiffness: float
) -> tuple[str, tuple[str, ...], float, float]:
    return kind, cycle, rest, stiffness


def _coordinates(elastic: dict[str, Any]) -> dict[str, tuple[float, float, float]]:
    rows = elastic["coordinates_mm"]
    return {row["attachment_location_id"]: tuple(row["position_mm"]) for row in rows}


def _spring_terms(elastic: dict[str, Any]) -> tuple[StretchTerm, ...]:
    return tuple(
        StretchTerm(
            row["edge_type"],
            row["source_location_id"],
            row["target_location_id"],
            row["rest_length_mm"],
            row["stiffness_n_per_mm"],
            row["response_id"],
        )
        for row in elastic["spring_terms"]
    )


def _mechanics_record(record: dict[str, Any]) -> dict[str, JSONValue]:
    return cast(dict[str, JSONValue], record)


def _sub(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return _finite_fsum(a[i] * b[i] for i in range(3))


def _finite_fsum(values: Iterable[float]) -> float:
    parts = tuple(values)
    if any(not math.isfinite(value) for value in parts):
        raise ForwardForceError("closed.sum_non_finite")
    try:
        total = math.fsum(parts)
    except OverflowError as error:
        raise ForwardForceError("closed.sum_overflow") from error
    if not math.isfinite(total):
        raise ForwardForceError("closed.sum_non_finite")
    return total


def _cross(a: tuple[float, ...], b: tuple[float, ...]) -> tuple[float, float, float]:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _validate_recipe(recipe: object) -> dict[str, Any]:
    if not isinstance(recipe, ClosedMechanicsRecipe):
        _fail("E_INPUT", "recipe.type")
    try:
        raw = parse_json(recipe.canonical_bytes)
        if not isinstance(raw, dict) or admit_closed_mechanics_recipe(raw) != recipe:
            _fail("E_INPUT", "recipe.binding_mismatch")
        return raw
    except (TypeError, ValueError, CanonicalizationError) as error:
        _fail("E_INPUT", f"recipe.binding_mismatch:{error}")


def _closed(value: object, fields: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(k, str) for k in value):
        _fail("E_INPUT", f"{path}.object_required")
    raw = dict(cast(Mapping[str, Any], value))
    extras = set(raw) - fields
    if extras:
        if any(
            any(part in key.casefold() for part in ("target", "embedding", "coordinate"))
            for key in extras
        ):
            _fail("E_INPUT", "input.prohibited_target_field")
        _fail("E_INPUT", f"{path}.fields")
    if set(raw) != fields:
        _fail("E_INPUT", f"{path}.fields")
    return raw


def _identifier(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("E_INPUT", f"{path}.invalid")
    return value


def _as_mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        _fail("E_INPUT", f"{path}.object_required")
    return cast(Mapping[str, object], value)


def _number(value: object, path: str, *, minimum: float, strict: bool = False) -> float:
    if isinstance(value, bool) or type(value) not in (int, float):
        _fail("E_INPUT", f"{path}.number_required")
    if isinstance(value, int) and abs(value) > SAFE_INTEGER:
        _fail("E_INPUT", f"{path}.unsafe_integer")
    try:
        result = float(cast(int | float, value))
    except OverflowError:
        _fail("E_INPUT", f"{path}.out_of_range")
    if not math.isfinite(result) or (result <= minimum if strict else result < minimum):
        _fail("E_INPUT", f"{path}.range")
    return result


def _digest(encoded: bytes) -> str:
    return sha256(b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + encoded).hexdigest()


def _fail(code: str, reason: str) -> NoReturn:
    raise ForwardClosedMechanicsError(code, reason)
