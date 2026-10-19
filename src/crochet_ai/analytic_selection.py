"""Bounded post-verification selection for native analytic CrochetIR proposals."""

from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from math import isfinite
from typing import Any, cast

from .analytic_trace_audit import bound_analytic_search_evidence, inspect_analytic_search_trace
from .backend_provenance import implementation_identity_hash, runtime_provenance
from .canonical import CanonicalProfile, canonical_hash, jcs_bytes, parse_json, validate_ijson
from .diagnostics import ArtifactValidationError
from .json_types import JSONValue
from .numerical_verification import (
    NumericalVerificationError,
    admit_numerical_run,
)
from .schema import validate_schema
from .trace_verification_types import TraceAuditInputError
from .validation import SemanticValidator
from .verification_pipeline import (
    ANALYTIC_NUMERICAL_CANDIDATE_V1,
    GATES,
    verify_artifacts,
)

PROFILE = "ANALYTIC_NUMERICAL_SELECTION_V1"
VERSION = "1.0.0"
SELECTION_DOMAIN = b"Crochet.AI\0ANALYTIC_NUMERICAL_SELECTION_V1\0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_METRICS = (
    "symmetric_chamfer_normalized",
    "robust_hausdorff_normalized",
    "silhouette_iou_complement",
    "normal_mean_degrees",
    "normal_p95_degrees",
    "section_error_normalized",
    "curvature_error_normalized",
    "relative_volume_error",
    "landmark_max_normalized",
)


class AnalyticSelectionError(ValueError):
    """Malformed global selection request, rejected before candidate execution."""

    def __init__(self, code: str, reason: str) -> None:
        self.code, self.reason = code, reason
        super().__init__(f"{code}: {reason}")


def _selection_digest(result: dict[str, JSONValue]) -> str:
    payload = deepcopy(result)
    payload["selection_evidence_sha256"] = ""
    verifications: list[JSONValue] = [payload.get("selected_verification")]
    candidates = payload.get("candidate_results")
    if isinstance(candidates, list):
        verifications.extend(
            candidate.get("verification")
            for candidate in candidates
            if isinstance(candidate, dict)
        )
    for verification in verifications:
        if not isinstance(verification, dict):
            continue
        gates = verification.get("gates")
        if isinstance(gates, list):
            for gate in gates:
                if isinstance(gate, dict):
                    gate.pop("telemetry", None)
    return sha256(SELECTION_DOMAIN + jcs_bytes(payload)).hexdigest()


def _fraction(value: object) -> Fraction:
    if type(value) is int:
        return Fraction(value)
    if type(value) is float and isfinite(value):
        return Fraction.from_float(value)
    raise AnalyticSelectionError("E_INPUT", "ranking.metric_not_binary64")


def _fraction_wire(value: Fraction) -> list[str]:
    return [str(value.numerator), str(value.denominator)]


def _gate_metric_map(gates: list[JSONValue]) -> dict[str, object]:
    gate = next(
        (item for item in gates if isinstance(item, dict) and item.get("gate_id") == "V7"), None
    )
    if not isinstance(gate, dict):
        raise AnalyticSelectionError("E_PROVENANCE", "ranking.v7_missing")
    metrics = gate.get("metric_vector")
    if not isinstance(metrics, dict):
        raise AnalyticSelectionError("E_PROVENANCE", "ranking.v7_metric_vector_missing")
    result: dict[str, object] = {}
    for key, value in metrics.items():
        if isinstance(key, str):
            result[key] = value
    result["normal_mean_degrees"] = metrics.get("surface_normal_mean_degrees")
    result["normal_p95_degrees"] = metrics.get("surface_normal_p95_degrees")
    required = {
        "symmetric_chamfer_normalized": "symmetric_chamfer_normalized",
        "robust_hausdorff_normalized": "robust_hausdorff_normalized",
        "normal_mean_degrees": "normal_mean_degrees",
        "normal_p95_degrees": "normal_p95_degrees",
        "section_error_normalized": "section_error_normalized",
        "curvature_error_normalized": "curvature_error_normalized",
        "relative_volume_error": "relative_volume_error",
        "landmark_max_normalized": "landmark_max_normalized",
    }
    normalized: dict[str, object] = {}
    for key, source in required.items():
        if source not in result:
            raise AnalyticSelectionError("E_PROVENANCE", "ranking.metric_missing." + key)
        normalized[key] = result[source]
    iou = result.get("silhouette_iou_min")
    if iou is None:
        raise AnalyticSelectionError("E_PROVENANCE", "ranking.metric_missing.silhouette_iou_min")
    normalized["silhouette_iou_complement"] = iou
    return normalized


