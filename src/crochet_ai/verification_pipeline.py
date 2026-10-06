"""Ordered, fail-closed V0-V10 verification orchestration (VERIFICATION_PIPELINE_V1)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Any

from .analytic_claims import AnalyticClaimsInputError, inspect_analytic_candidate_claims
from .analytic_coordinate_target import (
    VERSION as ANALYTIC_COORDINATE_TARGET_VERSION,
)
from .analytic_coordinate_target import (
    AnalyticCoordinateTarget,
)
from .analytic_target import VERSION as ANALYTIC_TARGET_VERSION
from .analytic_target import AnalyticTargetError, admit_analytic_target
from .analytic_trace_audit import bound_analytic_search_evidence, inspect_analytic_search_trace
from .backend_provenance import implementation_identity_hash
from .canonical import CanonicalProfile, canonical_hash, jcs_bytes, parse_json, validate_ijson
from .cell_conformance import CellConformanceInputError, inspect_closed_cell_conformance
from .diagnostics import ArtifactValidationError, Diagnostic, FailureCode
from .forward_closed_cells import ClosedCellsError, build_closed_surface_cells
from .json_types import JSONValue
from .models import DesignSpec, MaterialProfile
from .pattern import TerminologyProfile, export_pattern, verify_semantic_round_trip
from .pattern_context import PatternParseContext, PatternYarnBinding
from .physical_projection import PhysicalProjectionError, PhysicalSemanticProjection
from .prototype_final_relation import (
    PrototypeRelationInputError,
    inspect_prototype_final_relation,
    unique_original_proposal,
)
from .schema import validate_schema
from .surface_topology import SurfaceTopologyInputError, audit_surface_topology
from .trace_verification_types import TraceAuditInputError
from .v0_mesh_preflight import (
    V0MeshBudgets,
    V0MeshPreflightError,
    inspect_v0_mesh_v2,
)
from .validation import SemanticValidator

PIPELINE_ID = "VERIFICATION_PIPELINE_V1"
PIPELINE_VERSION = "1.0.0"
PROFILE_ID = "BACKEND_SEMANTIC_CHECKPOINT_V1"
PROFILE_VERSION = "1.0.0"
EVIDENCE_DOMAIN = b"Crochet.AI\x00VERIFICATION_GATE_EVIDENCE_V1\x00"
BUNDLE_DOMAIN = b"Crochet.AI\x00VERIFICATION_EVIDENCE_BUNDLE_V1\x00"
GATES = tuple(f"V{index}" for index in range(11))


class GateOutcome(StrEnum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    INDETERMINATE = "INDETERMINATE"
    NOT_RUN = "NOT_RUN"


class OverallState(StrEnum):
    REJECTED = "REJECTED"
    NOT_VERIFIED = "NOT_VERIFIED"
    EXPERIMENTAL = "EXPERIMENTAL"
    VERIFIED = "VERIFIED"


@dataclass(frozen=True, slots=True)
class VerificationProfile:
    profile_id: str
    version: str
    required_gates: tuple[str, ...]
    calibrated: bool
    permits_warnings: bool = False
    calibration_evidence_sha256: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.profile_id, str)
            or not self.profile_id
            or not isinstance(self.version, str)
            or not self.version
            or type(self.calibrated) is not bool
            or type(self.permits_warnings) is not bool
            or not self.required_gates
            or any(gate not in GATES for gate in self.required_gates)
            or tuple(sorted(set(self.required_gates), key=GATES.index)) != self.required_gates
        ):
            raise ValueError("profile gates must be nonempty, unique and ordered V0-V10")
        if self.calibration_evidence_sha256 is not None and not _valid_sha256(
            self.calibration_evidence_sha256
        ):
            raise ValueError("calibration evidence must be a SHA-256 hash")

    @property
    def content_hash(self) -> str:
        return _digest(
            b"Crochet.AI\0VERIFICATION_PROFILE_V1\0",
            {
                "profile_id": self.profile_id,
                "version": self.version,
                "required_gates": list(self.required_gates),
                "calibrated": self.calibrated,
                "permits_warnings": self.permits_warnings,
                "calibration_evidence_sha256": self.calibration_evidence_sha256,
            },
        )


BACKEND_SEMANTIC_CHECKPOINT_V1 = VerificationProfile(
    PROFILE_ID, PROFILE_VERSION, GATES, calibrated=False, permits_warnings=True
)


@dataclass(frozen=True, slots=True)
class GateResult:
    """Runner output; intentionally distinct from the immutable evidence record."""

    outcome: GateOutcome
    assertions: tuple[tuple[str, bool], ...] = ()
    diagnostics: tuple[Diagnostic, ...] = ()
    missing_checks: tuple[str, ...] = ()
    scope: str = ""
    telemetry: tuple[tuple[str, str], ...] = ()
    produced_artifact_hashes: tuple[tuple[str, str], ...] = ()
    threshold_profile_id: str = "NO_NUMERICAL_THRESHOLDS_V1"
    parameters_json: str = "{}"
    work_budget_json: str = "{}"
    metric_vector_json: str = "[]"
    linked_evidence_json: str = "{}"


@dataclass(frozen=True, slots=True)
class GateEvidence:
    gate_id: str
    implementation_version: str
    outcome: GateOutcome
    input_hashes: tuple[tuple[str, str], ...]
    verification_profile_id: str
    verification_profile_version: str
    verification_profile_hash: str
    assertions: tuple[tuple[str, bool], ...]
    diagnostics: tuple[str, ...]
    missing_checks: tuple[str, ...]
    scope: str
    evidence_hash: str
    telemetry: tuple[tuple[str, str], ...] = ()
    produced_artifact_hashes: tuple[tuple[str, str], ...] = ()
    threshold_profile_id: str = "NO_NUMERICAL_THRESHOLDS_V1"
    parameters_json: str = "{}"
    work_budget_json: str = "{}"
    metric_vector_json: str = "[]"
    linked_evidence_json: str = "{}"

    def canonical_payload(self) -> dict[str, JSONValue]:
        return {
            "gate_id": self.gate_id,
            "implementation_version": self.implementation_version,
            "outcome": self.outcome.value,
            "input_hashes": {key: value for key, value in self.input_hashes},
            "verification_profile_id": self.verification_profile_id,
            "verification_profile_version": self.verification_profile_version,
            "verification_profile_hash": self.verification_profile_hash,
            "assertions": [[name, value] for name, value in self.assertions],
            "assertion_counts": {
                "passed": sum(result for _, result in self.assertions),
                "failed": sum(not result for _, result in self.assertions),
            },
            "threshold_profile_id": self.threshold_profile_id,
            "parameters": parse_json(self.parameters_json),
            "work_budget": parse_json(self.work_budget_json),
            "random_seed": None,
            "metric_vector": parse_json(self.metric_vector_json),
            "linked_evidence": parse_json(self.linked_evidence_json),
            "produced_artifact_hashes": dict(self.produced_artifact_hashes),
            "diagnostics": [parse_json(item) for item in self.diagnostics],
            "missing_checks": list(self.missing_checks),
            "scope": self.scope,
        }

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            **self.canonical_payload(),
            "evidence_hash": self.evidence_hash,
            "telemetry": {key: value for key, value in self.telemetry},
        }


@dataclass(frozen=True, slots=True)
class VerificationResult:
    pipeline_id: str
    pipeline_version: str
    profile_id: str
    profile_version: str
    overall_state: OverallState
    physical_validation_status: str
    input_hashes: tuple[tuple[str, str], ...]
    gates: tuple[GateEvidence, ...]
    evidence_bundle_hash: str

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "pipeline_id": self.pipeline_id,
            "pipeline_version": self.pipeline_version,
            "verification_profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "verification_state": self.overall_state.value,
            "physical_status": self.physical_validation_status,
            "input_hashes": dict(self.input_hashes),
            "gates": [gate.to_dict() for gate in self.gates],
            "evidence_bundle_sha256": self.evidence_bundle_hash,
        }


Runner = Callable[[], GateResult]


def _digest(domain: bytes, value: Mapping[str, JSONValue]) -> str:
    return sha256(domain + jcs_bytes(dict(value))).hexdigest()


def evidence_is_valid(evidence: GateEvidence) -> bool:
    """Validate canonical digest and internal evidence invariants on resumed records."""
    try:
        payload = evidence.canonical_payload()
        return (
            evidence.gate_id in GATES
            and isinstance(evidence.input_hashes, tuple)
            and isinstance(evidence.assertions, tuple)
            and all(isinstance(item, tuple) for item in evidence.assertions)
            and isinstance(evidence.outcome, GateOutcome)
            and _valid_sha256(evidence.verification_profile_hash)
            and tuple(sorted(evidence.input_hashes)) == evidence.input_hashes
            and len(dict(evidence.input_hashes)) == len(evidence.input_hashes)
            and len(dict(evidence.produced_artifact_hashes))
            == len(evidence.produced_artifact_hashes)
            and all(_valid_sha256(value) for _, value in evidence.produced_artifact_hashes)
            and all(_valid_sha256(value) for _, value in evidence.input_hashes)
            and _digest(EVIDENCE_DOMAIN, payload) == evidence.evidence_hash
            and len(dict(evidence.assertions)) == len(evidence.assertions)
            and all(isinstance(value, bool) for _, value in evidence.assertions)
            and (evidence.outcome is not GateOutcome.PASS or not evidence.missing_checks)
            and (evidence.outcome is not GateOutcome.PASS or all(v for _, v in evidence.assertions))
            and (evidence.outcome is not GateOutcome.PASS or bool(evidence.assertions))
            and (evidence.outcome is not GateOutcome.FAIL or bool(evidence.diagnostics))
        )
    except (TypeError, ValueError):
        return False


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _make_evidence(
    gate_id: str,
    result: GateResult,
    input_hashes: tuple[tuple[str, str], ...],
    profile: VerificationProfile,
    implementation_version: str,
) -> GateEvidence:
    diagnostics = tuple(
        sorted(jcs_bytes(_diagnostic_payload(item)).decode("utf-8") for item in result.diagnostics)
    )
    partial = GateEvidence(
        gate_id,
        implementation_version,
        result.outcome,
        input_hashes,
        profile.profile_id,
        profile.version,
        profile.content_hash,
        tuple(sorted((name, value) for name, value in result.assertions)),
        diagnostics,
        tuple(sorted(result.missing_checks)),
        result.scope,
        "",
        tuple(sorted(result.telemetry)),
        tuple(sorted(result.produced_artifact_hashes)),
        result.threshold_profile_id,
        result.parameters_json,
        result.work_budget_json,
        result.metric_vector_json,
        result.linked_evidence_json,
    )
    evidence = GateEvidence(
        **{
            name: getattr(partial, name)
            for name in partial.__dataclass_fields__
            if name != "evidence_hash"
        },
        evidence_hash=_digest(EVIDENCE_DOMAIN, partial.canonical_payload()),
    )
    if not evidence_is_valid(evidence):
        raise ValueError(f"invalid runner evidence for {gate_id}")
    return evidence


def _diagnostic_payload(item: Diagnostic) -> dict[str, JSONValue]:
    # The JSON boundary preserves locations and reproducibility rather than reducing to prose.
    payload: dict[str, JSONValue] = {
        "code": item.code.value,
        "gate": item.gate,
        "message_key": item.message_key,
        "diagnostic_id": item.diagnostic_id,
        "severity": item.severity,
        "summary": item.summary,
        "artifact_hash": item.artifact_hash,
        "entity_refs": list(item.entity_refs),
        "json_pointers": list(item.json_pointers),
        "expected": _diagnostic_json(item.expected),
        "observed": _diagnostic_json(item.observed),
        "units": item.units,
        "tolerance_profile_id": item.tolerance_profile_id,
        "implementation_version": item.implementation_version,
        "cause_ids": list(item.cause_ids),
        "reproducibility": _diagnostic_json(item.reproducibility),
    }
    value = parse_json(jcs_bytes(payload))
    if not isinstance(value, dict):
        raise ValueError("diagnostic must be a JSON object")
    return value


def _diagnostic_json(value: object) -> JSONValue:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("diagnostic keys must be strings")
        return {key: _diagnostic_json(child) for key, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [_diagnostic_json(child) for child in value]
    raise ValueError("diagnostic value is not representable as JSON")


def _classify(evidence: Sequence[GateEvidence], profile: VerificationProfile) -> OverallState:
    required = [record for record in evidence if record.gate_id in profile.required_gates]
    if any(record.outcome is GateOutcome.FAIL for record in required):
        return OverallState.REJECTED
    if any(
        record.outcome in {GateOutcome.NOT_RUN, GateOutcome.INDETERMINATE} for record in required
    ):
        return OverallState.NOT_VERIFIED
    if len(required) != len(profile.required_gates):
        return OverallState.NOT_VERIFIED
    if any(record.outcome is GateOutcome.WARNING for record in required):
        return OverallState.EXPERIMENTAL if profile.permits_warnings else OverallState.NOT_VERIFIED
    if (
        profile.calibrated
        and profile.calibration_evidence_sha256 is not None
        and "V10" in profile.required_gates
        and all(record.implementation_version != "unversioned" for record in required)
        and all(record.outcome is GateOutcome.PASS for record in required)
    ):
        return OverallState.VERIFIED
    return OverallState.EXPERIMENTAL


def verify_runners(
    *,
    input_hashes: Mapping[str, str],
    runners: Mapping[str, Runner],
    profile: VerificationProfile = BACKEND_SEMANTIC_CHECKPOINT_V1,
    diagnostic_mode: bool = False,
    implementation_versions: Mapping[str, str] | None = None,
    resumed_evidence: tuple[GateEvidence, ...] = (),
) -> VerificationResult:
    """Run registered gates in V0-V10 order and hash immutable results."""
    if {"prior_gate_evidence", "implementation_identity"} & set(input_hashes):
        raise ValueError("reserved hash name in orchestration inputs")
    if not input_hashes or not all(_valid_sha256(value) for value in input_hashes.values()):
        raise ValueError("input hashes must be lowercase SHA-256 hex digests")
    ordered_hashes = tuple(
        sorted({**input_hashes, "implementation_identity": implementation_identity_hash()}.items())
    )
    if any(gate not in GATES for gate in profile.required_gates):
        raise ValueError("profile contains an unsupported gate")
    if (
        not profile.required_gates
        or not profile.profile_id
        or not profile.version
        or tuple(sorted(set(profile.required_gates), key=GATES.index)) != profile.required_gates
    ):
        raise ValueError("profile gates must be nonempty, unique and ordered V0-V10")

    evidence: list[GateEvidence] = []
    stopped = False
    versions = implementation_versions or {}
    if resumed_evidence and not validate_resumed_evidence(
        resumed_evidence,
        expected_input_hashes=input_hashes,
        profile=profile,
        implementation_versions=versions,
    ):
        raise ValueError("resumed evidence binding or integrity mismatch")
    resumed = {record.gate_id: record for record in resumed_evidence}
    for gate in GATES:
        if gate not in profile.required_gates:
            continue
        prior_hashes = dict(ordered_hashes)
        if evidence:
            prior_hashes["prior_gate_evidence"] = evidence[-1].evidence_hash
        if gate in resumed:
            record = resumed[gate]
            if stopped and not diagnostic_mode and record.outcome is not GateOutcome.NOT_RUN:
                raise ValueError("resumed success after mandatory failure")
            evidence.append(record)
            stopped = stopped or record.outcome is GateOutcome.FAIL
            continue
        if gate not in runners:
            result = GateResult(GateOutcome.NOT_RUN, missing_checks=("runner unavailable",))
        elif stopped and not diagnostic_mode:
            result = GateResult(
                GateOutcome.NOT_RUN, missing_checks=("blocked by prior mandatory failure",)
            )
        else:
            result = runners[gate]()
        record = _make_evidence(
            gate,
            result,
            tuple(sorted(prior_hashes.items())),
            profile,
            versions.get(gate, "unversioned"),
        )
        evidence.append(record)
        if result.outcome is GateOutcome.FAIL:
            stopped = True
    records = tuple(evidence)
    bundle_payload: dict[str, JSONValue] = {
        "pipeline_id": PIPELINE_ID,
        "pipeline_version": PIPELINE_VERSION,
        "profile_id": profile.profile_id,
        "profile_version": profile.version,
        "profile_hash": profile.content_hash,
        "input_hashes": {key: value for key, value in ordered_hashes},
        "gates": [
            record.canonical_payload() | {"evidence_hash": record.evidence_hash}
            for record in records
        ],
    }
    return VerificationResult(
        PIPELINE_ID,
        PIPELINE_VERSION,
        profile.profile_id,
        profile.version,
        _classify(records, profile),
        "UNTESTED",
        ordered_hashes,
        records,
        _digest(BUNDLE_DOMAIN, bundle_payload),
    )


def validate_resumed_evidence(
    records: Sequence[GateEvidence],
    *,
    expected_input_hashes: Mapping[str, str],
    profile: VerificationProfile,
    implementation_versions: Mapping[str, str],
) -> bool:
    """Reject reordered, stale, changed-profile, changed-implementation, or tampered evidence."""
    if {"prior_gate_evidence", "implementation_identity"} & set(expected_input_hashes):
        return False
    expected = tuple(
        sorted(
            {
                **expected_input_hashes,
                "implementation_identity": implementation_identity_hash(),
            }.items()
        )
    )
    if not all(_valid_sha256(value) for _, value in expected):
        return False
    gate_ids = tuple(record.gate_id for record in records)
    if gate_ids != profile.required_gates[: len(records)]:
        return False
    prior: GateEvidence | None = None
    for record in records:
        inputs = dict(expected)
        if prior is not None:
            inputs["prior_gate_evidence"] = prior.evidence_hash
        if not (
            evidence_is_valid(record)
            and record.input_hashes == tuple(sorted(inputs.items()))
            and record.verification_profile_id == profile.profile_id
            and record.verification_profile_version == profile.version
            and record.verification_profile_hash == profile.content_hash
            and record.implementation_version != "unversioned"
            and record.implementation_version == implementation_versions.get(record.gate_id)
        ):
            return False
        prior = record
    return True


def _diagnostics_for(report: Sequence[Diagnostic], gate: str) -> tuple[Diagnostic, ...]:
    return tuple(item for item in report if item.gate == gate)


def _report_result(diagnostics: Sequence[Diagnostic], *, scope: str) -> GateResult:
    return GateResult(
        GateOutcome.FAIL if diagnostics else GateOutcome.PASS,
        assertions=((scope, not diagnostics),),
        diagnostics=tuple(diagnostics),
        scope=scope,
    )


def verify_artifacts(
    design_spec: Mapping[str, Any],
    material_profile: Mapping[str, Any],
    crochet_ir: Mapping[str, Any],
    *,
    mesh_json: bytes | None = None,
    mesh_budgets: V0MeshBudgets | None = None,
    diagnostic_mode: bool = False,
    search_evidence: Mapping[str, Any] | None = None,
    profile: VerificationProfile = BACKEND_SEMANTIC_CHECKPOINT_V1,
) -> VerificationResult:
    """Adapt existing V0/V1/V2-V4 validators; future gates remain explicitly unavailable."""
    design = dict(design_spec)
    material = dict(material_profile)
    ir = dict(crochet_ir)
    for artifact in (design, material, ir):
        validate_ijson(artifact)
    material_schema = validate_schema("material_profile", material)
    validator = SemanticValidator(
        material_profiles={material["profile_id"]: material} if material_schema.ok else {},
        design_specs={design["design_spec_id"]: design}
        if validate_schema("design_spec", design).ok
        else {},
    )
    hashes = {
        "design_spec": _artifact_hash(design, CanonicalProfile.DESIGN_SPEC, validator),
        "material_profile": _artifact_hash(material, CanonicalProfile.MATERIAL_PROFILE, validator),
        "crochet_ir": _artifact_hash(ir, CanonicalProfile.CROCHET_IR, validator),
    }
    if search_evidence is not None:
        search_evidence = bound_analytic_search_evidence(search_evidence)
        hashes["analytic_search_evidence"] = _digest(
            b"Crochet.AI\0ANALYTIC_SEARCH_EVIDENCE_V1\0", dict(search_evidence)
        )
    if mesh_json is not None:
        hashes["raw_mesh"] = sha256(mesh_json).hexdigest()
    if mesh_budgets is not None:
        hashes["mesh_budgets"] = _digest(b"Crochet.AI\0V0_BUDGETS_V1\0", asdict(mesh_budgets))
    design_model: DesignSpec | None = None
    material_model: MaterialProfile | None = None
    design_report = validator.validate_design_spec(design)
    material_report = validator.validate_material_profile(material)
    if design_report.ok:
        design_model = DesignSpec.from_dict(design)
    if material_report.ok:
        material_model = MaterialProfile.from_dict(material)
    design_schema = validate_schema("design_spec", design)
    coordinate_target_scope = (
        design_schema.ok
        and design.get("target_geometry", {}).get("radial_profile", {}).get(
            "canonicalization_profile"
        ) == "SURFACE_OF_REVOLUTION_COORDINATE_PROFILE_CANONICAL_JSON_V1"
    )

    runners: dict[str, Runner] = {}
    if (
        mesh_json is not None
        and mesh_budgets is not None
        and design_model is not None
        and material_model is not None
    ):

        def run_v0() -> GateResult:
            try:
                result = inspect_v0_mesh_v2(
                    design_model, mesh_json, material_profile=material_model, budgets=mesh_budgets
                )
            except V0MeshPreflightError as error:
                outcome = GateOutcome.FAIL if error.outcome == "FAIL" else GateOutcome.INDETERMINATE
                return GateResult(
                    outcome,
                    diagnostics=(
                        Diagnostic(
                            FailureCode(error.code),
                            "V0",
                            error.reason,
                            "Mesh preflight did not establish admission",
                            hashes["raw_mesh"],
                            implementation_version="v0-mesh-adapter/1.0.0",
                        ),
                    ),
                    missing_checks=(error.reason,) if outcome is GateOutcome.INDETERMINATE else (),
                    scope="V0 mesh preflight",
                )
            return GateResult(
                GateOutcome(result.outcome),
                assertions=(("supported_mesh_preflight", True),),
                scope=f"V0 {result.domain_profile_id}; {result.implementation_version}",
                produced_artifact_hashes=(
                    ("normalized_mesh", result.normalized_mesh_sha256),
                    ("v0_preflight_evidence", result.evidence_sha256),
                ),
                threshold_profile_id=result.numerical_profile_id,
                parameters_json=jcs_bytes(
                    {
                        "domain_profile_id": result.domain_profile_id,
                        "numerical_profile_id": result.numerical_profile_id,
                        "numerical_profile_version": result.numerical_profile_version,
                        "numerical_profile_sha256": result.numerical_profile_sha256,
                    }
                ).decode("utf-8"),
                work_budget_json=jcs_bytes(asdict(mesh_budgets)).decode("utf-8"),
                metric_vector_json=jcs_bytes(
                    [list(item) for item in result.metric_evidence]
                ).decode("utf-8"),
                linked_evidence_json=jcs_bytes(_diagnostic_json(asdict(result))).decode("utf-8"),
            )

        runners["V0"] = run_v0
    elif (
        mesh_json is None
        and material_model is not None
        and (design_model is not None or coordinate_target_scope)
        and design["target_geometry"]["geometry_type"] == "ANALYTIC_SHAPE"
    ):

        def run_analytic_v0() -> GateResult:
            try:
                target = admit_analytic_target(design, validator)
            except AnalyticTargetError as error:
                outcome = (
                    GateOutcome.INDETERMINATE
                    if error.status == "NOT_APPLICABLE"
                    else GateOutcome.FAIL
                    if coordinate_target_scope
                    else GateOutcome.INDETERMINATE
                )
                return GateResult(
                    outcome,
                    diagnostics=(
                        Diagnostic(
                            FailureCode.UNSUPPORTED_FEATURE
                            if error.status == "NOT_APPLICABLE"
                            else FailureCode.INPUT,
                            "V0",
                            "analytic_target.admission_unavailable",
                            error.reason,
                            hashes["design_spec"],
                            implementation_version=(
                                "analytic-coordinate-target-adapter/1.0.0"
                                if coordinate_target_scope
                                else "analytic-target-adapter/1.0.0"
                            ),
                        ),
                    ),
                    missing_checks=(error.reason,),
                    scope="Analytic target admission did not establish V0",
                )
            if isinstance(target, AnalyticCoordinateTarget):
                return GateResult(
                    GateOutcome.PASS,
                    assertions=(
                        ("simple_exact_meridian_polyline", True),
                        ("closed_distinct_pole_ended_surface", True),
                        ("finite_distinct_cardinal_knot_witnesses", True),
                    ),
                    scope=(
                        "Ideal closed explicit-coordinate surface of revolution; "
                        "no sampled mesh or V7 certificate"
                    ),
                    produced_artifact_hashes=(("analytic_coordinate_target", target.sha256),),
                    threshold_profile_id=ANALYTIC_COORDINATE_TARGET_VERSION,
                    parameters_json=jcs_bytes(
                        {
                            "representation_version": ANALYTIC_COORDINATE_TARGET_VERSION,
                            "domain_profile_id": "V0_ANALYTIC_COORDINATE_TARGET_V1",
                        }
                    ).decode(),
                    work_budget_json=jcs_bytes(
                        {
                            "max_knots": 129,
                            "maximum_segment_pairs": 8_128,
                            "segment_pair_limit": target.segment_pair_limit,
                            "segment_pair_checks": target.segment_pair_checks,
                            "finite_distinct_cardinal_witness_count": 2
                            + 4 * (len(target.coordinates_mm) - 2),
                        }
                    ).decode(),
                    metric_vector_json=jcs_bytes(
                        [
                            ["ideal_component_count", 1],
                            ["ideal_boundary_count", 0],
                            ["ideal_genus", 0],
                        ]
                    ).decode(),
                    linked_evidence_json=jcs_bytes(target.to_dict()).decode(),
                )
            return GateResult(
                GateOutcome.PASS,
                assertions=(
                    ("unambiguous_analytic_primitive", True),
                    ("positive_finite_semiaxes_and_extent", True),
                    ("finite_distinct_cardinal_positions", True),
                    ("closed_regular_ideal_surface", True),
                ),
                scope=(
                    "Ideal closed SPHERE/ELLIPSOID target; not CrochetIR or sampled mesh topology"
                ),
                produced_artifact_hashes=(("analytic_target", target.sha256),),
                threshold_profile_id="ANALYTIC_REGULAR_PRIMITIVES_V1",
                parameters_json=jcs_bytes(
                    {
                        "representation_version": ANALYTIC_TARGET_VERSION,
                        "domain_profile_id": "V0_ANALYTIC_SHAPE_V1",
                    }
                ).decode(),
                work_budget_json=jcs_bytes({"cardinal_predicate_points": 6}).decode(),
                metric_vector_json=jcs_bytes(
                    [["ideal_component_count", 1], ["ideal_boundary_count", 0], ["ideal_genus", 0]]
                ).decode(),
                linked_evidence_json=jcs_bytes(target.to_dict()).decode(),
            )

        runners["V0"] = run_analytic_v0
    else:
        runners["V0"] = lambda: GateResult(
            GateOutcome.INDETERMINATE,
            missing_checks=("supported raw mesh and V0 budgets unavailable",),
            scope="No analytic geometry preflight is inferred",
        )

    runners["V1"] = lambda: _report_result(
        (*design_schema.diagnostics, *design_report.diagnostics, *material_report.diagnostics),
        scope="DesignSpec schema and SemanticValidator V1 constraints",
    )

    ir_schema = validate_schema("crochet_ir", ir)
    semantic = validator.validate_crochet_ir(ir, design if not design_report.diagnostics else None)
    for gate in ("V2", "V3"):
        schema_errors = ir_schema.diagnostics if not ir_schema.ok else ()
        diagnostics: tuple[Diagnostic, ...] = (
            tuple(schema_errors) if schema_errors else _diagnostics_for(semantic.diagnostics, gate)
        )

        def gate_runner(
            diagnostics: tuple[Diagnostic, ...] = diagnostics, gate_id: str = gate
        ) -> GateResult:
            if gate_id == "V3" and not ir_schema.ok:
                return GateResult(
                    GateOutcome.NOT_RUN, missing_checks=("CrochetIR schema prerequisite failed",)
                )
            return _report_result(
                diagnostics,
                scope=f"Bundled SemanticValidator single pass; diagnostics attributed to {gate_id}",
            )

        runners[gate] = gate_runner
    v4_diagnostics = _diagnostics_for(semantic.diagnostics, "V4")
    v4_passed = False

    def v4_runner() -> GateResult:
        nonlocal v4_passed
        if not ir_schema.ok:
            return GateResult(
                GateOutcome.NOT_RUN, missing_checks=("CrochetIR schema prerequisite failed",)
            )
        if v4_diagnostics:
            return GateResult(GateOutcome.FAIL, diagnostics=v4_diagnostics)
        if not semantic.ok or not design_report.ok or not material_report.ok:
            return GateResult(
                GateOutcome.NOT_RUN,
                missing_checks=("surface audit source prerequisites did not pass",),
            )
        try:
            projection = PhysicalSemanticProjection(ir, material, validator=validator)
            cells = build_closed_surface_cells(projection)
        except (ClosedCellsError, PhysicalProjectionError, ArtifactValidationError) as error:
            return GateResult(
                GateOutcome.INDETERMINATE,
                missing_checks=("supported closed surface unavailable: " + str(error),),
                scope="No independent surface audit for unsupported construction",
            )
        surface = cells.to_dict()
        try:
            audit = audit_surface_topology(surface["vertices"], surface["faces"])
        except SurfaceTopologyInputError as error:
            return GateResult(
                GateOutcome.FAIL,
                diagnostics=(
                    Diagnostic(
                        FailureCode.TOPOLOGY,
                        "V4",
                        "surface_topology.invalid_generated_complex",
                        str(error),
                        cells.sha256,
                        implementation_version="surface-topology-adapter/1.0.0",
                    ),
                ),
            )
        audit_data = audit.to_dict()
        try:
            conformance = inspect_closed_cell_conformance(
                ir, surface, validator=validator,
                projection_sha256=projection.sha256, surface_cells_sha256=cells.sha256,
            )
        except CellConformanceInputError as error:
            if str(error) in {
                "cell_conformance.event_budget_exceeded",
                "cell_conformance.source_table_budget_exceeded",
                "cell_conformance.source_identifier_budget_exceeded",
                "cell_conformance.vertex_budget_exceeded",
                "cell_conformance.face_budget_exceeded",
            }:
                return GateResult(
                    GateOutcome.INDETERMINATE,
                    missing_checks=("source-cell proof budget exhausted: " + str(error),),
                    scope="No completed source-cell proof within the declared work limits",
                )
            return GateResult(
                GateOutcome.FAIL,
                diagnostics=(Diagnostic(
                    FailureCode.TOPOLOGY, "V4", "cell_conformance.invalid_generated_complex",
                    str(error), cells.sha256,
                    implementation_version="closed-cell-source-adapter/1.0.0",
                ),),
            )
        conformance_data = conformance.to_dict()
        diagnostics = tuple(
            Diagnostic(
                FailureCode.TOPOLOGY,
                "V4",
                reason,
                "Independent combinatorial surface topology check failed",
                cells.sha256,
                implementation_version="surface-topology-adapter/1.0.0",
            )
            for reason in audit.diagnostics
        )
        diagnostics += tuple(
            Diagnostic(
                FailureCode.TOPOLOGY, "V4", reason,
                "Independent CrochetIR-to-cell conformance check failed", cells.sha256,
                implementation_version="closed-cell-source-adapter/1.0.0",
            )
            for reason in conformance.diagnostics if conformance.status == "FAIL"
        )
        supported_design = design["project_type"] == "AMIGURUMI_3D"
        required = design["target_geometry"].get("topology_expectation")
        requested_topology = supported_design and (
            design["domain_constraints"]["surface_mode"] == "CLOSED"
            and (required is None or (
                required["expected_connected_components"] == audit.components
                and required["expected_boundary_components"] == 0
            ))
        )
        if supported_design and not requested_topology:
            diagnostics += (Diagnostic(
                FailureCode.TOPOLOGY, "V4", "cell_conformance.design_topology_mismatch",
                "Generated closed surface does not match the requested topology", cells.sha256,
                implementation_version="closed-cell-source-adapter/1.0.0",
            ),)
        complete = audit.status == "PASS" and conformance.status == "PASS" and requested_topology
        v4_passed = complete and not diagnostics
        return GateResult(
            GateOutcome.FAIL if diagnostics else (
                GateOutcome.PASS if complete else GateOutcome.INDETERMINATE
            ),
            assertions=(
                ("closed_surface_topology", audit.status == "PASS"),
                ("source_cell_conformance", conformance.status == "PASS"),
                ("requested_topology", requested_topology),
            ),
            diagnostics=diagnostics,
            missing_checks=() if complete or diagnostics else (
                "closed single-component SC amigurumi source/design scope unsupported",
            ),
            scope="Independent closed single-component SC amigurumi topology and source-cell proof",
            produced_artifact_hashes=(
                ("physical_projection", projection.sha256),
                ("closed_surface_cells", cells.sha256),
                ("surface_topology_audit", audit.sha256),
                ("cell_source_conformance", conformance.sha256),
            ),
            threshold_profile_id="EXACT_COMBINATORIAL_SPHERE_V1",
            work_budget_json=jcs_bytes({
                "surface_audit": audit_data["budgets"],
                "cell_conformance": conformance_data["budgets"],
            }).decode(),
            metric_vector_json=jcs_bytes(
                [
                    {
                        "metric": "components",
                        "value": audit.components,
                        "required": 1,
                        "units": "count",
                    },
                    {
                        "metric": "euler_characteristic",
                        "value": audit.euler_characteristic,
                        "required": 2,
                        "units": "dimensionless",
                    },
                ]
            ).decode(),
            linked_evidence_json=jcs_bytes({
                "surface_topology": audit_data, "cell_conformance": conformance_data,
            }).decode(),
        )

    runners["V4"] = v4_runner

    def unavailable_runner() -> GateResult:
        return GateResult(
            GateOutcome.NOT_RUN,
            missing_checks=("runner unavailable in this checkpoint",),
            scope="No implementation registered",
        )

    for gate in (f"V{index}" for index in range(5, 11)):
        runners[gate] = unavailable_runner

    def v5_runner() -> GateResult:
        if not semantic.ok or not design_report.ok or not material_report.ok or not v4_passed:
            return GateResult(
                GateOutcome.NOT_RUN, missing_checks=("V1-V4 prerequisites did not all pass",),
            )
        try:
            claims = inspect_analytic_candidate_claims(design, material, ir, validator=validator)
        except AnalyticClaimsInputError as error:
            if "budget_exceeded" in str(error) or "resource_ceiling_exceeded" in str(error):
                return GateResult(
                    GateOutcome.INDETERMINATE,
                    missing_checks=("candidate-claims proof budget exhausted: " + str(error),),
                )
            return GateResult(
                GateOutcome.FAIL,
                diagnostics=(Diagnostic(
                    FailureCode.INPUT, "V5", "candidate_claims.invalid_input", str(error),
                    hashes["crochet_ir"], implementation_version="analytic-claims-adapter/1.0.0",
                ),),
            )
        claims_data = claims.to_dict()
        diagnostics = tuple(Diagnostic(
            FailureCode(code), "V5", reason, "Independent candidate claim check failed",
            hashes["crochet_ir"], implementation_version="analytic-claims-adapter/1.0.0",
        ) for code, reason in claims.diagnostics)
        assertions = claims.assertions
        missing_checks = claims.missing_checks
        produced_hashes: tuple[tuple[str, str], ...] = (
            ("analytic_candidate_claims", claims.sha256),
        )
        evidence_data: dict[str, Any] = claims_data
        trace_failed = False
        relation_data: dict[str, Any] | None = None
        relation_failed = False
        if search_evidence is not None:
            try:
                trace_audit = inspect_analytic_search_trace(
                    design, material, search_evidence["run_config"],
                    search_evidence["search_trace"],
                    search_evidence["candidate_proposals"], validator=validator,
                )
            except (TraceAuditInputError, AnalyticClaimsInputError) as error:
                return GateResult(
                    GateOutcome.FAIL, diagnostics=(Diagnostic(
                        FailureCode.INPUT, "V5", "search_trace.invalid_input", str(error),
                        hashes["crochet_ir"], implementation_version="analytic-trace-adapter/1.0.0",
                    ),),
                )
            evidence_data = {"candidate_claims": claims_data, "search_audit": trace_audit.to_dict()}
            assertions += tuple(("search." + key, value) for key, value in trace_audit.assertions)
            produced_hashes += (("analytic_search_audit", trace_audit.sha256),)
            diagnostics += tuple(Diagnostic(
                FailureCode(code), "V5", reason, "Independent search trace check failed",
                hashes["crochet_ir"], implementation_version="analytic-trace-adapter/1.0.0",
            ) for code, reason in trace_audit.diagnostics)
            trace_failed = trace_audit.status == "FAIL"
            missing_checks += trace_audit.missing_checks
            if trace_audit.status == "PASS":
                confirmed = {
                    "input_bound_search_trace",
                    "independently_confirmed_search_work_and_completion",
                    "count_window_admission", "global_phase_optimality",
                }
                missing_checks = tuple(item for item in missing_checks if item not in confirmed)
                proposal_hashes = search_evidence["search_trace"]["terminal"]["proposal_ir_sha256"]
                native = not any(
                    row["name"].startswith("prototype.")
                    for row in ir["provenance"]["solver_parameters"]
                )
                if native:
                    member = hashes["crochet_ir"] in proposal_hashes
                    assertions += (("search.candidate_is_emitted_proposal", member),)
                    if not member:
                        trace_failed = True
                        diagnostics += (Diagnostic(
                            FailureCode.DETERMINISM, "V5", "search_trace.candidate_not_emitted",
                            "Candidate is absent from the independently audited proposal batch",
                            hashes["crochet_ir"],
                            implementation_version="analytic-trace-adapter/1.0.0",
                        ),)
                else:
                    if "final_candidate_to_original_proposal_relation" not in missing_checks:
                        missing_checks += ("final_candidate_to_original_proposal_relation",)
                    original = unique_original_proposal(ir, search_evidence["candidate_proposals"])
                    if original is None:
                        missing_checks += (
                            "final_candidate_to_original_proposal_relation: "
                            "native_lineage_not_unique_or_not_found",
                        )
                    else:
                        try:
                            relation = inspect_prototype_final_relation(
                                design,
                                material,
                                original,
                                ir,
                                validator=validator,
                            )
                            relation_data = relation.to_dict()
                            produced_hashes += (("prototype_final_relation", relation.sha256),)
                            assertions += tuple(
                                ("relation." + key, value)
                                for key, value in relation_data["assertions"].items()
                            )
                            diagnostics += tuple(
                                Diagnostic(
                                    FailureCode(row["code"]),
                                    "V5",
                                    "prototype_relation." + row["code"].lower(),
                                    row["reason"],
                                    hashes["crochet_ir"],
                                    implementation_version="prototype-final-relation-adapter/1.0.0",
                                )
                                for row in relation_data["diagnostics"]
                            )
                            relation_failed = relation.status == "FAIL"
                            if relation.status == "PASS":
                                missing_checks = tuple(
                                    item
                                    for item in missing_checks
                                    if item != "final_candidate_to_original_proposal_relation"
                                )
                        except (
                            PrototypeRelationInputError,
                            AnalyticClaimsInputError,
                            ArtifactValidationError,
                        ) as error:
                            missing_checks += (
                                "final_candidate_to_original_proposal_relation: " + str(error),
                            )
                if relation_data is not None:
                    evidence_data["final_relation"] = relation_data
        return GateResult(
            GateOutcome.FAIL
            if claims.status == "FAIL" or trace_failed or relation_failed
            else GateOutcome.INDETERMINATE,
            assertions=assertions,
            diagnostics=diagnostics,
            missing_checks=missing_checks,
            scope=(
                "Independent analytic schedule and bounded staged search; "
                "physical selection remains open"
                + ("; final-relation audit linked" if relation_data is not None else "")
            )
            if search_evidence is not None
            else "Independent analytic schedule and bounds; complete search trace unavailable",
            produced_artifact_hashes=produced_hashes,
            threshold_profile_id=(
                "EXACT_ANALYTIC_SCHEDULE_CLAIMS_V1"
                if search_evidence is None
                else "EXACT_ANALYTIC_TRACE_AUDIT_V1"
                + ("+PROTOTYPE_FINAL_RELATION_AUDIT_V1" if relation_data is not None else "")
            ),
            work_budget_json=jcs_bytes(
                claims_data["budgets"]
                if search_evidence is None
                else {
                    "candidate_claims": claims_data["budgets"],
                    "search_audit": evidence_data["search_audit"]["budgets"],
                    **(
                        {"final_relation": relation_data["budgets"]}
                        if relation_data is not None
                        else {}
                    ),
                }
            ).decode(),
            parameters_json=jcs_bytes(claims_data["checked_parameters"]).decode(),
            linked_evidence_json=jcs_bytes(evidence_data).decode(),
        )

    runners["V5"] = v5_runner

    def v9_runner() -> GateResult:
        if not semantic.ok:
            return GateResult(
                GateOutcome.NOT_RUN, missing_checks=("semantic source validation did not pass",)
            )
        if len(ir["yarns"]) != 1:
            return GateResult(
                GateOutcome.NOT_RUN, missing_checks=("multi-yarn V9 adapter not implemented",)
            )
        yarn = ir["yarns"][0]
        color = next(item for item in ir["colors"] if item["color_id"] == yarn["color_id"])
        context = PatternParseContext(
            design, (PatternYarnBinding("Yarn A", material, color["label"], color["srgb_hex"]),)
        )
        diagnostics: list[Diagnostic] = []
        assertions: list[tuple[str, bool]] = []
        produced: list[tuple[str, str]] = []
        for terminology in TerminologyProfile:
            report = verify_semantic_round_trip(
                ir, terminology, context=context, validator=validator
            )
            diagnostics.extend(report.diagnostics)
            assertions.append((f"semantic_round_trip.{terminology.value}", report.ok))
            if report.ok:
                text = export_pattern(ir, terminology, validator=validator)
                produced.append(
                    (f"pattern_text.{terminology.value}", sha256(text.encode("utf-8")).hexdigest())
                )
        return GateResult(
            GateOutcome.FAIL if diagnostics else GateOutcome.PASS,
            assertions=tuple(assertions),
            diagnostics=tuple(diagnostics),
            scope="Single-yarn M1A text DE/US/UK; separate parser and frozen metadata linker",
            produced_artifact_hashes=tuple(produced),
        )

    runners["V9"] = v9_runner
    return verify_runners(
        input_hashes=hashes,
        runners=runners,
        profile=profile,
        diagnostic_mode=diagnostic_mode,
        implementation_versions={
            gate: (
                "analytic-coordinate-target-adapter/1.0.0"
                if coordinate_target_scope
                else "target-adapter/1.1.0"
            )
            if gate == "V0"
            else (
                "closed-cell-source-adapter/1.0.0"
                if gate == "V4"
                else (
                    (
                        "analytic-claims-adapter/1.0.0"
                        if search_evidence is None
                        else "prototype-final-relation-adapter/1.0.0"
                    )
                    if gate == "V5"
                    else "adapter/1.0.0"
                )
            )
            for gate in GATES
        },
    )


def _artifact_hash(
    value: dict[str, Any],
    profile: CanonicalProfile,
    validator: SemanticValidator,
) -> str:
    try:
        return canonical_hash(value, profile, validator=validator)
    except ArtifactValidationError:
        return sha256(b"Crochet.AI\x00UNVALIDATED_INPUT_V1\x00" + jcs_bytes(value)).hexdigest()
