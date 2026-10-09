"""Strict bounded numerical gate adapters for hypothesis-only F0 execution.

These adapters keep the forward solve target-free. Target sampling and rigid
registration happen only after a fresh successful solve; none of these gates
establishes physical calibration or physical verification.
"""

from __future__ import annotations

import math
import platform
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import TYPE_CHECKING, cast

from .analytic_coordinate_target import AnalyticCoordinateTarget
from .analytic_target import AnalyticTarget, admit_analytic_target
from .analytic_target_surface import sample_analytic_target_surface
from .backend_provenance import implementation_identity_hash, runtime_provenance
from .canonical import CanonicalProfile, canonical_hash, jcs_bytes, parse_json
from .diagnostics import ArtifactValidationError, Diagnostic, FailureCode
from .forward_closed_cells import build_closed_surface_cells
from .forward_closed_f0 import ClosedF0Error, admit_closed_f0_recipe, run_closed_f0
from .forward_f0_audit import audit_closed_f0
from .forward_graph import lower_forward_graph
from .geometry_comparison import GeometryComparisonError, _policy, compare_geometry
from .json_types import JSONValue
from .material_scenarios import GaugeScenario, MaterialScenarioError, build_gauge_scenarios
from .models import DesignSpec, MaterialProfile
from .pattern import TerminologyProfile, export_pattern, verify_semantic_round_trip
from .pattern_context import PatternParseContext, PatternYarnBinding
from .physical_projection import PhysicalProjectionError, PhysicalSemanticProjection
from .v0_mesh_preflight import V0MeshBudgets, V0MeshPreflightError, inspect_v0_mesh_v2
from .validation import SemanticValidator

if TYPE_CHECKING:
    from .verification_pipeline import GateResult

JsonObject = dict[str, JSONValue]

PROFILE = "NUMERICAL_VERIFICATION_CONTEXT_V1"
_AUDIT_PROFILE = "FORWARD_F0_AUDIT_POLICY_V1"
_AUDIT_MAX_OBJECTIVES = 20_000
_AUDIT_MAX_CONTACT_PAIRS = 2_000_000
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class NumericalVerificationError(ValueError):
    """Malformed or unsupported numerical verification input."""

    def __init__(self, code: str, reason: str) -> None:
        self.code, self.reason = code, reason
        super().__init__(f"{code}: {reason}")


@dataclass(frozen=True, slots=True)
class NumericalVerificationContext:
    canonical_bytes: bytes
    sha256: str
    forward_run: JsonObject
    target_sampling: JsonObject
    comparison_policy: JsonObject
    scenario_policy: JsonObject
    audit_policy: JsonObject
    rigid_alignment: tuple[tuple[float, float, float, float], ...]
    max_scenario_runs: int


@dataclass(frozen=True, slots=True)
class NumericalGateRunners:
    runners: dict[str, Callable[[], GateResult]]
    input_hashes: dict[str, str]
    artifacts: dict[str, JSONValue]


