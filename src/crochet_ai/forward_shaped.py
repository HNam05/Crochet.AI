"""Target-free initial elastic diagnostic for a narrow closed SC surface profile.

The result is an experimental rest-state diagnostic, not an optimizer, V6
simulation, independent verifier, or physical validation result.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, NoReturn, cast

from .canonical import SAFE_INTEGER, CanonicalizationError, jcs_bytes, parse_json
from .forward_closed_cells import ClosedCellsError, build_closed_surface_cells
from .forward_forces import ForwardForceError, _evaluate_stretch_terms_at_coordinates
from .forward_graph import ForwardGraph, ForwardGraphError, lower_forward_graph
from .forward_inputs import ForwardInputError, ForwardInputs, admit_forward_inputs
from .forward_stretch import StretchTerm
from .json_types import JSONValue
from .physical_projection import PhysicalSemanticProjection
from .validation import SemanticValidator

PROFILE = "FORWARD_SHAPED_ELASTIC_DIAGNOSTIC_V1"
_SHAPES = {"PLAIN": "PLAIN", "INCREASE": "INCREASE", "DECREASE": "DECREASE"}
_MAX_TERMS = 8192
_MAX_FACES = 4096


class ForwardShapedError(ValueError):
    """Stable classified rejection with no partial diagnostic output."""

    def __init__(self, code: str, reason: str) -> None:
        self.code = code
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ShapedForwardRecipe:
    canonical_bytes: bytes
    sha256: str


def admit_shaped_forward_recipe(value: object) -> ShapedForwardRecipe:
    raw = _closed(
        value,
        {
            "profile",
            "tension_profile_id",
            "fabric_state",
            "loading",
            "model_profile",
            "config",
            "rest_parameters",
        },
        "recipe",
    )
    if raw["profile"] != PROFILE:
        _fail("E_UNSUPPORTED_FEATURE", "recipe.unsupported_profile")
    _identifier(raw["tension_profile_id"], "recipe.tension_profile_id")
    _identifier(raw["fabric_state"], "recipe.fabric_state")
    try:
        inputs = admit_forward_inputs(
            _mapping(raw["loading"], "recipe.loading"),
            _mapping(raw["model_profile"], "recipe.model_profile"),
            _mapping(raw["config"], "recipe.config"),
        )
    except ForwardInputError as error:
        _fail("E_INPUT", error.reason)
    except CanonicalizationError as error:
        _fail("E_INPUT", f"recipe.noncanonical_input:{error}")
    if inputs.max_initializations != 1 or inputs.max_initialization_vertices > 2048:
        _fail("E_INPUT", "recipe.initialization_budget_exceeded")
    rest = _closed(
        raw["rest_parameters"],
        {
            "schema_version",
            "status",
            "provenance_id",
            "wale_rest_length_factors",
            "wale_stiffness_factors",
            "ring_rest_length_mm",
            "ring_stiffness_n_per_mm",
            "ring_initial_chord_mm",
            "ring_initial_offset_mm",
        },
        "rest_parameters",
    )
    if rest["schema_version"] != "1.0.0" or rest["status"] != "HYPOTHESIS":
        _fail("E_INPUT", "rest_parameters.unsupported_version_or_status")
    _identifier(rest["provenance_id"], "rest_parameters.provenance_id")
    for field in ("wale_rest_length_factors", "wale_stiffness_factors"):
        factors = _closed(rest[field], set(_SHAPES), f"rest_parameters.{field}")
        for shape in _SHAPES:
            _positive(factors[shape], f"rest_parameters.{field}.{shape}")
    for field in (
        "ring_rest_length_mm",
        "ring_stiffness_n_per_mm",
        "ring_initial_chord_mm",
        "ring_initial_offset_mm",
    ):
        _positive(rest[field], f"rest_parameters.{field}")
    admitted = {
        "profile": PROFILE,
        "tension_profile_id": raw["tension_profile_id"],
        "fabric_state": raw["fabric_state"],
        "loading": _normalized_input(inputs, "loading"),
        "model_profile": _normalized_input(inputs, "model_profile"),
        "config": _normalized_input(inputs, "config"),
        "rest_parameters": _normalize_rest(rest),
    }
    try:
        encoded = jcs_bytes(cast(JSONValue, admitted))
    except CanonicalizationError as error:
        _fail("E_INPUT", f"recipe.noncanonical_number:{error}")
    return ShapedForwardRecipe(
        encoded, sha256(b"Crochet.AI\0" + PROFILE.encode() + b"\0" + encoded).hexdigest()
    )


def inspect_shaped_forward_model(
    projection: PhysicalSemanticProjection,
    material: dict[str, Any],
    recipe: ShapedForwardRecipe,
    *,
    validator: SemanticValidator,
) -> dict[str, JSONValue]:
    if not isinstance(projection, PhysicalSemanticProjection):
        _fail("E_INPUT", "projection.type")
    raw = _validate_recipe(recipe)
    try:
        inputs = admit_forward_inputs(
            _mapping(raw["loading"], "loading"),
            _mapping(raw["model_profile"], "model_profile"),
            _mapping(raw["config"], "config"),
        )
        rest = _mapping(raw["rest_parameters"], "rest_parameters")
        cells = build_closed_surface_cells(
            projection,
            max_vertices=inputs.max_initialization_vertices,
            max_faces=_MAX_FACES,
        )
        graph = lower_forward_graph(
            projection,
            material,
            cast(str, raw["tension_profile_id"]),
            cast(str, raw["fabric_state"]),
            validator=validator,
        )
        projected = projection.to_dict()
        if len(graph.edges) > _MAX_TERMS:
            _fail("E_INPUT", "terms.budget_exceeded")
        cell_value = cells.to_dict()
        terms = _terms(graph, inputs, rest)
        coords = _coordinates(projected, graph, rest)
        if set(coords) != set(cell_value["vertices"]):
            _fail("E_INPUT", "initialization.vertex_set_mismatch")
        energy, force_rows, max_force = _evaluate_stretch_terms_at_coordinates(terms, coords)
        payload: dict[str, JSONValue] = {
            "profile": PROFILE,
            "status": "EXPERIMENTAL_INITIAL_ELASTIC_DIAGNOSTIC",
            "projection_sha256": projection.sha256,
            "material_sha256": graph.material_sha256,
            "recipe_sha256": recipe.sha256,
            "surface_cells_sha256": cells.sha256,
            "rest_parameters": rest,
            "coordinates_mm": [
                {"attachment_location_id": key, "position_mm": list(coords[key])}
                for key in sorted(coords)
            ],
            "faces": cell_value["faces"],
            "spring_terms": [_term_dict(term) for term in terms],
            "energy_n_mm": energy,
            "forces_n": [
                {"attachment_location_id": key, "force_n": list(force)} for key, force in force_rows
            ],
            "maximum_force_n": max_force,
            "missing_checks": [
                "closure_mechanics",
                "shear_bending",
                "loading_contact_response",
                "optimization_and_v6",
                "physical_calibration",
            ],
            "comparison_eligible": False,
            "verification_state": "NOT_VERIFIED",
            "physical_status": "UNTESTED",
        }
        encoded = jcs_bytes(payload)
        digest = sha256(b"Crochet.AI\0" + PROFILE.encode() + b"\0" + encoded).hexdigest()
        payload["sha256"] = digest
        return payload
    except ForwardShapedError:
        raise
    except ClosedCellsError as error:
        code = "E_INPUT" if "budget_exceeded" in str(error) else "E_UNSUPPORTED_FEATURE"
        _fail(code, str(error))
    except ForwardForceError as error:
        _fail("E_FORWARD_DIVERGED", str(error))
    except (ForwardGraphError, ForwardInputError) as error:
        _fail("E_INPUT", str(error))
    except (OverflowError, CanonicalizationError) as error:
        _fail("E_FORWARD_DIVERGED", f"numeric.invalid:{type(error).__name__}")


def _validate_recipe(recipe: object) -> dict[str, Any]:
    if not isinstance(recipe, ShapedForwardRecipe):
        _fail("E_INPUT", "recipe.type")
    try:
        raw = parse_json(recipe.canonical_bytes)
        if not isinstance(raw, dict):
            raise ValueError("recipe.payload")
        checked = admit_shaped_forward_recipe(raw)
        if checked != recipe:
            raise ValueError("recipe.binding_mismatch")
        return raw
    except (TypeError, ValueError) as error:
        _fail("E_INPUT", f"recipe.binding_mismatch:{error}")


def _coordinates(
    projected: dict[str, Any], graph: ForwardGraph, rest: dict[str, Any]
) -> dict[str, tuple[float, float, float]]:
    locations = {
        row["attachment_location_id"]: row["location_type"]
        for row in projected["attachment_locations"]
    }
    operations = {row["operation_type"]: row for row in projected["construction_operations"]}
    coords: dict[str, tuple[float, float, float]] = {}
    anchors = operations["MAGIC_RING"]["attachment_location_ids"]
    chord = _positive(rest["ring_initial_chord_mm"], "ring chord")
    ring_radius = chord / (2.0 * math.sin(math.pi / len(anchors)))
    offset = _positive(rest["ring_initial_offset_mm"], "ring offset")
    for index, location in enumerate(anchors):
        angle = 2.0 * math.pi * index / len(anchors)
        coords[location] = (ring_radius * math.cos(angle), ring_radius * math.sin(angle), -offset)
    z = 0.0
    stitches = {row["stitch_id"]: row for row in projected["stitches"]}
    events = {row["event_id"]: row for row in projected["construction_sequence"]}
    course_map = {row["course_id"]: row for row in projected["courses"]}
    for course_id in projected["course_order"]:
        course = course_map[course_id]
        top_ids: list[str] = []
        response_by_stitch = {row.stitch_id: row for row in graph.material_responses}
        course_pitches: list[float] = []
        stitch_pitches: list[float] = []
        for event_id in course["member_event_ids"]:
            event = events[event_id]
            if event["subject_ref"]["entity_type"] != "STITCH":
                _fail("E_UNSUPPORTED_FEATURE", "initialization.non_stitch_course_event")
            stitch = stitches[event["subject_ref"]["stitch_id"]]
            top_ids.extend(stitch["top_attachment_location_ids"])
            response = response_by_stitch[stitch["stitch_id"]]
            course_pitches.append(response.effective_course_pitch_mm)
            stitch_pitches.append(response.effective_stitch_pitch_mm)
        if any(value != course_pitches[0] for value in course_pitches[1:]) or any(
            value != stitch_pitches[0] for value in stitch_pitches[1:]
        ):
            _fail("E_UNSUPPORTED_FEATURE", "initialization.nonuniform_course_response")
        chord = stitch_pitches[0]
        if course_id != projected["course_order"][0]:
            z += course_pitches[0]
        radius = chord / (2.0 * math.sin(math.pi / len(top_ids)))
        for index, location in enumerate(top_ids):
            angle = 2.0 * math.pi * index / len(top_ids)
            coords[location] = (radius * math.cos(angle), radius * math.sin(angle), z)
    if set(coords) != set(locations) or any(
        not all(math.isfinite(x) for x in point) for point in coords.values()
    ):
        _fail("E_FORWARD_DIVERGED", "initialization.invalid_coordinates")
    return coords


def _terms(
    graph: ForwardGraph,
    inputs: ForwardInputs,
    rest: dict[str, Any],
) -> tuple[StretchTerm, ...]:
    params = rest
    factors = params["wale_rest_length_factors"]
    stiffness_factors = params["wale_stiffness_factors"]
    group_by_id = {group.stitch_id: group for group in graph.shaping_groups}
    response_by_id = {response.stitch_id: response for response in graph.material_responses}
    node_type_by_id = {node.attachment_location_id: node.location_type for node in graph.nodes}
    top_owner: dict[str, str] = {}
    if (
        len(group_by_id) != len(graph.shaping_groups)
        or len(response_by_id) != len(graph.material_responses)
        or len(node_type_by_id) != len(graph.nodes)
    ):
        _fail("E_INPUT", "terms.ambiguous_graph_label")
    if set(group_by_id) != set(response_by_id):
        _fail("E_INPUT", "terms.material_response_coverage")
    for group in graph.shaping_groups:
        for top in group.top_attachment_location_ids:
            if top in top_owner or node_type_by_id.get(top) != "TOP_LOOP":
                _fail("E_INPUT", "terms.ambiguous_top_owner")
            top_owner[top] = group.stitch_id
    terms: list[StretchTerm] = []
    for edge in graph.edges:
        if edge.edge_type == "COURSE":
            owner_id = top_owner.get(edge.source_location_id)
            owner = response_by_id.get(owner_id or "")
            if owner is None or node_type_by_id.get(edge.target_location_id) != "TOP_LOOP":
                _fail("E_INPUT", "terms.course_owner_missing")
            terms.append(
                StretchTerm(
                    "COURSE",
                    edge.source_location_id,
                    edge.target_location_id,
                    owner.effective_stitch_pitch_mm,
                    inputs.stiffness_course_n_per_mm,
                    owner.response_id,
                )
            )
        else:
            if edge.edge_type != "WALE":
                _fail("E_UNSUPPORTED_FEATURE", "terms.unsupported_edge_type")
            wale_group = group_by_id.get(edge.stitch_id or "")
            if wale_group is None:
                _fail("E_INPUT", "terms.wale_owner_missing")
            shape = wale_group.shaping
            if shape not in factors:
                _fail("E_UNSUPPORTED_FEATURE", "terms.unsupported_shaping")
            source_type = node_type_by_id.get(edge.source_location_id)
            target_type = node_type_by_id.get(edge.target_location_id)
            if source_type not in {"MAGIC_RING_ANCHOR", "TOP_LOOP"} or target_type != "TOP_LOOP":
                _fail("E_INPUT", "terms.unsupported_wale_endpoint")
            if (
                edge.source_location_id not in wale_group.base_attachment_location_ids
                or edge.target_location_id not in wale_group.top_attachment_location_ids
            ):
                _fail("E_INPUT", "terms.wale_owner_mismatch")
            ring = source_type == "MAGIC_RING_ANCHOR"
            response = response_by_id.get(wale_group.stitch_id)
            if response is None:
                _fail("E_INPUT", "terms.material_response_missing")
            length = (
                params["ring_rest_length_mm"]
                if ring
                else response.effective_course_pitch_mm * factors[shape]
            )
            stiffness = (
                params["ring_stiffness_n_per_mm"]
                if ring
                else inputs.stiffness_wale_n_per_mm * stiffness_factors[shape]
            )
            terms.append(
                StretchTerm(
                    "WALE",
                    edge.source_location_id,
                    edge.target_location_id,
                    length,
                    stiffness,
                    "ring-hypothesis" if ring else response.response_id,
                )
            )
    terms.sort(
        key=lambda item: (
            item.edge_type,
            item.source_location_id,
            item.target_location_id,
            item.response_id,
        )
    )
    return tuple(terms)


def _term_dict(term: StretchTerm) -> dict[str, JSONValue]:
    return {
        "edge_type": term.edge_type,
        "source_location_id": term.source_location_id,
        "target_location_id": term.target_location_id,
        "rest_length_mm": term.rest_length_mm,
        "stiffness_n_per_mm": term.stiffness_n_per_mm,
        "response_id": term.response_id,
    }


def _normalize_rest(rest: dict[str, Any]) -> dict[str, JSONValue]:
    return {
        "schema_version": "1.0.0",
        "status": "HYPOTHESIS",
        "provenance_id": rest["provenance_id"],
        "wale_rest_length_factors": {
            k: _positive(rest["wale_rest_length_factors"][k], k) for k in _SHAPES
        },
        "wale_stiffness_factors": {
            k: _positive(rest["wale_stiffness_factors"][k], k) for k in _SHAPES
        },
        **{
            k: _positive(rest[k], k)
            for k in (
                "ring_rest_length_mm",
                "ring_stiffness_n_per_mm",
                "ring_initial_chord_mm",
                "ring_initial_offset_mm",
            )
        },
    }


def _normalized_input(inputs: ForwardInputs, key: str) -> JSONValue:
    value = parse_json(inputs.canonical_bytes)
    if not isinstance(value, dict):
        raise ValueError("forward_inputs.payload")
    return value[key]


def _closed(value: object, fields: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(k, str) for k in value):
        _fail("E_INPUT", f"{path}.object_required")
    raw = dict(cast(Mapping[str, Any], value))
    if set(raw) != fields:
        extras = set(raw) - fields
        if any(
            any(token in key.casefold() for token in ("target", "embedding", "coordinate"))
            for key in extras
        ):
            _fail("E_INPUT", "input.prohibited_target_field")
        _fail("E_INPUT", f"{path}.fields")
    return raw


def _mapping(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail("E_INPUT", f"{path}.object_required")
    return dict(cast(Mapping[str, Any], value))


def _identifier(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail("E_INPUT", f"{path}.invalid")
    return value


def _positive(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("E_INPUT", f"{path}.positive_number_required")
    if isinstance(value, int) and abs(value) > SAFE_INTEGER:
        _fail("E_INPUT", f"{path}.unsafe_integer")
    try:
        result = float(value)
    except OverflowError:
        _fail("E_INPUT", f"{path}.number_out_of_range")
    if not math.isfinite(result) or result <= 0:
        _fail("E_INPUT", f"{path}.positive_number_required")
    return result


def _fail(code: str, reason: str) -> NoReturn:
    raise ForwardShapedError(code, reason)
