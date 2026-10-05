"""Bounded target-free orchestration for the experimental forward prototype."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import cast

from .canonical import jcs_bytes, parse_json
from .forward_bending import (
    BendingParameters,
    ForwardBendingError,
    admit_bending_parameters,
    prepare_bending_terms,
)
from .forward_cells import ForwardSurfaceCellsError, build_forward_surface_cells
from .forward_final_exact_contact import (
    ForwardFinalExactContactError,
    diagnose_final_exact_self_contact,
)
from .forward_graph import ForwardGraphError, lower_forward_graph
from .forward_initialization import ForwardInitializationError, initialize_forward_graph
from .forward_inputs import (
    PROFILE as INPUTS_PROFILE,
)
from .forward_inputs import (
    ForwardInputError,
    ForwardInputs,
    admit_forward_inputs,
)
from .forward_shear import (
    ForwardShearError,
    ShearBendingOptimizeResult,
    ShearParameters,
    admit_shear_parameters,
    optimize_stretch_shear_bending_prototype,
    prepare_shear_terms,
)
from .forward_stretch import ForwardStretchError, prepare_stretch_terms
from .forward_triangulation import ForwardTriangulationError, triangulate_forward_surface_cells
from .json_types import JSONValue
from .physical_projection import PhysicalSemanticProjection
from .validation import SemanticValidator

PROFILE = "FORWARD_STRETCH_SHEAR_BENDING_PIPELINE_V1"
_LIMITS = {
    "max_initializations": 1,
    "max_initialization_vertices": 128,
    "max_line_search_trials": 32,
    "max_optimizer_iterations": 128,
    "max_energy_evaluations": 4096,
    "max_linear_iterations": 2048,
    "max_contact_pairs_evaluated": 32640,
}
class ForwardPipelineError(ValueError):
    """Classified failure at a forward execution boundary."""

    def __init__(self, code: str, reason: str) -> None:
        self.code = code
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class ForwardPipelineRecipe:
    tension_profile_id: str
    fabric_state: str
    inputs: ForwardInputs
    shear: ShearParameters
    bending: BendingParameters


def admit_forward_pipeline_recipe(value: object) -> ForwardPipelineRecipe:
    """Admit the closed client recipe. No physical values are inferred."""
    raw = _closed_object(
        value,
        {
            "profile",
            "tension_profile_id",
            "fabric_state",
            "loading",
            "model_profile",
            "config",
            "shear_parameters",
            "bending_parameters",
        },
        "forward_run",
    )
    if raw["profile"] != PROFILE:
        raise ForwardPipelineError("E_UNSUPPORTED_FEATURE", "forward_run.unsupported_profile")
    tension = _nonempty(raw["tension_profile_id"], "forward_run.tension_profile_id")
    fabric = _nonempty(raw["fabric_state"], "forward_run.fabric_state")
    try:
        inputs = admit_forward_inputs(
            _object(raw["loading"], "forward_run.loading"),
            _object(raw["model_profile"], "forward_run.model_profile"),
            _object(raw["config"], "forward_run.config"),
        )
        _enforce_limits(inputs)
        shear_doc = _closed_object(
            raw["shear_parameters"],
            {"schema_version", "status", "provenance_id", "stiffness_n_mm", "rest_cosine"},
            "forward_run.shear_parameters",
        )
        bending_doc = _closed_object(
            raw["bending_parameters"],
            {"schema_version", "status", "provenance_id", "stiffness_n_mm", "rest_dihedral_rad"},
            "forward_run.bending_parameters",
        )
        shear = _admit_shear(shear_doc)
        bending = _admit_bending(bending_doc)
    except ForwardPipelineError:
        raise
    except (ForwardInputError, ForwardShearError, ForwardBendingError) as error:
        raise ForwardPipelineError("E_INPUT", str(error)) from error
    return ForwardPipelineRecipe(tension, fabric, inputs, shear, bending)


def run_forward_pipeline(
    projection: PhysicalSemanticProjection,
    material: dict[str, object],
    recipe: ForwardPipelineRecipe,
    *,
    validator: SemanticValidator,
) -> dict[str, JSONValue]:
    """Run only from physical semantics, material, admitted recipe and validator."""
    if not isinstance(projection, PhysicalSemanticProjection):
        raise ForwardPipelineError("E_INPUT", "forward_pipeline.projection_type")
    if not isinstance(recipe, ForwardPipelineRecipe):
        raise ForwardPipelineError("E_INPUT", "forward_pipeline.recipe_type")
    _validate_recipe(recipe)
    try:
        graph = lower_forward_graph(
            projection,
            material,
            recipe.tension_profile_id,
            recipe.fabric_state,
            validator=validator,
        )
        cells = build_forward_surface_cells(projection, graph)
        triangulation = triangulate_forward_surface_cells(cells)
        pair_count = len(triangulation.triangles) * (len(triangulation.triangles) - 1) // 2
        if pair_count > recipe.inputs.max_contact_pairs_evaluated:
            raise ForwardPipelineError("E_INPUT", "forward_run.contact_pair_budget_exceeded")
        initialization = initialize_forward_graph(projection, graph, recipe.inputs)
        stretch = prepare_stretch_terms(graph, recipe.inputs)
        shear = prepare_shear_terms(cells, recipe.shear, recipe.inputs)
        bending = prepare_bending_terms(cells, initialization, recipe.bending, recipe.inputs)
        optimized = optimize_stretch_shear_bending_prototype(
            stretch, shear, bending, initialization, recipe.inputs
        )
        optimization_value = cast(dict[str, JSONValue], parse_json(optimized.canonical_bytes))
        contact_value: dict[str, JSONValue] | None = None
        contact_adapter: dict[str, JSONValue] | None = None
        surface_coordinates: tuple[tuple[str, tuple[float, float, float]], ...] | None = None
        if optimized.status == "EXPERIMENTAL_FORCE_BALANCED":
            optimized_coordinates = dict(optimized.coordinates_mm or ())
            initialized_ids = {key for key, _ in initialization.coordinates_mm}
            surface_ids = {
                location_id for cell in cells.cells for location_id in cell.attachment_location_ids
            }
            if not set(optimized_coordinates).issubset(initialized_ids):
                raise ForwardPipelineError(
                    "E_INPUT", "forward_pipeline.optimizer_coordinate_domain"
                )
            if not surface_ids.issubset(optimized_coordinates):
                raise ForwardPipelineError(
                    "E_INPUT", "forward_pipeline.optimizer_surface_coordinates_missing"
                )
            surface_coordinates = tuple(
                (key, optimized_coordinates[key]) for key in sorted(surface_ids)
            )
            contact_optimization = _with_surface_coordinates(optimized, dict(surface_coordinates))
            contact = diagnose_final_exact_self_contact(
                cells, triangulation, contact_optimization, recipe.inputs
            )
            contact_value = cast(dict[str, JSONValue], parse_json(contact.canonical_bytes))
            contact_adapter = {
                "profile": "FORWARD_SURFACE_COORDINATE_RESTRICTION_V1",
                "optimizer_sha256": optimized.sha256,
                "contact_optimizer_sha256": contact_optimization.sha256,
                "retained_location_ids": cast(JSONValue, sorted(surface_ids)),
                "excluded_location_ids": cast(
                    JSONValue, sorted(set(optimized_coordinates) - surface_ids)
                ),
            }
        forbidden = bool(contact_value and contact_value["forbidden_pair_count"] != 0)
        status = "FORBIDDEN_FINAL_INTERSECTION" if forbidden else optimized.status
        coordinates: JSONValue = None
        triangles: JSONValue = None
        if (
            status == "EXPERIMENTAL_FORCE_BALANCED"
            and contact_value is not None
            and surface_coordinates is not None
        ):
            coordinates = [
                {"attachment_location_id": key, "xyz_mm": list(point)}
                for key, point in surface_coordinates
            ]
            triangles = [
                {
                    "face_index": face_index,
                    "triangle_index": row.triangle_index,
                    "attachment_location_ids": list(row.attachment_location_ids),
                }
                for face_index, row in enumerate(triangulation.triangles)
            ]
        if forbidden:
            optimization_value["coordinates_mm"] = None
        payload: dict[str, JSONValue] = {
            "profile": PROFILE,
            "schema_version": "1.0.0",
            "status": status,
            "unit": "mm",
            "geometry_role": "EXPERIMENTAL_DEBUG_ONLY",
            "physical_input_sha256": projection.sha256,
            "material_sha256": graph.material_sha256,
            "tension_profile_id": recipe.tension_profile_id,
            "fabric_state": recipe.fabric_state,
            "forward_inputs_sha256": recipe.inputs.sha256,
            "stretch_terms_sha256": optimized.stretch_terms_sha256,
            "shear_terms_sha256": shear.sha256,
            "bending_terms_sha256": bending.sha256,
            "optimizer_sha256": optimized.sha256,
            "cells_sha256": cells.sha256,
            "triangulation_sha256": triangulation.sha256,
            "initialization_sha256": initialization.sha256,
            "optimizer": optimization_value,
            "final_contact": contact_value,
            "final_contact_adapter": contact_adapter,
            "coordinates_mm": coordinates,
            "triangles": triangles,
            "lower_boundary_location_ids": (
                list(cells.lower_boundary_location_ids) if coordinates is not None else None
            ),
            "upper_boundary_location_ids": (
                list(cells.upper_boundary_location_ids) if coordinates is not None else None
            ),
            "limitations": [
                "experimental_target_free_open_strip_only",
                "does_not_establish_v6_convergence_or_verified_geometry",
                "exact_contact_diagnostic_does_not_establish_clearance_or_contact_response",
            ],
        }
        encoded = jcs_bytes(payload)
        payload["canonical_bytes_object"] = cast(dict[str, JSONValue], parse_json(encoded))
        payload["sha256"] = sha256(
            b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + encoded
        ).hexdigest()
        return payload
    except ForwardPipelineError:
        raise
    except ForwardSurfaceCellsError as error:
        raise ForwardPipelineError("E_UNSUPPORTED_FEATURE", str(error)) from error
    except ForwardInitializationError as error:
        code = "E_UNSUPPORTED_FEATURE" if "unsupported" in error.reason else "E_INPUT"
        raise ForwardPipelineError(code, str(error)) from error
    except (
        ForwardGraphError,
        ForwardTriangulationError,
        ForwardStretchError,
        ForwardShearError,
        ForwardBendingError,
        ForwardFinalExactContactError,
    ) as error:
        raise ForwardPipelineError("E_INPUT", str(error)) from error


def _parameter_fields(raw: dict[str, object]) -> tuple[str, float]:
    if raw.get("schema_version") != "1.0.0":
        raise ForwardPipelineError("E_INPUT", "forward_run.parameter_schema_version")
    if raw.get("status") != "HYPOTHESIS":
        raise ForwardPipelineError("E_INPUT", "forward_run.parameter_status")
    provenance = _nonempty(raw.get("provenance_id"), "forward_run.parameter_provenance_id")
    stiffness = _number(raw.get("stiffness_n_mm"), "forward_run.stiffness_n_mm")
    return provenance, stiffness


def _admit_shear(raw: dict[str, object]) -> ShearParameters:
    provenance, stiffness = _parameter_fields(raw)
    cosine = _number(raw.get("rest_cosine"), "forward_run.rest_cosine")
    return admit_shear_parameters(provenance, stiffness, cosine)


def _admit_bending(raw: dict[str, object]) -> BendingParameters:
    provenance, stiffness = _parameter_fields(raw)
    angle = _number(raw.get("rest_dihedral_rad"), "forward_run.rest_dihedral_rad")
    return admit_bending_parameters(provenance, angle, stiffness)


def _enforce_limits(inputs: ForwardInputs) -> None:
    for name, maximum in _LIMITS.items():
        value = getattr(inputs, name)
        if type(value) is not int or value < 1:
            raise ForwardPipelineError("E_INPUT", f"forward_run.{name}_invalid")
        if value > maximum:
            raise ForwardPipelineError("E_INPUT", f"forward_run.{name}_exceeds_server_limit")


def _validate_recipe(recipe: ForwardPipelineRecipe) -> None:
    if not isinstance(recipe.inputs, ForwardInputs):
        raise ForwardPipelineError("E_INPUT", "forward_pipeline.inputs_type")
    if not isinstance(recipe.shear, ShearParameters) or not isinstance(
        recipe.bending, BendingParameters
    ):
        raise ForwardPipelineError("E_INPUT", "forward_pipeline.parameter_type")
    _nonempty(recipe.tension_profile_id, "forward_run.tension_profile_id")
    _nonempty(recipe.fabric_state, "forward_run.fabric_state")
    _enforce_limits(recipe.inputs)
    try:
        admitted_inputs = cast(dict[str, object], parse_json(recipe.inputs.canonical_bytes))
        if set(admitted_inputs) != {"profile", "loading", "model_profile", "config"}:
            raise ValueError("forward_inputs.fields")
        if admitted_inputs["profile"] != INPUTS_PROFILE:
            raise ValueError("forward_inputs.profile")
        checked_inputs = admit_forward_inputs(
            _object(admitted_inputs["loading"], "forward_inputs.loading"),
            _object(admitted_inputs["model_profile"], "forward_inputs.model_profile"),
            _object(admitted_inputs["config"], "forward_inputs.config"),
        )
        if checked_inputs != recipe.inputs:
            raise ValueError("forward_inputs.binding_mismatch")
        checked_shear = admit_shear_parameters(
            recipe.shear.provenance_id, recipe.shear.stiffness_n_mm, recipe.shear.rest_cosine
        )
        checked_bending = admit_bending_parameters(
            recipe.bending.provenance_id,
            recipe.bending.rest_dihedral_rad,
            recipe.bending.stiffness_n_mm,
        )
        if checked_shear != recipe.shear or checked_bending != recipe.bending:
            raise ValueError("forward_parameters.binding_mismatch")
    except (
        ForwardInputError,
        ForwardShearError,
        ForwardBendingError,
        TypeError,
        ValueError,
    ) as error:
        raise ForwardPipelineError("E_INPUT", "forward_pipeline.recipe_binding_mismatch") from error


def _with_surface_coordinates(
    optimized: ShearBendingOptimizeResult,
    coordinates: dict[str, tuple[float, float, float]],
) -> ShearBendingOptimizeResult:
    payload = cast(dict[str, JSONValue], parse_json(optimized.canonical_bytes))
    payload["coordinates_mm"] = [
        {"attachment_location_id": key, "xyz_mm": list(point)}
        for key, point in sorted(coordinates.items())
    ]
    encoded = jcs_bytes(payload)
    digest = sha256(
        b"Crochet.AI\0FORWARD_STRETCH_SHEAR_BENDING_OPTIMIZATION_V1\0" + encoded
    ).hexdigest()
    return replace(
        optimized,
        coordinates_mm=tuple(sorted(coordinates.items())),
        canonical_bytes=encoded,
        sha256=digest,
    )


def _closed_object(value: object, keys: set[str], name: str) -> dict[str, object]:
    raw = _object(value, name)
    if set(raw) != keys:
        raise ForwardPipelineError("E_INPUT", f"{name}.fields")
    return raw


def _object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ForwardPipelineError("E_INPUT", f"{name}.object_required")
    return dict(value.items())


def _nonempty(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ForwardPipelineError("E_INPUT", f"{name}.invalid")
    return value


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ForwardPipelineError("E_INPUT", f"{name}.number_required")
    try:
        converted = float(value)
    except OverflowError as error:
        raise ForwardPipelineError("E_INPUT", f"{name}.number_out_of_range") from error
    if not math.isfinite(converted):
        raise ForwardPipelineError("E_INPUT", f"{name}.number_out_of_range")
    return converted