def _shape_counts(ir: dict[str, JSONValue]) -> tuple[int, int, int]:
    stitches = ir.get("stitches")
    courses = ir.get("courses")
    operations = ir.get("construction_operations")
    if (
        not isinstance(stitches, list)
        or not isinstance(courses, list)
        or not isinstance(operations, list)
    ):
        raise AnalyticSelectionError("E_PROVENANCE", "ranking.checked_ir_shape_invalid")
    seams = sum(
        1
        for item in operations
        if isinstance(item, dict)
        and item.get("operation_type") == "JOIN"
        and item.get("join_method") == "SEWN"
    )
    cuts = sum(
        1
        for item in operations
        if isinstance(item, dict) and item.get("operation_type") == "CUT_YARN"
    )
    reattaches = sum(
        1
        for item in operations
        if isinstance(item, dict)
        and item.get("operation_type") == "ATTACH"
        and bool(item.get("input_frontier_ids"))
    )
    return seams, cuts, reattaches


def _ranking(
    ir: dict[str, JSONValue], gates: list[JSONValue], ir_hash: str
) -> tuple[tuple[object, ...], dict[str, JSONValue]]:
    seams, cuts, reattaches = _shape_counts(ir)
    metric_map = _gate_metric_map(gates)
    exact_metrics = {
        name: _fraction(metric_map[name])
        for name in _METRICS
        if name != "silhouette_iou_complement"
    }
    iou = _fraction(metric_map["silhouette_iou_complement"])
    exact_metrics["silhouette_iou_complement"] = Fraction(1) - iou
    stitches = cast(list[JSONValue], ir["stitches"])
    courses = cast(list[JSONValue], ir["courses"])
    shaping = sum(
        1
        for item in stitches
        if isinstance(item, dict) and item.get("shaping") in {"INCREASE", "DECREASE"}
    )
    key: tuple[object, ...] = (
        seams,
        cuts,
        reattaches,
        *(exact_metrics[name] for name in _METRICS),
        len(stitches),
        len(courses),
        shaping,
        ir_hash,
    )
    evidence: dict[str, JSONValue] = {
        "construction_counts": {
            "sewn_seams": seams,
            "yarn_cuts": cuts,
            "yarn_reattachments": reattaches,
            "stitches": len(stitches),
            "courses": len(courses),
            "shaping_nodes": shaping,
        },
        "metrics_exact": {
            name: cast(JSONValue, _fraction_wire(value)) for name, value in exact_metrics.items()
        },
        "canonical_crochet_ir_sha256": ir_hash,
    }
    return key, evidence


