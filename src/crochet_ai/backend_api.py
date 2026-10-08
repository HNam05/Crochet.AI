"""Versioned, transport-independent JSON boundary; no network or filesystem input."""

from __future__ import annotations

import re
from dataclasses import asdict, fields
from fractions import Fraction
from typing import Any

import rfc8785

from .analytic_claims import AnalyticClaimsInputError, inspect_analytic_candidate_claims
from .analytic_compile import CompileProvenance
from .analytic_counts import CountSearchBudget
from .analytic_geometry import MeridianNumerics
from .analytic_placement import PlacementBudget
from .analytic_solver import AnalyticRunConfig, generate_analytic
from .analytic_target import AnalyticTargetError, admit_analytic_target
from .analytic_trace_audit import inspect_analytic_search_trace
from .backend_capabilities import backend_capability_matrix
from .calibration_campaign import (
    CalibrationCampaign,
    CalibrationError,
    CalibrationMeasurement,
    calibration_protocol,
    derive_draft_material,
)
from .canonical import (
    CanonicalizationError,
    CanonicalProfile,
    canonical_hash,
    parse_json,
    validate_ijson,
)
from .cell_conformance import CellConformanceInputError, inspect_closed_cell_conformance
from .diagnostics import ArtifactValidationError
from .forward_closed_cells import ClosedCellsError, build_closed_surface_cells
from .forward_closed_mechanics import (
    ForwardClosedMechanicsError,
    admit_closed_mechanics_recipe,
    run_closed_mechanics,
)
from .forward_pipeline import (
    ForwardPipelineError,
    admit_forward_pipeline_recipe,
    run_forward_pipeline,
)
from .forward_shaped import (
    ForwardShapedError,
    admit_shaped_forward_recipe,
    inspect_shaped_forward_model,
)
from .models import DesignSpec, MaterialProfile
from .pattern import TerminologyProfile, export_pattern
from .physical_projection import PhysicalProjectionError, PhysicalSemanticProjection
from .prototype_final_relation import PrototypeRelationInputError, inspect_prototype_final_relation
from .schema import validate_schema
from .solver_types import GenerationError
from .surface_topology import SurfaceTopologyInputError, audit_surface_topology
from .target_mesh_openings import (
    TargetMeshOpeningDiagnostic,
    TargetMeshOpeningError,
    diagnose_target_mesh_openings,
)
from .trace_verification_types import TraceAuditInputError
from .v0_mesh_preflight import (
    V0MeshBudgets,
    V0MeshPreflightError,
    V0MeshResult,
    inspect_v0_closed_mesh_v2,
    inspect_v0_mesh_v2,
)
from .validation import SemanticValidator
from .verification_pipeline import (
    BACKEND_SEMANTIC_CHECKPOINT_V1,
    verify_artifacts,
)

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
                    "operations": [
                        "capabilities",
                        "generate_analytic",
                        "validate_ir",
                        "export_ir",
                        "inspect_mesh_openings",
                        "inspect_v0_closed_mesh_v2",
                        "inspect_v0_mesh_v2",
                        "run_forward_prototype",
                        "inspect_shaped_forward_model",
                        "run_closed_forward_prototype",
                        "verify_candidate",
                        "inspect_analytic_search_trace",
                        "calibration_protocol",
                        "inspect_calibration_campaign",
                        "derive_calibration_material",
                        "inspect_analytic_target",
                        "inspect_closed_surface_cells",
                        "inspect_closed_surface_topology",
                        "inspect_closed_cell_conformance",
                        "inspect_analytic_candidate_claims",
                        "inspect_prototype_final_relation",
                    ],
                    "candidate_domains": ["CLOSED_POLE_SINGLE_COLOR_SC_ANALYTIC"],
                    "physical_verification_available": False,
                    "deployment_scope": "LOCAL_SINGLE_USER",
                    "verification_profiles": [
                        {
                            "profile_id": BACKEND_SEMANTIC_CHECKPOINT_V1.profile_id,
                            "version": BACKEND_SEMANTIC_CHECKPOINT_V1.version,
                            "sha256": BACKEND_SEMANTIC_CHECKPOINT_V1.content_hash,
                            "calibrated": False,
                            "required_gates": list(BACKEND_SEMANTIC_CHECKPOINT_V1.required_gates),
                        }
                    ],
                    "capability_matrix": backend_capability_matrix(),
                }
            elif operation == "inspect_analytic_candidate_claims":
                _object(
                    request,
                    {"api_version", "operation", "design_spec", "material_profile", "crochet_ir"},
                    "request",
                )
                for key in ("design_spec", "material_profile", "crochet_ir"):
                    if not isinstance(request[key], dict):
                        raise ApiInputError(f"request.{key}")
                claims_design = request["design_spec"]
                claims_material = request["material_profile"]
                DesignSpec.from_dict(claims_design)
                MaterialProfile.from_dict(claims_material)
                claims_validator = SemanticValidator(
                    design_specs={claims_design.get("design_spec_id", ""): claims_design},
                    material_profiles={claims_material.get("profile_id", ""): claims_material},
                )
                claims = inspect_analytic_candidate_claims(
                    claims_design, claims_material, request["crochet_ir"],
                    validator=claims_validator,
                )
                data = {
                    "candidate_claims": claims.to_dict(), "candidate_claims_sha256": claims.sha256,
                    "verification_state": "REJECTED" if claims.status == "FAIL" else "NOT_VERIFIED",
                    "physical_status": "UNTESTED",
                }
            elif operation == "inspect_prototype_final_relation":
                _object(
                    request,
                    {
                        "api_version",
                        "operation",
                        "design_spec",
                        "material_profile",
                        "original_proposal",
                        "crochet_ir",
                    },
                    "request",
                )
                for key in ("design_spec", "material_profile", "original_proposal", "crochet_ir"):
                    if not isinstance(request[key], dict):
                        raise ApiInputError(f"request.{key}")
                relation_design = request["design_spec"]
                relation_material = request["material_profile"]
                DesignSpec.from_dict(relation_design)
                MaterialProfile.from_dict(relation_material)
                relation_validator = SemanticValidator(
                    design_specs={relation_design.get("design_spec_id", ""): relation_design},
                    material_profiles={relation_material.get("profile_id", ""): relation_material},
                )
                relation = inspect_prototype_final_relation(
                    relation_design,
                    relation_material,
                    request["original_proposal"],
                    request["crochet_ir"],
                    validator=relation_validator,
                )
                relation_report = relation.to_dict()
                data = {
                    "final_relation": relation_report,
                    "final_relation_sha256": relation.sha256,
                    "verification_state": "REJECTED"
                    if relation.status == "FAIL"
                    else "NOT_VERIFIED",
                    "physical_status": "UNTESTED",
                }
            elif operation == "inspect_analytic_target":
                _object(
                    request,
                    {"api_version", "operation", "design_spec", "material_profile"},
                    "request",
                )
                if not isinstance(request["design_spec"], dict) or not isinstance(
                    request["material_profile"], dict
                ):
                    raise ApiInputError("request.artifact_objects_required")
                target_material = MaterialProfile.from_dict(request["material_profile"]).to_dict()
                target_material_id = target_material["profile_id"]
                if not isinstance(target_material_id, str):
                    raise ApiInputError("target.material_profile_id")
                validator = SemanticValidator(
                    material_profiles={target_material_id: target_material}
                )
                design = request["design_spec"]
                target = admit_analytic_target(design, validator)
                binding = design["material_profile"]
                binding_hash = (
                    canonical_hash(binding["profile"], CanonicalProfile.MATERIAL_PROFILE)
                    if binding["binding_type"] == "INLINE"
                    else binding["sha256"]
                )
                if (
                    canonical_hash(target_material, CanonicalProfile.MATERIAL_PROFILE)
                    != binding_hash
                ):
                    raise ApiInputError("target.material_binding")
                data = {
                    "target": target.to_dict(),
                    "verification_state": "NOT_VERIFIED",
                    "physical_status": "UNTESTED",
                }
            elif operation in (
                "inspect_closed_surface_cells", "inspect_closed_surface_topology",
                "inspect_closed_cell_conformance",
            ):
                _object(
                    request,
                    {"api_version", "operation", "design_spec", "material_profile", "crochet_ir"},
                    "request",
                )
                for key in ("design_spec", "material_profile", "crochet_ir"):
                    if not isinstance(request[key], dict):
                        raise ApiInputError(f"request.{key}")
                cells_design = request["design_spec"]
                cells_material = request["material_profile"]
                DesignSpec.from_dict(cells_design)
                MaterialProfile.from_dict(cells_material)
                cells_validator = SemanticValidator(
                    design_specs={cells_design["design_spec_id"]: cells_design},
                    material_profiles={cells_material["profile_id"]: cells_material},
                )
                for report in (
                    cells_validator.validate_design_spec(cells_design),
                    cells_validator.validate_material_profile(cells_material),
                ):
                    if not report.ok:
                        raise ArtifactValidationError(report)
                cells_projection = PhysicalSemanticProjection(
                    request["crochet_ir"], cells_material, validator=cells_validator
                )
                cells = build_closed_surface_cells(cells_projection)
                data = {
                    "surface_cells": cells.to_dict(),
                    "surface_cells_sha256": cells.sha256,
                    "verification_state": "NOT_VERIFIED",
                    "physical_status": "UNTESTED",
                }
                if operation != "inspect_closed_surface_cells":
                    surface = data["surface_cells"]
                    audit = audit_surface_topology(surface["vertices"], surface["faces"])
                    data["surface_topology"] = audit.to_dict()
                    data["surface_topology_sha256"] = audit.sha256
                    conformance = inspect_closed_cell_conformance(
                        request["crochet_ir"], surface, validator=cells_validator,
                        projection_sha256=cells_projection.sha256,
                        surface_cells_sha256=cells.sha256,
                    )
                    data["cell_conformance"] = conformance.to_dict()
                    data["cell_conformance_sha256"] = conformance.sha256
                    if audit.status != "PASS" or conformance.status == "FAIL":
                        data["verification_state"] = "REJECTED"
            elif operation == "calibration_protocol":
                _object(request, {"api_version", "operation"}, "request")
                data = calibration_protocol()
            elif operation == "inspect_calibration_campaign":
                _object(request, {"api_version", "operation", "campaign"}, "request")
                campaign = CalibrationCampaign(request["campaign"])
                data = {
                    "campaign": campaign.to_dict(),
                    "campaign_sha256": campaign.sha256,
                    "physical_status": "UNTESTED",
                    "verification_state": "NOT_VERIFIED",
                }
            elif operation == "derive_calibration_material":
                _object(
                    request,
                    {
                        "api_version",
                        "operation",
                        "campaign",
                        "measurements",
                        "profile_id",
                        "response_id",
                        "created_at",
                    },
                    "request",
                )
                campaign = CalibrationCampaign(request["campaign"])
                raw_measurements = request["measurements"]
                if not isinstance(raw_measurements, list) or len(raw_measurements) > 64:
                    raise ApiInputError("request.measurements")
                for key in ("profile_id", "response_id", "created_at"):
                    if not isinstance(request[key], str):
                        raise ApiInputError(f"request.{key}")
                data = derive_draft_material(
                    campaign,
                    [CalibrationMeasurement(value, campaign) for value in raw_measurements],
                    profile_id=request["profile_id"],
                    response_id=request["response_id"],
                    created_at=request["created_at"],
                )
            elif operation == "inspect_analytic_search_trace":
                _object(request, {"api_version", "operation", "design_spec", "material_profile",
                                  "run_config", "search_trace", "candidate_proposals"}, "request")
                for key in ("design_spec", "material_profile"):
                    if not isinstance(request[key], dict):
                        raise ApiInputError("request." + key)
                for key, identity in (("design_spec", "design_spec_id"),
                                      ("material_profile", "profile_id")):
                    if not isinstance(request[key].get(identity), str):
                        raise ApiInputError("request." + key + "." + identity)
                validator = SemanticValidator(
                    design_specs={
                        request["design_spec"].get("design_spec_id", ""): request["design_spec"]
                    },
                    material_profiles={
                        request["material_profile"].get("profile_id", ""):
                        request["material_profile"]
                    },
                )
                data = inspect_analytic_search_trace(
                    request["design_spec"], request["material_profile"], request["run_config"],
                    request["search_trace"], request["candidate_proposals"], validator=validator,
                ).to_dict()
            elif operation == "verify_candidate":
                _object(
                    request,
                    {
                        "api_version",
                        "operation",
                        "design_spec",
                        "material_profile",
                        "crochet_ir",
                        "mesh_json",
                        "diagnostic_mode",
                    } | ({"search_evidence"} if "search_evidence" in request else set()),
                    "request",
                )
                if type(request["diagnostic_mode"]) is not bool:
                    raise ApiInputError("request.diagnostic_mode")
                if request["mesh_json"] is not None and not isinstance(request["mesh_json"], str):
                    raise ApiInputError("request.mesh_json")
                for key in ("design_spec", "material_profile", "crochet_ir"):
                    if not isinstance(request[key], dict):
                        raise ApiInputError(f"request.{key}")
                evidence = None
                if "search_evidence" in request:
                    evidence = _object(
                        request["search_evidence"],
                        {"run_config", "search_trace", "candidate_proposals"}, "search_evidence",
                    )
                raw_mesh = (
                    None if request["mesh_json"] is None else request["mesh_json"].encode("utf-8")
                )
                checkpoint = verify_artifacts(
                    request["design_spec"],
                    request["material_profile"],
                    request["crochet_ir"],
                    mesh_json=raw_mesh,
                    mesh_budgets=V0MeshBudgets(
                        max_bytes=262_144,
                        max_vertices=128,
                        max_faces=256,
                        max_vertex_pairs=8_128,
                        max_face_pairs=32_640,
                        max_distance_piece_pairs=130_560,
                        max_lambda_bits=512,
                        max_orientation_tests=800_000,
                        max_openings=16,
                        max_landmark_refs=64,
                        max_landmarks=32,
                        max_landmark_edge_tests=16_384,
                    )
                    if raw_mesh is not None
                    else None,
                    diagnostic_mode=request["diagnostic_mode"],
                    search_evidence=evidence,
                )
                data = checkpoint.to_dict()
            elif operation in {
                "inspect_mesh_openings",
                "inspect_v0_closed_mesh_v2",
                "inspect_v0_mesh_v2",
            }:
                _object(
                    request,
                    {
                        "api_version",
                        "operation",
                        "design_spec",
                        "material_profile",
                        "mesh_json",
                    },
                    "request",
                )
                if not isinstance(request["mesh_json"], str):
                    raise ApiInputError("request.mesh_json")
                # Bytes, not reserialized JSON, must match the declared source digest.
                raw_mesh = request["mesh_json"].encode("utf-8")
                design_model = DesignSpec.from_dict(request["design_spec"])
                material_model = MaterialProfile.from_dict(request["material_profile"])
                result: TargetMeshOpeningDiagnostic | V0MeshResult
                if operation == "inspect_mesh_openings":
                    result = diagnose_target_mesh_openings(
                        design_model,
                        raw_mesh,
                        material_profile=material_model,
                        max_bytes=262_144,
                        max_vertices=128,
                        max_faces=256,
                        max_openings=16,
                        max_landmark_refs=64,
                        max_landmarks=32,
                        max_vertex_pairs=8_128,
                        max_landmark_edge_tests=16_384,
                    )
                    preflight_state = "INDETERMINATE"
                else:
                    inspector = (
                        inspect_v0_closed_mesh_v2
                        if operation == "inspect_v0_closed_mesh_v2"
                        else inspect_v0_mesh_v2
                    )
                    result = inspector(
                        design_model,
                        raw_mesh,
                        material_profile=material_model,
                        budgets=V0MeshBudgets(
                            max_bytes=262_144,
                            max_vertices=128,
                            max_faces=256,
                            max_vertex_pairs=8_128,
                            max_face_pairs=32_640,
                            max_distance_piece_pairs=130_560,
                            max_lambda_bits=512,
                            max_orientation_tests=800_000,
                            max_openings=16,
                            max_landmark_refs=64,
                            max_landmarks=32,
                            max_landmark_edge_tests=16_384,
                        ),
                    )
                    preflight_state = result.outcome
                data = {
                    "diagnostic": parse_json(rfc8785.dumps(asdict(result))),
                    "verification_state": "NOT_VERIFIED",
                    "mesh_preflight_state": preflight_state,
                    "physical_status": "UNTESTED",
                }
            elif operation in {
                "run_forward_prototype",
                "inspect_shaped_forward_model",
                "run_closed_forward_prototype",
            }:
                _object(
                    request,
                    {
                        "api_version",
                        "operation",
                        "design_spec",
                        "material_profile",
                        "crochet_ir",
                        "forward_run",
                    },
                    "request",
                )
                design, material, value = (
                    request["design_spec"],
                    request["material_profile"],
                    request["crochet_ir"],
                )
                if not isinstance(design, dict) or not isinstance(material, dict):
                    raise ApiInputError("request.artifacts")
                if not isinstance(value, dict):
                    raise ApiInputError("request.crochet_ir")
                for kind, artifact in (("design_spec", design), ("material_profile", material)):
                    report = validate_schema(kind, artifact)
                    if not report.ok:
                        raise ArtifactValidationError(report)
                source_validator = SemanticValidator(
                    material_profiles={material.get("profile_id", ""): material},
                    design_specs={design.get("design_spec_id", ""): design},
                )
                report = source_validator.validate_crochet_ir(value)
                if not report.ok:
                    raise ArtifactValidationError(report)
                source_sha256 = canonical_hash(
                    value, CanonicalProfile.CROCHET_IR, validator=source_validator
                )
                try:
                    projection = PhysicalSemanticProjection(
                        value, material, validator=source_validator
                    )
                except PhysicalProjectionError as error:
                    raise ForwardPipelineError("E_UNSUPPORTED_FEATURE", str(error)) from error
                execution_validator = SemanticValidator(
                    material_profiles={material.get("profile_id", ""): material}
                )
                if operation == "run_forward_prototype":
                    recipe = admit_forward_pipeline_recipe(request["forward_run"])
                    bundle = run_forward_pipeline(
                        projection, material, recipe, validator=execution_validator
                    )
                elif operation == "inspect_shaped_forward_model":
                    shaped_recipe = admit_shaped_forward_recipe(request["forward_run"])
                    bundle = inspect_shaped_forward_model(
                        projection, material, shaped_recipe, validator=execution_validator
                    )
                else:
                    closed_recipe = admit_closed_mechanics_recipe(request["forward_run"])
                    bundle = run_closed_mechanics(
                        projection, material, closed_recipe, validator=execution_validator
                    )
                data = {
                    "source_crochet_ir_sha256": source_sha256,
                    "experimental_forward_bundle": bundle,
                    "verification_state": "NOT_VERIFIED",
                    "physical_status": "UNTESTED",
                    "v6_outcome": "NOT_RUN",
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
                        "search_trace": (
                            batch.search_trace.to_dict() if batch.search_trace is not None else None
                        ),
                        "search_trace_sha256": (
                            batch.search_trace.sha256 if batch.search_trace is not None else None
                        ),
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
        except (
            SurfaceTopologyInputError, CellConformanceInputError, AnalyticClaimsInputError,
            TraceAuditInputError,
            PrototypeRelationInputError,
        ) as error:
            return error_response("E_INPUT", str(error))
        except (ClosedCellsError, PhysicalProjectionError) as error:
            return error_response("E_UNSUPPORTED_FEATURE", str(error))
        except AnalyticTargetError as error:
            return error_response(
                "E_UNSUPPORTED_FEATURE" if error.status == "NOT_APPLICABLE" else "E_INPUT",
                error.reason,
            )
        except GenerationError as error:
            return error_response("E_INPUT", error.reason)
        except CalibrationError as error:
            return error_response("E_INPUT", str(error))
        except TargetMeshOpeningError as error:
            if str(error).startswith("E_UNSUPPORTED_FEATURE:"):
                return error_response("E_UNSUPPORTED_FEATURE", str(error))
            return error_response("E_INPUT", str(error))
        except V0MeshPreflightError as error:
            return {
                "api_version": API_VERSION,
                "ok": False,
                "error": {
                    "code": error.code,
                    "reason": error.reason,
                    "outcome": error.outcome,
                    "gate": "V0",
                },
            }
        except (ForwardPipelineError, ForwardShapedError, ForwardClosedMechanicsError) as error:
            return error_response(error.code, error.reason)
        except (
            ApiInputError,
            CanonicalizationError,
            rfc8785.CanonicalizationError,
            RecursionError,
        ) as error:
            return error_response("E_INPUT", str(error))
