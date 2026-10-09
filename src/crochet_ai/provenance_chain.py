"""Diagnostic content-integrity audit for a serialized software/physical evidence bundle.

This module checks hashes and links. A self-submitted bundle cannot prove who ran a
gate, so a valid chain is deliberately never reported as authenticated verification.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from hashlib import sha256
from typing import Any, NoReturn, cast

from .canonical import (
    CanonicalizationError,
    CanonicalProfile,
    canonical_hash,
    jcs_bytes,
    validate_ijson,
)
from .diagnostics import ArtifactValidationError
from .json_types import JSONValue
from .validation import SemanticValidator
from .verification_pipeline import (
    GATES,
    GateEvidence,
    GateOutcome,
    evidence_is_valid,
)

PROFILE = "PROVENANCE_CHAIN_DIAGNOSTIC_V1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_SOURCE_PROFILES = {
    "design_spec": CanonicalProfile.DESIGN_SPEC,
    "material_profile": CanonicalProfile.MATERIAL_PROFILE,
    "crochet_ir": CanonicalProfile.CROCHET_IR,
}
_GATE_SERIALIZED_FIELDS = {
    "gate_id",
    "implementation_version",
    "outcome",
    "input_hashes",
    "verification_profile_id",
    "verification_profile_version",
    "verification_profile_hash",
    "assertions",
    "assertion_counts",
    "threshold_profile_id",
    "parameters",
    "work_budget",
    "random_seed",
    "metric_vector",
    "linked_evidence",
    "produced_artifact_hashes",
    "diagnostics",
    "missing_checks",
    "scope",
    "evidence_hash",
    "telemetry",
}


class ProvenanceChainError(ValueError):
    """A malformed or contradictory provenance bundle, with a stable error code."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


def _fail(code: str, reason: str) -> NoReturn:
    raise ProvenanceChainError(code, reason)


def _is_hash(value: object) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _domain_hash(profile: str, value: object) -> str:
    if not isinstance(value, dict):
        _fail("E_PROVENANCE", "artifact payload must be a JSON object")
    validate_ijson(value)
    return sha256(
        b"Crochet.AI\0" + profile.encode("ascii") + b"\0" + jcs_bytes(cast(JSONValue, value))
    ).hexdigest()


def _check_hash_links(payload: object, known_hashes: Mapping[str, str], path: str) -> None:
    if isinstance(payload, dict):
        for key, child in payload.items():
            if key.endswith("_sha256"):
                role = key[:-7]
                if role not in known_hashes or child != known_hashes[role]:
                    _fail("E_PROVENANCE", f"unresolved or contradictory hash link at {path}/{key}")
            _check_hash_links(child, known_hashes, f"{path}/{key}")
    elif isinstance(payload, list):
        for index, child in enumerate(payload):
            _check_hash_links(child, known_hashes, f"{path}/{index}")