def select_analytic_numerical_candidate(
    design_spec: Mapping[str, Any],
    material_profile: Mapping[str, Any],
    search_evidence: Mapping[str, Any],
    numerical_run: object,
    selection_policy: Mapping[str, Any],
    *,
    software_commit: str,
    source_snapshot: Mapping[str, str],
) -> dict[str, JSONValue]:
    """Audit and numerically verify a bounded prefix; select only a complete batch."""
    if not all(
        isinstance(value, Mapping)
        for value in (design_spec, material_profile, search_evidence)
    ):
        raise AnalyticSelectionError("E_SCHEMA", "global.mapping_required")
    try:
        design, material = deepcopy(dict(design_spec)), deepcopy(dict(material_profile))
        evidence = bound_analytic_search_evidence(deepcopy(dict(search_evidence)))
        validate_ijson(design)
        validate_ijson(material)
    except (TypeError, ValueError) as error:
        raise AnalyticSelectionError("E_INPUT", "global.request_invalid") from error
    if not isinstance(selection_policy, Mapping):
        raise AnalyticSelectionError("E_SCHEMA", "selection_policy.invalid")
    selection_policy = deepcopy(dict(selection_policy))
    if (
        set(selection_policy) != {"profile", "schema_version", "max_candidate_evaluations"}
        or selection_policy.get("profile") != PROFILE
        or selection_policy.get("schema_version") != VERSION
    ):
        raise AnalyticSelectionError("E_SCHEMA", "selection_policy.invalid")
    solver_options = design.get("solver_options")
    if (
        not isinstance(solver_options, dict)
        or type(solver_options.get("max_candidate_evaluations")) is not int
    ):
        raise AnalyticSelectionError("E_SCHEMA", "design_spec.solver_options_invalid")
    limit = selection_policy.get("max_candidate_evaluations")
    if (
        type(limit) is not int
        or not 1 <= limit <= 8
        or limit > solver_options["max_candidate_evaluations"]
    ):
        raise AnalyticSelectionError("E_BUDGET", "selection_policy.candidate_limit_invalid")
    proposals = evidence["candidate_proposals"]
    if not isinstance(proposals, list) or len(proposals) > 8:
        raise AnalyticSelectionError("E_BUDGET", "search_evidence.proposal_limit")
    if not isinstance(software_commit, str) or not _COMMIT.fullmatch(software_commit):
        raise AnalyticSelectionError("E_INPUT", "software_commit.invalid")
    if (
        not isinstance(source_snapshot, Mapping)
        or set(source_snapshot) != {"source_snapshot_sha256", "implementation_identity"}
        or not all(
            isinstance(value, str) and _SHA256.fullmatch(value)
            for value in source_snapshot.values()
        )
    ):
        raise AnalyticSelectionError("E_INPUT", "source_snapshot.invalid")
    source_snapshot = dict(source_snapshot)
    if (
        not validate_schema("material_profile", material).ok
        or not validate_schema("design_spec", design).ok
    ):
        raise AnalyticSelectionError("E_SCHEMA", "global.design_or_material_invalid")
    global_validator = SemanticValidator(
        material_profiles={str(material.get("profile_id")): material},
    )
    material_report = global_validator.validate_material_profile(material)
    design_report = global_validator.validate_design_spec(design)
    if not design_report.ok or not material_report.ok:
        raise AnalyticSelectionError("E_SCHEMA", "global.design_or_material_invalid")
    try:
        context = admit_numerical_run(deepcopy(numerical_run))
    except NumericalVerificationError as error:
        raise AnalyticSelectionError(error.code, error.reason) from error
    if context.max_scenario_runs != 5:
        raise AnalyticSelectionError("E_BUDGET", "context.requires_exactly_five_scenarios")
    try:
        source_hash = runtime_provenance(software_commit).source_snapshot_sha256
        if (
            source_snapshot["source_snapshot_sha256"] != source_hash
            or source_snapshot["implementation_identity"] != implementation_identity_hash()
        ):
            raise AnalyticSelectionError("E_PROVENANCE", "source_snapshot.does_not_match_runtime")
    except AnalyticSelectionError:
        raise
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise AnalyticSelectionError(
            "E_PROVENANCE", "source_snapshot.runtime_identity_invalid"
        ) from error
    validator = SemanticValidator(
        design_specs={str(design.get("design_spec_id")): design},
        material_profiles={str(material.get("profile_id")): material},
    )
    try:
        audit = inspect_analytic_search_trace(
            design,
            material,
            evidence["run_config"],
            evidence["search_trace"],
            evidence["candidate_proposals"],
            validator=validator,
        )
    except (TraceAuditInputError, ArtifactValidationError) as error:
        raise AnalyticSelectionError("E_INPUT", str(error)) from error
    audit_data = cast(dict[str, JSONValue], audit.to_dict())
    request_digest = sha256(
        b"Crochet.AI\0ANALYTIC_NUMERICAL_SELECTION_REQUEST_V1\0"
        + jcs_bytes(
            {
                "design_spec": cast(JSONValue, design),
                "material_profile": cast(JSONValue, material),
                "search_evidence": cast(JSONValue, evidence),
                "numerical_run": parse_json(context.canonical_bytes),
                "selection_policy": cast(JSONValue, dict(selection_policy)),
                "software_commit": software_commit,
                "source_snapshot": cast(JSONValue, dict(source_snapshot)),
            }
        )
    ).hexdigest()
    result: dict[str, JSONValue] = {
        "profile": PROFILE,
        "schema_version": VERSION,
        "status": "INDETERMINATE",
        "verification_state": "NOT_VERIFIED",
        "physical_status": "UNTESTED",
        "selection_scope": "AUDITED_EMITTED_BATCH_ONLY",
        "source_execution_authentication": "NOT_ESTABLISHED",
        "selected_crochet_ir": None,
        "selected_crochet_ir_sha256": None,
        "candidate_results": [],
        "selection_evidence": {
            "batch_trace_audit": audit_data,
            "request_sha256": request_digest,
            "candidate_evaluation_limit": limit,
            "candidate_evaluations_reserved": min(len(proposals), limit),
            "max_fresh_scenario_runs_reserved": min(len(proposals), limit) * 5,
            "max_complete_trace_audits": min(len(proposals), limit) + 1,
        },
        "selection_evidence_sha256": "",
        "generation_terminal": (
            evidence["search_trace"].get("terminal")
            if isinstance(evidence["search_trace"], dict)
            else None
        ),
    }
    if audit.status == "FAIL":
        result["status"] = "REJECTED"
        result["verification_state"] = "REJECTED"
    elif audit.status != "PASS" or audit.missing_checks:
        result["status"] = "INDETERMINATE"
    else:
        reached = min(len(proposals), limit)
        candidate_results: list[JSONValue] = []
        eligible: list[
            tuple[
                tuple[object, ...], dict[str, JSONValue], dict[str, JSONValue], dict[str, JSONValue]
            ]
        ] = []
        for index, proposal in enumerate(proposals[:reached]):
            if not isinstance(proposal, dict):
                candidate_results.append(
                    {"index": index, "status": "REJECTED", "diagnostic": "proposal.not_object"}
                )
                continue
            ir = cast(dict[str, JSONValue], proposal)
            try:
                verification = verify_artifacts(
                    design,
                    material,
                    ir,
                    diagnostic_mode=False,
                    search_evidence=evidence,
                    profile=ANALYTIC_NUMERICAL_CANDIDATE_V1,
                    numerical_context=context,
                    software_commit=software_commit,
                    source_snapshot=source_snapshot,
                ).to_dict()
                gates = verification.get("gates")
                gate_rows: list[JSONValue] = gates if isinstance(gates, list) else []
                ir_hash = canonical_hash(ir, CanonicalProfile.CROCHET_IR, validator=validator)
                input_hashes = verification.get("input_hashes")
                profile_bound = (
                    verification.get("verification_profile_id")
                    == ANALYTIC_NUMERICAL_CANDIDATE_V1.profile_id
                    and verification.get("profile_version")
                    == ANALYTIC_NUMERICAL_CANDIDATE_V1.version
                    and isinstance(input_hashes, dict)
                    and input_hashes.get("crochet_ir") == ir_hash
                    and verification.get("verification_state") == "EXPERIMENTAL"
                    and verification.get("physical_status") == "UNTESTED"
                )
                gate_pass = (
                    profile_bound
                    and [g.get("gate_id") for g in gate_rows if isinstance(g, dict)] == list(GATES)
                    and len(gate_rows) == len(GATES)
                    and all(
                        isinstance(g, dict)
                        and g.get("verification_profile_id")
                        == ANALYTIC_NUMERICAL_CANDIDATE_V1.profile_id
                        and g.get("verification_profile_version")
                        == ANALYTIC_NUMERICAL_CANDIDATE_V1.version
                        and g.get("verification_profile_hash")
                        == ANALYTIC_NUMERICAL_CANDIDATE_V1.content_hash
                        for g in gate_rows
                    )
                    and all(
                        isinstance(g, dict)
                        and g.get("outcome") == "PASS"
                        and not g.get("missing_checks")
                        and not g.get("diagnostics")
                        and all(
                            isinstance(a, list) and len(a) == 2 and a[1] is True
                            for a in cast(list[JSONValue], g.get("assertions", []))
                        )
                        for g in gate_rows
                    )
                )
                candidate: dict[str, JSONValue] = {
                    "index": index,
                    "candidate_crochet_ir_sha256": ir_hash,
                    "verification": verification,
                    "verification_state": verification["verification_state"],
                    "physical_status": "UNTESTED",
                    "eligible": gate_pass,
                }
                if gate_pass:
                    rank_key, rank_evidence = _ranking(ir, gate_rows, ir_hash)
                    candidate["ranking"] = rank_evidence
                    eligible.append((rank_key, ir, verification, candidate))
                else:
                    candidate["status"] = (
                        "REJECTED"
                        if verification.get("verification_state") == "REJECTED"
                        else "INDETERMINATE"
                    )
                candidate_results.append(candidate)
            except NumericalVerificationError as error:
                candidate_results.append(
                    {
                        "index": index,
                        "status": "INDETERMINATE",
                        "diagnostic": {"code": error.code, "reason": error.reason},
                    }
                )
        if len(proposals) > reached:
            candidate_results.extend(
                {
                    "index": index,
                    "status": "NOT_RUN",
                    "diagnostic": "candidate_not_evaluated_due_to_policy_limit",
                }
                for index in range(reached, len(proposals))
            )
        result["candidate_results"] = candidate_results
        complete_batch = len(proposals) <= limit
        if not complete_batch:
            result["status"] = "BUDGET_EXHAUSTED"
        elif eligible and len(candidate_results) == len(proposals):
            selected = min(eligible, key=lambda row: row[0])
            result["status"] = "SELECTED"
            result["verification_state"] = "EXPERIMENTAL"
            result["selected_crochet_ir"] = selected[1]
            result["selected_crochet_ir_sha256"] = cast(str, selected[0][-1])
            result["selected_verification"] = selected[2]
            ranking_evidence = cast(dict[str, JSONValue], result["selection_evidence"])
            ranking_evidence["eligible_candidate_order"] = [
                {"index": row[3]["index"], "ranking": row[3]["ranking"]}
                for row in sorted(eligible, key=lambda row: row[0])
            ]
        elif any(
            isinstance(c, dict) and c.get("status") == "INDETERMINATE" for c in candidate_results
        ):
            result["status"] = "INDETERMINATE"
        else:
            result["status"] = "NO_FEASIBLE_CANDIDATE"
    result["selection_evidence_sha256"] = _selection_digest(result)
    return result
