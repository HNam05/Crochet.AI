"""Versioned, transport-independent JSON boundary; no network or filesystem input."""

from __future__ import annotations

import re
from dataclasses import fields
from fractions import Fraction
from typing import Any

import rfc8785

from .analytic_compile import CompileProvenance
from .analytic_counts import CountSearchBudget
from .analytic_geometry import MeridianNumerics
from .analytic_placement import PlacementBudget
from .analytic_solver import AnalyticRunConfig, generate_analytic
from .canonical import (
    CanonicalizationError,
    CanonicalProfile,
    canonical_hash,
    parse_json,
    validate_ijson,
)
from .diagnostics import ArtifactValidationError
from .pattern import TerminologyProfile, export_pattern
from .schema import validate_schema
from .solver_types import GenerationError
from .validation import SemanticValidator

API_VERSION = "1.0.0"
MAX_REQUEST_BYTES = 2_000_000
MAX_JSON_NODES = 100_000
MAX_JSON_DEPTH = 64


class ApiInputError(ValueError):
    pass


def _object(value: object, keys: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ApiInputError(f"{name}.fields")
    return value


def _config(value: object) -> AnalyticRunConfig:
    data = dict(_object(value, {f.name for f in fields(AnalyticRunConfig)}, "run_config"))
    data["numerics"] = MeridianNumerics(
        **_object(data["numerics"], {f.name for f in fields(MeridianNumerics)}, "numerics")
    )
    data["count_budget"] = CountSearchBudget(
        **_object(data["count_budget"], {f.name for f in fields(CountSearchBudget)}, "count_budget")
    )
    data["placement_budget"] = PlacementBudget(
        **_object(
            data["placement_budget"], {f.name for f in fields(PlacementBudget)}, "placement_budget"
        )
    )
    separation = data["minimum_shaping_separation_turns"]
    if (
        not isinstance(separation, str)
        or re.fullmatch(r"[0-9]{1,39}/[1-9][0-9]{0,38}", separation) is None
    ):
        raise ApiInputError("run_config.minimum_shaping_separation_turns")
    data["minimum_shaping_separation_turns"] = Fraction(separation)
    for name in ("parameter_profile_id", "tension_profile_id", "fabric_state"):
        if not isinstance(data[name], str):
            raise ApiInputError(f"run_config.{name}")
    result = AnalyticRunConfig(**data)
    result.validate()
    return result


def bounded_json(text: str | bytes) -> dict[str, Any]:
    if len(text) > MAX_REQUEST_BYTES:
        raise ApiInputError("request.size")
    try:
        value = parse_json(text)
    except (CanonicalizationError, RecursionError, ValueError) as error:
        raise ApiInputError("request.invalid_json") from error
    if not isinstance(value, dict):
        raise ApiInputError("request.object_required")
    pending: list[tuple[object, int]] = [(value, 0)]
    visited = 0
    while pending:
        node, depth = pending.pop()
        visited += 1
        if depth > MAX_JSON_DEPTH or visited > MAX_JSON_NODES:
            raise ApiInputError("request.complexity")
        if isinstance(node, dict):
            pending.extend((v, depth + 1) for v in node.values())
        elif isinstance(node, list):
            pending.extend((v, depth + 1) for v in node)
    if len(rfc8785.dumps(value)) > MAX_REQUEST_BYTES:
        raise ApiInputError("request.size")
    return value


def error_response(code: str, reason: str) -> dict[str, Any]:
    return {"api_version": API_VERSION, "ok": False, "error": {"code": code, "reason": reason}}


class BackendAPI:
    """Local single-user service facade; provenance is server-owned, never client supplied."""

    def __init__(self, provenance: CompileProvenance) -> None:
        self.provenance = provenance

    def handle_json(self, request: str | bytes) -> dict[str, Any]:
        try:
            return self.handle(bounded_json(request))
        except ApiInputError as error:
            return error_response("E_INPUT", str(error))

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        try:
            # Apply the same bounded boundary to in-process clients as wire clients.
            validate_ijson(request)
            request = bounded_json(rfc8785.dumps(request))
            operation = request.get("operation")
            if not isinstance(operation, str):
                raise ApiInputError("request.operation")
            if request.get("api_version") != API_VERSION:
                raise ApiInputError("request.api_version")
            if operation == "capabilities":
                _object(request, {"api_version", "operation"}, "request")
                data: dict[str, Any] = {
                    "operations": ["capabilities", "generate_analytic", "validate_ir", "export_ir"],
                    "candidate_domains": ["CLOSED_POLE_SINGLE_COLOR_SC_ANALYTIC"],
                    "physical_verification_available": False,
                    "deployment_scope": "LOCAL_SINGLE_USER",
                }
            elif operation in {"generate_analytic", "validate_ir", "export_ir"}:
                keys = {"api_version", "operation", "design_spec", "material_profile"}
                keys |= {"run_config"} if operation == "generate_analytic" else {"crochet_ir"}
                if operation == "export_ir":
                    keys.add("terminology")
                _object(request, keys, "request")
                design, material = request["design_spec"], request["material_profile"]
                if not isinstance(design, dict) or not isinstance(material, dict):
                    raise ApiInputError("request.artifacts")
                for kind, artifact in (("design_spec", design), ("material_profile", material)):
                    report = validate_schema(kind, artifact)
                    if not report.ok:
                        raise ArtifactValidationError(report)
                validator = SemanticValidator(
                    material_profiles={material.get("profile_id", ""): material},
                    design_specs={design.get("design_spec_id", ""): design},
                )
                if operation == "generate_analytic":
                    batch = generate_analytic(
                        design, material, _config(request["run_config"]), self.provenance
                    )
                    data = {
                        "generation_status": batch.status.value,
                        "reason": batch.reason,
                        "verification_state": "NOT_VERIFIED",
                        "physical_status": "UNTESTED",
                        "completed_course_hypotheses": batch.completed_course_hypotheses,
                        "work": {
                            "count_transitions": batch.count_transition_evaluations,
                            "placement_transitions": batch.placement_transition_evaluations,
                            "placement_pairs": batch.placement_pair_evaluations,
                        },
                        "candidates": [],
                    }
                    for candidate in batch.candidates:
                        value = candidate.crochet_ir.to_dict()
                        data["candidates"].append(
                            {
                                "crochet_ir": value,
                                "sha256": canonical_hash(
                                    value, CanonicalProfile.CROCHET_IR, validator=validator
                                ),
                                "verification_state": "NOT_VERIFIED",
                                "material_response_id": candidate.material_response_id,
                                "course_spacing_residual_mm": candidate.course_spacing_residual_mm,
                            }
                        )
                else:
                    value = request["crochet_ir"]
                    if not isinstance(value, dict):
                        raise ApiInputError("request.crochet_ir")
                    report = validator.validate_crochet_ir(value)
                    if not report.ok:
                        raise ArtifactValidationError(report)
                    data = {
                        "semantic_validation": "PASS",
                        "verification_state": "NOT_VERIFIED",
                        "sha256": canonical_hash(
                            value, CanonicalProfile.CROCHET_IR, validator=validator
                        ),
                    }
                    if operation == "export_ir":
                        try:
                            terminology = TerminologyProfile(request["terminology"])
                        except (ValueError, TypeError) as error:
                            raise ApiInputError("request.terminology") from error
                        data["pattern"] = export_pattern(value, terminology, validator=validator)
            else:
                raise ApiInputError("request.operation")
            return {"api_version": API_VERSION, "ok": True, "data": data}
        except ArtifactValidationError as error:
            return {
                "api_version": API_VERSION,
                "ok": False,
                "error": {
                    "code": error.report.diagnostics[0].code.value
                    if error.report.diagnostics
                    else "E_INTERNAL",
                    "reason": "artifact.invalid",
                    "diagnostics": [
                        {
                            "code": d.code.value,
                            "gate": d.gate,
                            "message_key": d.message_key,
                            "diagnostic_id": d.diagnostic_id,
                            "artifact_hash": d.artifact_hash,
                            "entity_refs": list(d.entity_refs),
                            "json_pointers": list(d.json_pointers),
                        }
                        for d in error.report.diagnostics
                    ],
                },
            }
        except GenerationError as error:
            return error_response("E_INPUT", error.reason)
        except (
            ApiInputError,
            CanonicalizationError,
            rfc8785.CanonicalizationError,
            RecursionError,
        ) as error:
            return error_response("E_INPUT", str(error))