def _gate_from_dict(value: object) -> GateEvidence:
    if not isinstance(value, dict) or not _GATE_SERIALIZED_FIELDS.issuperset(value):
        _fail("E_PROVENANCE", "gate record has an invalid serialized shape")
    if set(value) != _GATE_SERIALIZED_FIELDS:
        _fail("E_PROVENANCE", "gate record fields do not match serialized GateEvidence")
    if value["random_seed"] is not None:
        _fail("E_PROVENANCE", "unsupported non-null random_seed in gate evidence")
    try:
        payload = {
            key: child
            for key, child in value.items()
            if key not in {"telemetry", "assertion_counts", "random_seed"}
        }
        if not isinstance(payload["input_hashes"], dict) or not isinstance(
            payload["produced_artifact_hashes"], dict
        ):
            _fail("E_PROVENANCE", "gate hash collections must be objects")
        if not isinstance(payload["assertions"], list) or not isinstance(
            payload["diagnostics"], list
        ):
            _fail("E_PROVENANCE", "gate assertions and diagnostics must be arrays")
        if not isinstance(payload["evidence_hash"], str):
            _fail("E_PROVENANCE", "gate evidence hash is missing")
        gate = GateEvidence(
            gate_id=payload["gate_id"],
            implementation_version=payload["implementation_version"],
            outcome=GateOutcome(payload["outcome"]),
            input_hashes=tuple(sorted(payload["input_hashes"].items())),
            verification_profile_id=payload["verification_profile_id"],
            verification_profile_version=payload["verification_profile_version"],
            verification_profile_hash=payload["verification_profile_hash"],
            assertions=tuple((item[0], item[1]) for item in payload["assertions"]),
            diagnostics=tuple(jcs_bytes(item).decode("utf-8") for item in payload["diagnostics"]),
            missing_checks=tuple(payload["missing_checks"]),
            scope=payload["scope"],
            evidence_hash=payload["evidence_hash"],
            telemetry=tuple(sorted(value["telemetry"].items())),
            produced_artifact_hashes=tuple(sorted(payload["produced_artifact_hashes"].items())),
            threshold_profile_id=payload["threshold_profile_id"],
            parameters_json=jcs_bytes(payload["parameters"]).decode("utf-8"),
            work_budget_json=jcs_bytes(payload["work_budget"]).decode("utf-8"),
            metric_vector_json=jcs_bytes(payload["metric_vector"]).decode("utf-8"),
            linked_evidence_json=jcs_bytes(payload["linked_evidence"]).decode("utf-8"),
        )
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        if isinstance(error, ProvenanceChainError):
            raise
        _fail("E_PROVENANCE", "gate record cannot be reconstructed as GateEvidence")
    counts = {
        "passed": sum(result for _, result in gate.assertions),
        "failed": sum(not result for _, result in gate.assertions),
    }
    if value["assertion_counts"] != counts or not evidence_is_valid(gate):
        _fail("E_PROVENANCE", "gate evidence digest or internal assertions are invalid")
    return gate