def admit_numerical_run(value: object) -> NumericalVerificationContext:
    """Admit a closed numerical recipe, policies, and post-solve rigid transform."""
    required = {
        "profile",
        "schema_version",
        "forward_run",
        "target_sampling",
        "comparison_policy",
        "scenario_policy",
        "audit_policy",
        "rigid_alignment",
        "max_scenario_runs",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise NumericalVerificationError("E_SCHEMA", "context.fields_invalid")
    if value["profile"] != PROFILE or value["schema_version"] != "1.0.0":
        raise NumericalVerificationError("E_UNSUPPORTED_FEATURE", "context.version_invalid")
    if type(value["max_scenario_runs"]) is not int or not 5 <= value["max_scenario_runs"] <= 9:
        raise NumericalVerificationError("E_BUDGET", "context.scenario_budget_invalid")
    try:
        recipe = admit_closed_f0_recipe(value["forward_run"])
    except (ClosedF0Error, TypeError, ValueError) as error:
        raise NumericalVerificationError("E_INPUT", "context.forward_run_invalid") from error
    for name in ("target_sampling", "comparison_policy", "scenario_policy", "audit_policy"):
        if not isinstance(value[name], dict):
            raise NumericalVerificationError("E_SCHEMA", f"context.{name}_object_required")
    comparison = cast(JsonObject, value["comparison_policy"])
    audit_policy = cast(JsonObject, value["audit_policy"])
    _validate_audit_policy(audit_policy)
    thresholds = comparison.get("hard_thresholds")
    required_metrics = {
        "symmetric_chamfer_normalized",
        "robust_hausdorff_normalized",
        "silhouette_iou_min",
        "topology_match",
        "normal_mean_degrees",
        "normal_p95_degrees",
        "section_error_normalized",
        "curvature_error_normalized",
        "relative_volume_error",
        "landmark_max_normalized",
    }
    if not isinstance(thresholds, dict) or set(thresholds) != required_metrics:
        raise NumericalVerificationError(
            "E_SCHEMA", "context.comparison_policy_requires_full_metric_vector"
        )
    for metric, threshold in thresholds.items():
        expected_unit = "degree" if metric in {"normal_mean_degrees", "normal_p95_degrees"} else "1"
        if not isinstance(threshold, dict) or threshold.get("unit") != expected_unit:
            raise NumericalVerificationError(
                "E_SCHEMA", "context.comparison_threshold_unit_invalid"
            )
    topology_threshold = thresholds["topology_match"]
    topology_value = (
        topology_threshold.get("value") if isinstance(topology_threshold, dict) else None
    )
    if not _finite(topology_value) or float(cast(int | float, topology_value)) >= 1.0:
        raise NumericalVerificationError(
            "E_SCHEMA", "context.topology_threshold_must_reject_mismatch"
        )
    try:
        _policy(comparison)
    except (GeometryComparisonError, TypeError, ValueError) as error:
        raise NumericalVerificationError("E_INPUT", "context.comparison_policy_invalid") from error
    matrix = value["rigid_alignment"]
    if (
        not isinstance(matrix, list)
        or len(matrix) != 4
        or any(not isinstance(row, list) or len(row) != 4 for row in matrix)
    ):
        raise NumericalVerificationError("E_SCHEMA", "context.rigid_alignment_shape_invalid")
    m = tuple(tuple(float(x) if _finite(x) else math.nan for x in row) for row in matrix)
    if any(not math.isfinite(x) for row in m for x in row):
        raise NumericalVerificationError("E_INPUT", "context.rigid_alignment_nonfinite")
    rotation = tuple(row[:3] for row in m[:3])
    if any(
        abs(sum(rotation[k][i] * rotation[k][j] for k in range(3)) - (1.0 if i == j else 0.0))
        > 1e-10
        for i in range(3)
        for j in range(3)
    ):
        raise NumericalVerificationError("E_INPUT", "context.rigid_alignment_not_isometry")
    det = (
        rotation[0][0] * (rotation[1][1] * rotation[2][2] - rotation[1][2] * rotation[2][1])
        - rotation[0][1] * (rotation[1][0] * rotation[2][2] - rotation[1][2] * rotation[2][0])
        + rotation[0][2] * (rotation[1][0] * rotation[2][1] - rotation[1][1] * rotation[2][0])
    )
    if abs(det - 1.0) > 1e-10 or any(
        abs(m[3][i] - (1.0 if i == 3 else 0.0)) > 1e-12 for i in range(4)
    ):
        raise NumericalVerificationError("E_INPUT", "context.rigid_alignment_not_proper_affine")
    normalized: dict[str, JSONValue] = {
        "profile": PROFILE,
        "schema_version": "1.0.0",
        "forward_run": parse_json(recipe.canonical_bytes),
        "target_sampling": cast(JSONValue, value["target_sampling"]),
        "comparison_policy": cast(JSONValue, value["comparison_policy"]),
        "scenario_policy": cast(JSONValue, value["scenario_policy"]),
        "audit_policy": cast(JSONValue, audit_policy),
        "rigid_alignment": [list(row) for row in m],
        "max_scenario_runs": value["max_scenario_runs"],
    }
    encoded = jcs_bytes(normalized)
    admitted_value = parse_json(encoded)
    if not isinstance(admitted_value, dict):
        raise NumericalVerificationError("E_SCHEMA", "context.internal_canonical_shape_invalid")
    return NumericalVerificationContext(
        encoded,
        _digest(b"NUMERICAL_VERIFICATION_CONTEXT_V1\0", encoded),
        cast(JsonObject, admitted_value["forward_run"]),
        cast(JsonObject, admitted_value["target_sampling"]),
        cast(JsonObject, admitted_value["comparison_policy"]),
        cast(JsonObject, admitted_value["scenario_policy"]),
        cast(JsonObject, admitted_value["audit_policy"]),
        cast(tuple[tuple[float, float, float, float], ...], m),
        value["max_scenario_runs"],
    )


def _validate_audit_policy(value: JsonObject) -> None:
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
    if set(value) != required or value.get("profile") != _AUDIT_PROFILE:
        raise NumericalVerificationError("E_SCHEMA", "context.audit_policy_fields_invalid")
    for key, maximum in (
        ("max_replay_objective_evaluations", _AUDIT_MAX_OBJECTIVES),
        ("max_contact_pair_evaluations", _AUDIT_MAX_CONTACT_PAIRS),
    ):
        count = value[key]
        if type(count) is not int or not 1 <= count <= maximum:
            raise NumericalVerificationError("E_BUDGET", "context.audit_policy_budget_invalid")
    for key in ("tolerance_owner", "tolerance_rationale", "validation_path"):
        text_value = value[key]
        if not isinstance(text_value, str) or not text_value.strip():
            raise NumericalVerificationError("E_SCHEMA", "context.audit_policy_rationale_required")
    for key in (
        "coordinate_abs_tolerance_mm",
        "force_abs_tolerance_n",
        "energy_abs_tolerance_n_mm",
    ):
        tolerance = value[key]
        if not _finite(tolerance) or float(cast(int | float, tolerance)) < 0:
            raise NumericalVerificationError("E_INPUT", "context.audit_policy_tolerance_invalid")


def build_numerical_gate_runners(
    design: JsonObject,
    material: JsonObject,
    ir: JsonObject,
    validator: SemanticValidator,
    context: NumericalVerificationContext,
    software_commit: str,
    source_snapshot: Mapping[str, str],
    *,
    mesh_json: bytes | None = None,
    mesh_budgets: V0MeshBudgets | None = None,
) -> NumericalGateRunners:
    """Build V6/V7/V8/V10 callbacks over admitted inputs and fresh F0 calls."""
    if not isinstance(context, NumericalVerificationContext):
        raise NumericalVerificationError("E_INPUT", "context.not_admitted")
    canonical_context = parse_json(context.canonical_bytes)
    if not isinstance(canonical_context, dict):
        raise NumericalVerificationError("E_PROVENANCE", "context.canonical_bytes_invalid")
    checked_context = admit_numerical_run(canonical_context)
    if checked_context != context:
        raise NumericalVerificationError("E_PROVENANCE", "context.fields_changed_after_admission")
    context = checked_context
    try:
        design = cast(JsonObject, parse_json(jcs_bytes(design)))
        material = cast(JsonObject, parse_json(jcs_bytes(material)))
        ir = cast(JsonObject, parse_json(jcs_bytes(ir)))
    except (TypeError, ValueError) as error:
        raise NumericalVerificationError(
            "E_INPUT", "source_documents_not_canonical_json"
        ) from error
    target_geometry = design.get("target_geometry")
    target_frame = (
        target_geometry.get("coordinate_frame") if isinstance(target_geometry, dict) else None
    )
    frame_id = target_frame.get("coordinate_frame_id") if isinstance(target_frame, dict) else None
    if (
        not isinstance(frame_id, str)
        or context.comparison_policy.get("coordinate_frame_id") != frame_id
    ):
        raise NumericalVerificationError("E_INPUT", "comparison_frame_does_not_match_design")
    if not _COMMIT.fullmatch(software_commit):
        raise NumericalVerificationError("E_PROVENANCE", "software_commit.invalid")
    if not isinstance(source_snapshot, Mapping) or not source_snapshot:
        raise NumericalVerificationError("E_PROVENANCE", "source_snapshot.required")
    if set(source_snapshot) != {"source_snapshot_sha256", "implementation_identity"}:
        raise NumericalVerificationError("E_PROVENANCE", "source_snapshot.fields_invalid")
    if any(
        not isinstance(value, str) or not _SHA256.fullmatch(value)
        for value in source_snapshot.values()
    ):
        raise NumericalVerificationError("E_PROVENANCE", "source_snapshot.digest_invalid")
    snapshot: dict[str, str] = {}
    for key, digest in source_snapshot.items():
        if (
            not isinstance(key, str)
            or not key
            or not isinstance(digest, str)
            or not _SHA256.fullmatch(digest)
        ):
            raise NumericalVerificationError("E_PROVENANCE", "source_snapshot.invalid")
        snapshot[key] = digest
    if snapshot != {
        "source_snapshot_sha256": runtime_provenance(software_commit).source_snapshot_sha256,
        "implementation_identity": implementation_identity_hash(),
    }:
        raise NumericalVerificationError(
            "E_PROVENANCE", "server_source_snapshot_or_implementation_identity_mismatch"
        )
    try:
        projection = PhysicalSemanticProjection(ir, material, validator=validator)
        closed_cells = build_closed_surface_cells(projection, max_vertices=2048, max_faces=4096)
        cell_payload = closed_cells.to_dict()
        expected_vertices = set(cell_payload["vertices"])
        expected_faces = cell_payload["faces"]
        closed = cast(JsonObject, context.forward_run["closed_recipe"])
        elastic = cast(JsonObject, closed["elastic_recipe"])
        tension_id = elastic.get("tension_profile_id")
        fabric_state = elastic.get("fabric_state")
        if not isinstance(tension_id, str) or not isinstance(fabric_state, str):
            raise NumericalVerificationError("E_INPUT", "forward_material_selection_invalid")
        graph = lower_forward_graph(
            projection,
            material,
            tension_id,
            fabric_state,
            validator=validator,
        )
        geometry_type = (
            target_geometry.get("geometry_type") if isinstance(target_geometry, dict) else None
        )
        if geometry_type == "MESH_3D":
            if not isinstance(mesh_json, bytes) or not isinstance(mesh_budgets, V0MeshBudgets):
                raise NumericalVerificationError(
                    "E_INPUT", "mesh_target_bytes_and_budgets_required"
                )
            if set(context.target_sampling) != {"profile", "schema_version"} or (
                context.target_sampling.get("profile") != "MESH_ADMITTED_TARGET_SURFACE_V1"
                or context.target_sampling.get("schema_version") != "1.0.0"
            ):
                raise NumericalVerificationError(
                    "E_UNSUPPORTED_FEATURE", "mesh_target_sampling_profile_invalid"
                )
            design_model = DesignSpec.from_dict(design)
            material_model = MaterialProfile.from_dict(material)
            try:
                admitted_mesh = inspect_v0_mesh_v2(
                    design_model,
                    mesh_json,
                    material_profile=material_model,
                    budgets=mesh_budgets,
                )
            except V0MeshPreflightError as error:
                raise NumericalVerificationError(
                    "E_INPUT", "mesh_target_v0_admission_failed"
                ) from error
            if admitted_mesh.outcome != "PASS":
                raise NumericalVerificationError("E_INPUT", "mesh_target_v0_not_pass")
            expectation = cast(JsonObject, target_geometry).get("topology_expectation")
            if (
                admitted_mesh.domain_profile_id != "V0_AMIGURUMI_CLOSED_SURFACE_V1"
                or not isinstance(expectation, dict)
                or expectation.get("expected_connected_components") != 1
                or not _closed_genus_zero_mesh(admitted_mesh.normalized_mesh_jcs)
            ):
                raise NumericalVerificationError(
                    "E_UNSUPPORTED_FEATURE", "mesh_target_must_be_closed_single_genus_zero"
                )
            target_mesh: JSONValue = parse_json(admitted_mesh.normalized_mesh_jcs)
            if not isinstance(target_mesh, dict):
                raise NumericalVerificationError("E_PROVENANCE", "normalized_mesh_shape_invalid")
            normalized_frame = target_mesh.get("coordinate_system")
            normalized_frame_id = (
                normalized_frame.get("coordinate_frame_id")
                if isinstance(normalized_frame, dict)
                else None
            )
            if (
                admitted_mesh.source_sha256 != sha256(mesh_json).hexdigest()
                or admitted_mesh.coordinate_frame_id != frame_id
                or normalized_frame_id != frame_id
            ):
                raise NumericalVerificationError("E_PROVENANCE", "mesh_target_binding_mismatch")
            target_sha256 = admitted_mesh.normalized_mesh_sha256
            target_sampling_evidence: JSONValue = {
                "profile": "MESH_ADMITTED_TARGET_SURFACE_V1",
                "schema_version": "1.0.0",
                "raw_source_sha256": admitted_mesh.source_sha256,
                "normalized_mesh_sha256": admitted_mesh.normalized_mesh_sha256,
                "v0_evidence_sha256": admitted_mesh.evidence_sha256,
                "v0_domain_profile_id": admitted_mesh.domain_profile_id,
                "coordinate_frame_id": admitted_mesh.coordinate_frame_id,
                "interpolation": "NONE",
            }
        else:
            if mesh_json is not None or mesh_budgets is not None:
                raise NumericalVerificationError("E_INPUT", "mesh_supplied_for_non_mesh_target")
            target: AnalyticTarget | AnalyticCoordinateTarget = admit_analytic_target(
                design, validator
            )
            sampled = sample_analytic_target_surface(
                cast(dict[str, object], design),
                target,
                context.target_sampling,
                validator=validator,
            )
            target_mesh = parse_json(sampled.sampled_mesh_jcs_bytes)
            target_sha256 = sampled.sampled_mesh_sha256
            target_sampling_evidence = sampled.to_dict()
        material_hash = canonical_hash(material, CanonicalProfile.MATERIAL_PROFILE)
        ir_hash = canonical_hash(ir, CanonicalProfile.CROCHET_IR, validator=validator)
        design_hash = canonical_hash(design, CanonicalProfile.DESIGN_SPEC, validator=validator)
        _check_landmark_bindings(
            design, context.comparison_policy, frame_id, len(expected_vertices)
        )
    except NumericalVerificationError:
        raise
    except (
        ArtifactValidationError,
        PhysicalProjectionError,
        ValueError,
        KeyError,
        TypeError,
    ) as error:
        raise NumericalVerificationError("E_INPUT", "source_or_target_admission_failed") from error
    hashes = {
        "design_spec": design_hash,
        "material_profile": material_hash,
        "crochet_ir": ir_hash,
        "physical_projection": projection.sha256,
        "numerical_context": context.sha256,
        "software_commit": sha256(software_commit.encode()).hexdigest(),
        "source_snapshot": _digest(b"SOURCE_SNAPSHOT_V1\0", jcs_bytes(cast(JSONValue, snapshot))),
    }
    state: dict[str, JSONValue] = {
        "f0_runs": [],
        "f0_audits": [],
        "comparison": None,
        "sampled_target": target_sampling_evidence,
    }
    gate_cache: dict[str, GateResult] = {}

    def run(scenario: GaugeScenario | None = None) -> JsonObject:
        recipe = admit_closed_f0_recipe(context.forward_run)
        result = run_closed_f0(
            projection,
            material,
            recipe,
            validator=validator,
            gauge_scenario=scenario,
            gauge_policy=context.scenario_policy if scenario is not None else None,
        )
        if (
            result.get("projection_sha256") != projection.sha256
            or result.get("material_sha256") != material_hash
            or result.get("recipe_sha256") != recipe.sha256
            or result.get("gauge_scenario_sha256")
            != (None if scenario is None else scenario.scenario_sha256)
        ):
            raise NumericalVerificationError("E_PROVENANCE", "forward_run_binding_mismatch")
        if result.get("status") == "CONVERGED" and not _source_geometry_matches(
            result, expected_vertices, expected_faces
        ):
            raise NumericalVerificationError("E_PROVENANCE", "forward_geometry_projection_mismatch")
        cast(list[JSONValue], state["f0_runs"]).append(cast(JSONValue, result))
        return result

    def v6() -> GateResult:
        if "V6" in gate_cache:
            return gate_cache["V6"]
        result = run()
        state["V6_forward_run"] = cast(JSONValue, result)
        audit = _audit_successful_result(result, None)
        if audit is not None:
            state["V6_f0_audit"] = audit
        gate_cache["V6"] = _f0_gate_result(
            "V6", result, hashes["crochet_ir"], context.forward_run, audit
        )
        return gate_cache["V6"]

    def _audit_successful_result(
        result: JsonObject, scenario: GaugeScenario | None
    ) -> JsonObject | None:
        if (
            not _f0_integrity(result, context.forward_run)
            or result.get("status") != "CONVERGED"
            or result.get("comparison_eligible") is not True
        ):
            return None
        if scenario is not None:
            scenario_policy: object | None = context.scenario_policy
            gauge_scenario: GaugeScenario | None = scenario
        else:
            scenario_policy = None
            gauge_scenario = None
        audit = audit_closed_f0(
            projection,
            material,
            admit_closed_f0_recipe(context.forward_run),
            result,
            validator=validator,
            policy=context.audit_policy,
            gauge_scenario=gauge_scenario,
            gauge_policy=scenario_policy,
        )
        audit["audit_sha256"] = _digest(
            b"FORWARD_CLOSED_F0_AUDIT_EVIDENCE_V1\0",
            jcs_bytes(cast(JSONValue, audit)),
        )
        cast(list[JSONValue], state["f0_audits"]).append(cast(JSONValue, audit))
        return audit

    def compare_result(result: JsonObject) -> JsonObject | None:
        if result.get("status") != "CONVERGED" or result.get("comparison_eligible") is not True:
            return None
        coordinates, faces = result.get("coordinates_mm"), result.get("faces")
        if not isinstance(coordinates, list) or not isinstance(faces, list):
            return None
        points: dict[str, list[float]] = {}
        for row in coordinates:
            if not isinstance(row, dict) or not isinstance(row.get("attachment_location_id"), str):
                return None
            xyz = row.get("position_mm")
            if not isinstance(xyz, list) or len(xyz) != 3 or any(not _finite(x) for x in xyz):
                return None
            location_id = row.get("attachment_location_id")
            if not isinstance(location_id, str):
                return None
            point = [float(cast(int | float, value)) for value in xyz]
            points[location_id] = _transform(context.rigid_alignment, point)
        ids = sorted(points)
        index = {key: i for i, key in enumerate(ids)}
        face_ids: list[list[int]] = []
        for face in faces:
            if (
                not isinstance(face, list)
                or len(face) != 3
                or any(not isinstance(key, str) or key not in index for key in face)
            ):
                return None
            face_ids.append([index[cast(str, key)] for key in face])
        predicted = _mesh_dict(frame_id, [points[key] for key in ids], face_ids)
        try:
            compared = compare_geometry(
                predicted,
                cast(JsonObject, target_mesh),
                context.comparison_policy,
            )
        except (GeometryComparisonError, ValueError, TypeError):
            return None
        return compared

    def v7() -> GateResult:
        if "V7" in gate_cache:
            return gate_cache["V7"]
        if "V6" not in gate_cache:
            gate_cache["V7"] = _indeterminate(
                "V7", hashes["crochet_ir"], "V6_fresh_forward_run_not_yet_available"
            )
            return gate_cache["V7"]
        if gate_cache["V6"].outcome.value != "PASS":
            gate_cache["V7"] = _indeterminate(
                "V7", hashes["crochet_ir"], "V6_did_not_admit_comparison_geometry"
            )
            return gate_cache["V7"]
        result = cast(JsonObject, state["V6_forward_run"])
        comparison = compare_result(result) if _f0_integrity(result, context.forward_run) else None
        state["comparison"] = comparison
        if comparison is None:
            gate_cache["V7"] = _indeterminate(
                "V7", hashes["crochet_ir"], "forward_result_not_comparison_eligible"
            )
            return gate_cache["V7"]
        gate_cache["V7"] = _comparison_gate_result("V7", comparison, hashes["crochet_ir"])
        return gate_cache["V7"]

    def v8() -> GateResult:
        if "V8" in gate_cache:
            return gate_cache["V8"]
        if "V6" not in gate_cache:
            gate_cache["V8"] = _indeterminate(
                "V8", hashes["material_profile"], "V6_nominal_forward_run_not_yet_available"
            )
            return gate_cache["V8"]
        try:
            scenarios = build_gauge_scenarios(material, graph, context.scenario_policy)
        except (MaterialScenarioError, ValueError, TypeError) as error:
            gate_cache["V8"] = _indeterminate(
                "V8", hashes["material_profile"], f"scenario_admission:{error}"
            )
            return gate_cache["V8"]
        if len(scenarios) != 5 or len(scenarios) > context.max_scenario_runs:
            gate_cache["V8"] = _indeterminate(
                "V8", hashes["material_profile"], "required_scenario_set_or_budget_invalid"
            )
            return gate_cache["V8"]
        rows: list[JSONValue] = []
        fails = False
        incomplete = False
        for scenario_index, scenario in enumerate(scenarios):
            result = (
                cast(JsonObject, state["V6_forward_run"]) if scenario_index == 0 else run(scenario)
            )
            audit = (
                cast(JsonObject, state["V6_f0_audit"])
                if scenario_index == 0 and isinstance(state.get("V6_f0_audit"), dict)
                else _audit_successful_result(result, scenario)
            )
            comparison = (
                compare_result(result)
                if audit is not None
                and audit.get("status") == "PASS"
                and _f0_integrity(result, context.forward_run)
                else None
            )
            row: dict[str, JSONValue] = {
                "scenario_id": scenario.scenario_id,
                "scenario_sha256": scenario.scenario_sha256,
                "f0_status": str(result.get("status")),
                "f0_audit": audit,
                "comparison": comparison,
            }
            rows.append(row)
            if audit is not None and audit.get("status") == "FAIL":
                fails = True
            elif (
                result.get("status") == "BUDGET_EXHAUSTED"
                and _f0_integrity(result, context.forward_run)
            ) or (audit is not None and audit.get("status") == "INDETERMINATE"):
                incomplete = True
            elif result.get("status") != "CONVERGED":
                fails = True
            elif comparison is None:
                incomplete = True
            elif cast(str, comparison.get("outcome")) == "FAIL":
                fails = True
            elif cast(str, comparison.get("outcome")) != "PASS":
                incomplete = True
        state["scenario_results"] = rows
        if fails:
            gate_cache["V8"] = _failed(
                "V8", hashes["material_profile"], "scenario_forward_or_comparison_failed", rows
            )
            return gate_cache["V8"]
        if incomplete:
            gate_cache["V8"] = _indeterminate(
                "V8", hashes["material_profile"], "scenario_checks_incomplete", rows
            )
            return gate_cache["V8"]
        from .verification_pipeline import GateOutcome, GateResult

        gate_cache["V8"] = GateResult(
            GateOutcome.PASS,
            assertions=(("all_five_required_material_endpoint_scenarios_pass", True),),
            scope=(
                "Finite five-case material endpoint hypothesis sweep; no continuous "
                "coverage or calibration claim"
            ),
            produced_artifact_hashes=(
                ("scenario_sweep", _digest(b"V8_SCENARIOS\0", jcs_bytes(rows))),
            ),
            threshold_profile_id="MATERIAL_SCENARIO_POLICY_V1",
            linked_evidence_json=jcs_bytes(
                {"results": rows, "physical_status": "UNTESTED"}
            ).decode(),
        )
        return gate_cache["V8"]

    def v10() -> GateResult:
        if "V10" in gate_cache:
            return gate_cache["V10"]
        if not {"V6", "V7", "V8"}.issubset(gate_cache):
            gate_cache["V10"] = _indeterminate(
                "V10", hashes["crochet_ir"], "V6_V7_V8_evidence_not_yet_available"
            )
            return gate_cache["V10"]
        if any(gate_cache[name].outcome.value != "PASS" for name in ("V6", "V7", "V8")):
            gate_cache["V10"] = _indeterminate(
                "V10", hashes["crochet_ir"], "required_numerical_gates_not_all_passed"
            )
            return gate_cache["V10"]
        nominal = state.get("V6_forward_run")
        comparison = state.get("comparison")
        scenarios_evidence = state.get("scenario_results")
        audit_records = state.get("f0_audits")
        audits_valid = (
            isinstance(audit_records, list)
            and len(audit_records) == 5
            and all(_audit_record_is_valid(item) for item in audit_records)
        )
        v8_sweep_hash = dict(gate_cache["V8"].produced_artifact_hashes).get("scenario_sweep")
        linked_scenario_hash = (
            _digest(b"V8_SCENARIOS\0", jcs_bytes(cast(JSONValue, scenarios_evidence)))
            if isinstance(scenarios_evidence, list)
            else None
        )
        scenario_audit_hashes = (
            [
                cast(JsonObject, row["f0_audit"]).get("audit_sha256")
                for row in scenarios_evidence
                if isinstance(row, dict) and isinstance(row.get("f0_audit"), dict)
            ]
            if isinstance(scenarios_evidence, list)
            else []
        )
        state_audit_hashes = (
            [item.get("audit_sha256") for item in audit_records if isinstance(item, dict)]
            if isinstance(audit_records, list)
            else []
        )
        v6_audit_hash = dict(gate_cache["V6"].produced_artifact_hashes).get("forward_f0_audit")
        if (
            not isinstance(nominal, dict)
            or not isinstance(comparison, dict)
            or not isinstance(scenarios_evidence, list)
            or not audits_valid
            or v8_sweep_hash != linked_scenario_hash
            or scenario_audit_hashes != state_audit_hashes
            or not state_audit_hashes
            or state_audit_hashes[0] != v6_audit_hash
            or not gate_cache["V6"].produced_artifact_hashes
            or not gate_cache["V7"].produced_artifact_hashes
            or not gate_cache["V8"].produced_artifact_hashes
        ):
            gate_cache["V10"] = _indeterminate(
                "V10", hashes["crochet_ir"], "required_provenance_link_missing"
            )
            return gate_cache["V10"]
        yarns = ir.get("yarns")
        colors = ir.get("colors")
        if not isinstance(yarns, list) or len(yarns) != 1 or not isinstance(colors, list):
            gate_cache["V10"] = _indeterminate(
                "V10", hashes["crochet_ir"], "single_yarn_export_scope_required"
            )
            return gate_cache["V10"]
        yarn = yarns[0]
        if not isinstance(yarn, dict):
            gate_cache["V10"] = _indeterminate(
                "V10", hashes["crochet_ir"], "yarn_binding_record_invalid"
            )
            return gate_cache["V10"]
        color = next(
            (
                c
                for c in colors
                if isinstance(c, dict) and c.get("color_id") == yarn.get("color_id")
            ),
            None,
        )
        if not isinstance(color, dict):
            gate_cache["V10"] = _indeterminate(
                "V10", hashes["crochet_ir"], "yarn_color_binding_missing"
            )
            return gate_cache["V10"]
        color_label, color_hex = color.get("label"), color.get("srgb_hex")
        if not isinstance(color_label, str) or not isinstance(color_hex, str):
            gate_cache["V10"] = _indeterminate(
                "V10", hashes["crochet_ir"], "yarn_color_attributes_invalid"
            )
            return gate_cache["V10"]
        parse_context = PatternParseContext(
            design, (PatternYarnBinding("Yarn A", material, color_label, color_hex),)
        )
        assertions: list[tuple[str, bool]] = []
        produced: list[tuple[str, str]] = []
        diagnostics: list[Diagnostic] = []
        for terminology in TerminologyProfile:
            report = verify_semantic_round_trip(
                ir, terminology, context=parse_context, validator=validator
            )
            assertions.append((f"semantic_round_trip.{terminology.value}", report.ok))
            diagnostics.extend(report.diagnostics)
            if report.ok:
                exported = export_pattern(ir, terminology, validator=validator)
                produced.append(
                    (
                        f"pattern_text.{terminology.value}",
                        sha256(exported.encode("utf-8")).hexdigest(),
                    )
                )
        from .verification_pipeline import GateOutcome, GateResult

        provenance_chain: dict[str, JSONValue] = {
            "input_hashes": cast(JSONValue, hashes),
            "forward_recipe_sha256": nominal.get("recipe_sha256"),
            "nominal_forward_sha256": nominal.get("sha256"),
            "forward_audit_sha256s": [
                audit.get("audit_sha256")
                for audit in cast(list[JSONValue], audit_records)
                if isinstance(audit, dict)
            ],
            "sampled_target_sha256": target_sha256,
            "comparison_sha256": comparison.get("sha256"),
            "scenario_results_sha256": _digest(
                b"V8_SCENARIOS\0", jcs_bytes(cast(JSONValue, scenarios_evidence))
            ),
            "export_hashes": cast(JSONValue, dict(produced)),
            "software_commit": software_commit,
            "source_snapshot": cast(JSONValue, snapshot),
            "runtime": {
                "python_implementation": platform.python_implementation(),
                "python_version": platform.python_version(),
            },
            "source_execution_authentication": "NOT_ESTABLISHED",
            "commit_checkout_binding": "UNCONFIRMED",
            "consistency_scope": "runtime_recipe_and_artifact_link_consistency_only",
            "physical_status": "UNTESTED",
        }
        gate_cache["V10"] = GateResult(
            GateOutcome.FAIL if diagnostics else GateOutcome.PASS,
            assertions=tuple(assertions),
            diagnostics=tuple(diagnostics),
            scope=(
                "Runtime, recipe, artifact-link, and semantic DE/US/UK export consistency; "
                "source execution authentication is not established; physical status remains "
                "UNTESTED"
            ),
            produced_artifact_hashes=tuple(produced),
            threshold_profile_id="SEMANTIC_EXPORT_ROUNDTRIP_V1",
            linked_evidence_json=jcs_bytes(provenance_chain).decode(),
        )
        state["V10_provenance_chain"] = provenance_chain
        return gate_cache["V10"]

    return NumericalGateRunners(
        {"V6": v6, "V7": v7, "V8": v8, "V10": v10},
        {
            key: value
            for key, value in hashes.items()
            if key
            not in {
                "design_spec",
                "material_profile",
                "crochet_ir",
            }
        },
        state,
    )


def _check_landmark_bindings(
    design: JsonObject, policy: JsonObject, frame_id: str, vertex_count: int
) -> None:
    """Bind every nominated prediction vertex to an authoritative target requirement."""
    requirements = design.get("landmarks")
    nominations = policy.get("landmarks")
    if not isinstance(requirements, list) or not isinstance(nominations, list):
        raise NumericalVerificationError("E_INPUT", "landmark_lists_required")
    required: dict[str, JsonObject] = {}
    for requirement in requirements:
        if not isinstance(requirement, dict) or not isinstance(requirement.get("landmark_id"), str):
            raise NumericalVerificationError("E_INPUT", "landmark_requirement_invalid")
        identifier = cast(str, requirement["landmark_id"])
        if identifier in required or requirement.get("coordinate_frame_id") != frame_id:
            raise NumericalVerificationError(
                "E_PROVENANCE", "landmark_requirement_frame_or_id_invalid"
            )
        required[identifier] = requirement
    nominated: dict[str, JsonObject] = {}
    for nomination in nominations:
        if not isinstance(nomination, dict) or not isinstance(nomination.get("name"), str):
            raise NumericalVerificationError("E_INPUT", "landmark_nomination_invalid")
        identifier = cast(str, nomination["name"])
        if identifier in nominated:
            raise NumericalVerificationError("E_PROVENANCE", "landmark_nomination_duplicate")
        nominated[identifier] = nomination
    if set(required) != set(nominated):
        raise NumericalVerificationError("E_PROVENANCE", "landmark_requirement_set_mismatch")
    thresholds = _json_object(policy.get("hard_thresholds"))
    threshold = (
        None if thresholds is None else _json_object(thresholds.get("landmark_max_normalized"))
    )
    bound = None if threshold is None else _native_number(threshold.get("value"))
    length = _native_number(policy.get("characteristic_length_mm"))
    if bound is None or length is None:
        raise NumericalVerificationError("E_INPUT", "landmark_threshold_invalid")
    from fractions import Fraction

    absolute_bound = Fraction.from_float(bound) * Fraction.from_float(length)
    for identifier, requirement in required.items():
        nomination = nominated[identifier]
        if jcs_bytes(nomination.get("target_xyz_mm")) != jcs_bytes(requirement.get("position_mm")):
            raise NumericalVerificationError("E_PROVENANCE", "landmark_target_position_mismatch")
        index = nomination.get("predicted_vertex_index")
        if type(index) is not int or not 0 <= index < vertex_count:
            raise NumericalVerificationError("E_REFERENCE", "landmark_prediction_vertex_invalid")
        tolerance = _native_number(requirement.get("tolerance_mm"))
        if tolerance is None or tolerance < 0 or absolute_bound > Fraction.from_float(tolerance):
            raise NumericalVerificationError(
                "E_INPUT", "landmark_threshold_exceeds_design_tolerance"
            )


def _f0_gate_result(
    gate: str,
    result: JsonObject,
    artifact_hash: str,
    recipe: JsonObject,
    audit: JsonObject | None,
) -> GateResult:
    from .verification_pipeline import GateOutcome, GateResult

    starts = result.get("starts")
    ok = (
        _f0_integrity(result, recipe)
        and result.get("status") == "CONVERGED"
        and result.get("comparison_eligible") is True
        and isinstance(starts, list)
        and len(starts) == _native_int(_json_object(recipe.get("solver_parameters")), "start_count")
        and all(
            isinstance(s, dict)
            and s.get("status") == "CONVERGED"
            and isinstance(s.get("coordinates_mm"), list)
            and bool(s.get("coordinates_mm"))
            for s in starts
        )
    )
    assertions = (
        ("fresh_target_free_f0_run", True),
        ("all_required_starts_converged", bool(ok)),
        (
            "geometry_exposed_only_on_convergence",
            result.get("coordinates_mm") is None or bool(ok),
        ),
    )
    if _f0_integrity(result, recipe) and result.get("status") == "BUDGET_EXHAUSTED":
        return _indeterminate(
            gate,
            artifact_hash,
            "forward_model_work_budget_exhausted_before_convergence",
            cast(JSONValue, result),
        )
    if ok:
        if audit is None:
            return _indeterminate(
                gate, artifact_hash, "independent_f0_replay_audit_missing", cast(JSONValue, result)
            )
        audit_status = audit.get("status")
        if audit_status != "PASS":
            if audit_status == "INDETERMINATE":
                return _indeterminate(
                    gate,
                    artifact_hash,
                    f"independent_f0_replay_audit:{audit.get('reason', 'incomplete')}",
                    cast(JSONValue, audit),
                )
            return _failed(
                gate,
                artifact_hash,
                f"independent_f0_replay_audit:{audit.get('reason', 'failed')}",
                cast(JSONValue, audit),
            )
        return GateResult(
            GateOutcome.PASS,
            assertions=(*assertions, ("independent_f0_replay_audit", True)),
            scope="Bounded hypothesis F0 numerical convergence; not physical evidence",
            produced_artifact_hashes=(
                ("forward_run", cast(str, result.get("sha256"))),
                ("forward_f0_audit", cast(str, audit.get("audit_sha256"))),
            ),
            threshold_profile_id="FORWARD_CLOSED_F0_V1",
            linked_evidence_json=jcs_bytes(
                {"forward_run": result, "independent_audit": audit}
            ).decode(),
        )
    return _failed(
        gate, artifact_hash, f"forward_status:{result.get('status')}", cast(JSONValue, result)
    )


def _audit_record_is_valid(value: JSONValue) -> bool:
    if not isinstance(value, dict) or value.get("status") != "PASS":
        return False
    digest = value.get("audit_sha256")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        return False
    unsigned = {key: item for key, item in value.items() if key != "audit_sha256"}
    try:
        return digest == _digest(
            b"FORWARD_CLOSED_F0_AUDIT_EVIDENCE_V1\0",
            jcs_bytes(cast(JSONValue, unsigned)),
        )
    except (TypeError, ValueError):
        return False


def _f0_integrity(result: JsonObject, recipe: JsonObject) -> bool:
    unsigned = {key: value for key, value in result.items() if key != "sha256"}
    try:
        actual_digest = sha256(
            b"Crochet.AI\0FORWARD_CLOSED_F0_V1\0" + jcs_bytes(cast(JSONValue, unsigned))
        ).hexdigest()
    except (TypeError, ValueError):
        return False
    if (
        result.get("profile") != "FORWARD_CLOSED_F0_V1"
        or result.get("sha256") != actual_digest
        or result.get("verification_state") != "NOT_VERIFIED"
        or result.get("physical_status") != "UNTESTED"
        or result.get("constitutive_status") != "HYPOTHESIS"
    ):
        return False
    solver = _json_object(recipe.get("solver_parameters"))
    closed = _json_object(recipe.get("closed_recipe"))
    elastic = _json_object(closed.get("elastic_recipe")) if closed is not None else None
    config = _json_object(elastic.get("config")) if elastic is not None else None
    if solver is None or config is None:
        return False
    budgets, tolerances, starts = (
        _json_object(config.get("work_budgets")),
        _json_object(config.get("tolerances")),
        result.get("starts"),
    )
    if budgets is None or tolerances is None:
        return False
    start_count = _native_int(solver, "start_count")
    if not isinstance(starts, list) or start_count is None or len(starts) != start_count:
        return False
    force_tolerance = _nested_number(tolerances, "force_residual_n", "value")
    step_tolerance = _nested_number(tolerances, "position_step_mm", "value")
    energy_tolerance = _nested_number(tolerances, "relative_energy_change", "value")
    mode_tolerance = _nested_number(tolerances, "mode_equivalence_rms_mm", "value")
    max_iterations = _native_int(budgets, "max_optimizer_iterations")
    max_evaluations = _native_int(budgets, "max_energy_evaluations")
    max_trials = _native_int(budgets, "max_line_search_trials")
    if (
        force_tolerance is None
        or step_tolerance is None
        or energy_tolerance is None
        or mode_tolerance is None
        or max_iterations is None
        or max_evaluations is None
        or max_trials is None
    ):
        return False
    if result.get("status") == "CONVERGED":
        top_coordinates = result.get("coordinates_mm")
        top_faces = result.get("faces")
        if (
            not isinstance(top_coordinates, list)
            or not top_coordinates
            or not isinstance(top_faces, list)
            or not top_faces
            or _json_object(result.get("final_mechanics")) is None
            or _native_number(result.get("mode_equivalence_rms_mm")) is None
            or result.get("preparation_energy_evaluations") != 1
        ):
            return False
        maximum_contact_pairs = _native_int(budgets, "max_contact_pairs_evaluated")
        contact_work = _json_object(result.get("contact_work"))
        contact_pairs = _native_int(contact_work, "pair_evaluations")
        if (
            maximum_contact_pairs is None
            or contact_pairs is None
            or contact_pairs > maximum_contact_pairs
        ):
            return False
        for item in starts:
            start = _json_object(item)
            if start is None or start.get("status") != "CONVERGED":
                return False
            force = _native_number(start.get("maximum_force_n"))
            step = _native_number(start.get("last_step_mm"))
            energy = _native_number(start.get("relative_energy_change"))
            iterations = _native_int(start, "optimizer_iterations")
            evaluations = _native_int(start, "energy_evaluations")
            trials = _native_int(start, "line_search_trials")
            coordinates = start.get("coordinates_mm")
            stationary = _native_int(start, "stationary_checks")
            if (
                force is None
                or step is None
                or energy is None
                or iterations is None
                or evaluations is None
                or trials is None
                or stationary is None
                or stationary < 2
                or force > force_tolerance
                or step > step_tolerance
                or energy > energy_tolerance
                or iterations > max_iterations
                or evaluations > max_evaluations
                or trials > max_iterations * max_trials
                or evaluations < stationary
                or min(force, step, energy) < 0
                or not isinstance(coordinates, list)
                or not coordinates
            ):
                return False
        mode_rms = _native_number(result.get("mode_equivalence_rms_mm"))
        if mode_rms is None or mode_rms < 0 or mode_rms > mode_tolerance:
            return False
    else:
        if result.get("coordinates_mm") is not None or result.get("faces") is not None:
            return False
        for item in starts:
            start = _json_object(item)
            if start is not None and start.get("coordinates_mm") is not None:
                return False
    return True


def _comparison_gate_result(gate: str, result: JsonObject, artifact_hash: str) -> GateResult:
    from .verification_pipeline import GateOutcome, GateResult

    outcome = result.get("outcome")
    if outcome == "FAIL":
        record = _failed(
            gate, artifact_hash, "comparison_threshold_failed", cast(JSONValue, result)
        )
    elif outcome != "PASS":
        record = _indeterminate(
            gate, artifact_hash, "comparison_has_indeterminate_metrics", cast(JSONValue, result)
        )
    else:
        record = GateResult(
            GateOutcome.PASS,
            assertions=(("sampled_mesh_comparison_checks_pass", True),),
        )
    return replace(
        record,
        scope=(
            "Target mesh comparison under the selected analytic discretization or V0-admitted "
            "mesh profile; ideal-surface and physical acceptance not established"
        ),
        produced_artifact_hashes=(("geometry_comparison", cast(str, result.get("sha256"))),),
        threshold_profile_id="GEOMETRY_COMPARISON_DIAGNOSTIC_V1",
        metric_vector_json=jcs_bytes(result.get("metrics", {})).decode(),
        parameters_json=jcs_bytes(result.get("policy", {})).decode(),
        work_budget_json=jcs_bytes(result.get("work", {})).decode(),
        linked_evidence_json=jcs_bytes(result).decode(),
    )


def _failed(
    gate: str, artifact_hash: str, reason: str, evidence: JSONValue | None = None
) -> GateResult:
    from .verification_pipeline import GateOutcome, GateResult

    diagnostic = Diagnostic(
        FailureCode.INPUT,
        gate,
        "numerical_gate.failed",
        reason,
        artifact_hash,
        implementation_version="numerical-verification/1.0.0",
    )
    return GateResult(
        GateOutcome.FAIL,
        diagnostics=(diagnostic,),
        scope="Numerical execution failed closed",
        linked_evidence_json=jcs_bytes({"evidence": evidence}).decode(),
    )


def _indeterminate(
    gate: str, artifact_hash: str, reason: str, evidence: JSONValue | None = None
) -> GateResult:
    from .verification_pipeline import GateOutcome, GateResult

    return GateResult(
        GateOutcome.INDETERMINATE,
        missing_checks=(reason,),
        scope="Numerical evidence incomplete; no physical claim",
        linked_evidence_json=jcs_bytes(
            {"evidence": evidence, "physical_status": "UNTESTED"}
        ).decode(),
    )


def _mesh_dict(
    frame: str, vertices: list[list[float]], faces: list[list[int]]
) -> dict[str, JSONValue]:
    return {
        "representation_version": "INDEXED_TRIANGLE_MESH_V1",
        "coordinate_system": {
            "length_unit": "MILLIMETER",
            "handedness": "RIGHT_HANDED",
            "coordinate_frame_id": frame,
        },
        "vertices": [{"position_mm": cast(JSONValue, p)} for p in vertices],
        "faces": [{"vertex_indices": cast(JSONValue, f)} for f in faces],
    }


def _closed_genus_zero_mesh(normalized_mesh_jcs: str) -> bool:
    value = parse_json(normalized_mesh_jcs)
    if not isinstance(value, dict):
        return False
    vertices, faces = value.get("vertices"), value.get("faces")
    if not isinstance(vertices, list) or not vertices or not isinstance(faces, list) or not faces:
        return False
    edges: set[tuple[int, int]] = set()
    for face_record in faces:
        if not isinstance(face_record, dict):
            return False
        indices = face_record.get("vertex_indices")
        if (
            not isinstance(indices, list)
            or len(indices) != 3
            or any(type(index) is not int or not 0 <= index < len(vertices) for index in indices)
            or len(set(indices)) != 3
        ):
            return False
        a, b, c = cast(list[int], indices)
        face_edges = ((a, b), (b, c), (c, a))
        edges.update((min(left, right), max(left, right)) for left, right in face_edges)
    return len(vertices) - len(edges) + len(faces) == 2


def _source_geometry_matches(
    result: JsonObject, expected_vertices: set[str], expected_faces: JSONValue
) -> bool:
    coordinates = result.get("coordinates_mm")
    faces = result.get("faces")
    if not isinstance(coordinates, list) or not isinstance(faces, list):
        return False
    if faces != expected_faces or not _point_labels_match(coordinates, expected_vertices):
        return False
    starts = result.get("starts")
    return isinstance(starts, list) and all(
        isinstance(start, dict)
        and isinstance(start.get("coordinates_mm"), list)
        and _point_labels_match(start["coordinates_mm"], expected_vertices)
        for start in starts
    )


def _point_labels_match(rows: JSONValue, expected_vertices: set[str]) -> bool:
    if not isinstance(rows, list):
        return False
    labels: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("attachment_location_id"), str):
            return False
        position = row.get("position_mm")
        if (
            not isinstance(position, list)
            or len(position) != 3
            or any(not _finite(value) for value in position)
        ):
            return False
        labels.append(cast(str, row["attachment_location_id"]))
    return len(labels) == len(set(labels)) and set(labels) == expected_vertices


def _transform(
    matrix: tuple[tuple[float, float, float, float], ...], point: list[float]
) -> list[float]:
    return [sum(matrix[i][j] * point[j] for j in range(3)) + matrix[i][3] for i in range(3)]


def _finite(value: object) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    if isinstance(value, int) and abs(value) > 9_007_199_254_740_991:
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def _json_object(value: JSONValue | None) -> JsonObject | None:
    return value if isinstance(value, dict) else None


def _native_number(value: JSONValue | None) -> float | None:
    return float(cast(int | float, value)) if _finite(value) else None


def _native_int(value: JsonObject | None, key: str) -> int | None:
    if value is None:
        return None
    member = value.get(key)
    return member if type(member) is int and 0 <= member <= 9_007_199_254_740_991 else None


def _nested_number(value: JsonObject, parent: str, key: str) -> float | None:
    nested = _json_object(value.get(parent))
    return None if nested is None else _native_number(nested.get(key))


def _digest(domain: bytes, encoded: bytes) -> str:
    return sha256(b"Crochet.AI\0" + domain + encoded).hexdigest()