def inspect_provenance_chain(value: object) -> dict[str, Any]:
    """Recompute a strict bundle's content links and return diagnostic-only status.

    Bundle shape: profile, software_commit, source_bindings, artifact_records,
    gate_records, physical_claim, required_roles. Artifact source payloads use the
    canonical DesignSpec/MaterialProfile/CrochetIR profiles; other payloads are
    restricted to the generic domain-separated JCS profile below.
    """
    if not isinstance(value, dict):
        _fail("E_PROVENANCE", "bundle must be a JSON object")
    try:
        validate_ijson(value)
    except (TypeError, ValueError) as error:
        _fail("E_PROVENANCE", f"bundle is not valid I-JSON: {error}")
    expected = {
        "profile",
        "software_commit",
        "source_bindings",
        "artifact_records",
        "gate_records",
        "physical_claim",
        "required_roles",
    }
    if set(value) != expected or value.get("profile") != PROFILE:
        _fail("E_PROVENANCE", "bundle fields or diagnostic profile are unsupported")
    commit = value["software_commit"]
    if not isinstance(commit, str) or not _COMMIT.fullmatch(commit):
        _fail("E_PROVENANCE", "software_commit must be 40 lowercase hexadecimal characters")
    bindings = value["source_bindings"]
    if not isinstance(bindings, dict) or not set(_SOURCE_PROFILES).issubset(bindings):
        _fail(
            "E_PROVENANCE",
            "source_bindings must explicitly bind DesignSpec, MaterialProfile, and CrochetIR",
        )
    if any(not isinstance(role, str) or not _is_hash(digest) for role, digest in bindings.items()):
        _fail("E_PROVENANCE", "source binding values must be lowercase SHA-256 digests")

    records = value["artifact_records"]
    if not isinstance(records, list):
        _fail("E_PROVENANCE", "artifact_records must be an ordered array")
    by_role: dict[str, dict[str, Any]] = {}
    source_payloads: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict) or set(record) != {"role", "profile", "sha256", "payload"}:
            _fail(
                "E_PROVENANCE",
                "artifact record must contain exactly role, profile, sha256, payload",
            )
        role, profile, claimed, payload = (
            record[key] for key in ("role", "profile", "sha256", "payload")
        )
        if not isinstance(role, str) or not role or role in by_role:
            _fail("E_PROVENANCE", "artifact roles must be nonempty and unique")
        if not isinstance(profile, str) or not profile or not _is_hash(claimed):
            _fail("E_PROVENANCE", f"artifact {role!r} has invalid profile or digest")
        if role in _SOURCE_PROFILES:
            if profile != _SOURCE_PROFILES[role].value or not isinstance(payload, dict):
                _fail("E_PROVENANCE", f"source artifact {role!r} has the wrong canonical profile")
            source_payloads[role] = payload
        else:
            if profile != "PROVENANCE_ARTIFACT_JCS_V1":
                _fail("E_PROVENANCE", f"artifact {role!r} uses an unsupported domain profile")
            if _domain_hash(profile, payload) != claimed:
                _fail("E_PROVENANCE", f"artifact {role!r} content digest mismatch")
        by_role[role] = record

    material = source_payloads.get("material_profile")
    design = source_payloads.get("design_spec")
    validator = SemanticValidator(
        material_profiles={material["profile_id"]: material}
        if material and isinstance(material.get("profile_id"), str)
        else {},
        design_specs={design["design_spec_id"]: design}
        if design and isinstance(design.get("design_spec_id"), str)
        else {},
    )
    for role, payload in source_payloads.items():
        try:
            computed = canonical_hash(payload, _SOURCE_PROFILES[role], validator=validator)
        except (ArtifactValidationError, CanonicalizationError, TypeError, ValueError) as error:
            _fail(
                "E_PROVENANCE",
                "source artifact "
                f"{role!r} failed semantic canonicalization: {type(error).__name__}",
            )
        if computed != by_role[role]["sha256"] or bindings.get(role) != computed:
            _fail(
                "E_PROVENANCE",
                f"source artifact {role!r} does not match its bound canonical digest",
            )
    absent_sources = sorted(set(_SOURCE_PROFILES) - set(source_payloads))
    if absent_sources:
        _fail(
            "E_PROVENANCE",
            f"required source artifact records are missing: {', '.join(absent_sources)}",
        )
    for role, digest in bindings.items():
        if role not in by_role or by_role[role]["sha256"] != digest:
            _fail("E_PROVENANCE", f"source binding {role!r} has no matching artifact record")

    required_roles = value["required_roles"]
    if (
        not isinstance(required_roles, list)
        or not required_roles
        or any(not isinstance(x, str) for x in required_roles)
    ):
        _fail("E_PROVENANCE", "required_roles must be a nonempty ordered list")
    if len(required_roles) != len(set(required_roles)):
        _fail("E_PROVENANCE", "required_roles contains duplicates")
    if not set(_SOURCE_PROFILES).issubset(required_roles):
        _fail("E_PROVENANCE", "required_roles must include all three canonical source artifacts")
    missing_roles = [role for role in required_roles if role not in by_role]
    known_hashes = {role: record["sha256"] for role, record in by_role.items()}
    known_hashes.update(bindings)
    for role, record in by_role.items():
        if role not in _SOURCE_PROFILES:
            _check_hash_links(record["payload"], known_hashes, f"artifact_records/{role}/payload")

    gates_raw = value["gate_records"]
    if not isinstance(gates_raw, list):
        _fail("E_PROVENANCE", "gate_records must be an array")
    gates = [_gate_from_dict(record) for record in gates_raw]
    gate_ids = [gate.gate_id for gate in gates]
    if len(set(gate_ids)) != len(gate_ids) or gate_ids != list(GATES[: len(gate_ids)]):
        _fail("E_PROVENANCE", "gate records must be unique and contiguous in V0-V9 order")
    if len(gates) > 10:
        _fail("E_PROVENANCE", "physical V10 evidence is outside this bundle profile")
    identity: str | None = None
    for index, gate in enumerate(gates):
        inputs = dict(gate.input_hashes)
        if identity is None:
            identity = inputs.get("implementation_identity")
        expected_inputs = dict(bindings)
        if identity is not None:
            expected_inputs["implementation_identity"] = identity
        if index:
            expected_inputs["prior_gate_evidence"] = gates[index - 1].evidence_hash
        if inputs != expected_inputs:
            _fail("E_PROVENANCE", f"{gate.gate_id} input bindings or predecessor digest mismatch")
        if (
            gate.verification_profile_id,
            gate.verification_profile_version,
            gate.verification_profile_hash,
        ) != (
            gates[0].verification_profile_id,
            gates[0].verification_profile_version,
            gates[0].verification_profile_hash,
        ):
            _fail("E_PROVENANCE", "gate verification profile changed inside the chain")
        if "implementation_identity" not in inputs or not _is_hash(
            inputs["implementation_identity"]
        ):
            _fail("E_PROVENANCE", f"{gate.gate_id} lacks an implementation identity binding")

    physical = value["physical_claim"]
    if not isinstance(physical, dict) or set(physical) != {"status", "records"}:
        _fail("E_PROVENANCE", "physical_claim must contain exactly status and records")
    status, physical_records = physical["status"], physical["records"]
    if (
        not isinstance(status, str)
        or status not in {"UNTESTED", "CALIBRATED", "PHYSICALLY_VERIFIED"}
        or not isinstance(physical_records, list)
    ):
        _fail("E_PROVENANCE", "physical claim status or records are invalid")
    if status == "UNTESTED" and physical_records:
        _fail("E_PROVENANCE", "UNTESTED physical claim cannot carry positive records")
    for physical_record in physical_records:
        if not isinstance(physical_record, dict) or set(physical_record) != {
            "role",
            "profile",
            "sha256",
            "payload",
        }:
            _fail("E_PROVENANCE", "physical record has an invalid artifact-record shape")
        role = physical_record["role"]
        if (
            not isinstance(role, str)
            or role not in {"calibration_record", "physical_trial_record"}
            or physical_record["profile"] != "PROVENANCE_ARTIFACT_JCS_V1"
        ):
            _fail("E_PROVENANCE", "physical record role or profile is unsupported")
        if (
            not _is_hash(physical_record["sha256"])
            or _domain_hash(physical_record["profile"], physical_record["payload"])
            != physical_record["sha256"]
        ):
            _fail("E_PROVENANCE", "physical record digest mismatch")
        payload = physical_record["payload"]
        if (
            not isinstance(payload, dict)
            or payload.get("design_spec_sha256") != bindings["design_spec"]
            or payload.get("material_profile_sha256") != bindings["material_profile"]
            or payload.get("crochet_ir_sha256") != bindings["crochet_ir"]
        ):
            _fail(
                "E_PROVENANCE",
                "physical record is not bound to this DesignSpec, material profile, and CrochetIR",
            )
        _check_hash_links(payload, known_hashes, f"physical_claim/records/{role}/payload")

    failed_physical_trial = any(
        item["role"] == "physical_trial_record"
        and isinstance(item["payload"], dict)
        and item["payload"].get("outcome") == "FAIL"
        and item["payload"].get("failure_code") == "E_PHYSICAL_VALIDATION"
        for item in physical_records
    )
    if status != "UNTESTED" and not failed_physical_trial:
        missing_roles.append("trusted_physical_review_binding")
    outcomes = [gate.outcome for gate in gates]
    has_gate_failure = GateOutcome.FAIL in outcomes
    all_software_gates = len(gates) == 10 and gate_ids == list(GATES[:10])
    all_gate_pass = all(outcome is GateOutcome.PASS for outcome in outcomes)
    if failed_physical_trial:
        result_status = "FAIL"
        diagnostics = ["E_PHYSICAL_VALIDATION"]
    elif has_gate_failure:
        result_status = "FAIL"
        diagnostics = ["E_PROVENANCE"]
    elif missing_roles or not all_software_gates or not all_gate_pass:
        result_status = "INCOMPLETE"
        diagnostics = []
    else:
        # A hash-valid self-submitted bundle cannot authenticate execution.
        result_status = "INCOMPLETE"
        diagnostics = ["trusted_execution_attestation_required"]
    return {
        "profile": PROFILE,
        "integrity": "VALID",
        "result": result_status,
        "verification_authenticity": "NOT_ESTABLISHED",
        "physical_status_claim": status,
        "diagnostics": diagnostics,
        "missing_roles": missing_roles,
        "artifact_hashes": {role: record["sha256"] for role, record in by_role.items()},
        "gate_ids": gate_ids,
        "software_commit": commit,
    }
