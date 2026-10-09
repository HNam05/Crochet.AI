from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any

import pytest

from crochet_ai.canonical import CanonicalProfile, canonical_hash
from crochet_ai.provenance_chain import PROFILE, ProvenanceChainError, inspect_provenance_chain
from crochet_ai.validation import SemanticValidator
from crochet_ai.verification_pipeline import GATES, GateOutcome, GateResult, verify_runners


def _bundle(
    design_spec: dict[str, Any], material_profile: dict[str, Any], closed_ir: dict[str, Any]
) -> dict[str, Any]:
    validator = SemanticValidator(
        design_specs={design_spec["design_spec_id"]: design_spec},
        material_profiles={material_profile["profile_id"]: material_profile},
    )
    source_values = {
        "design_spec": (design_spec, CanonicalProfile.DESIGN_SPEC),
        "material_profile": (material_profile, CanonicalProfile.MATERIAL_PROFILE),
        "crochet_ir": (closed_ir, CanonicalProfile.CROCHET_IR),
    }
    bindings = {
        role: canonical_hash(payload, profile, validator=validator)
        for role, (payload, profile) in source_values.items()
    }
    result = verify_runners(
        input_hashes=bindings,
        runners={
            gate: lambda: GateResult(
                GateOutcome.PASS,
                assertions=(("synthetic_fixture_check", True),),
            )
            for gate in GATES[:10]
        },
        implementation_versions={gate: "fixture-runner/1" for gate in GATES[:10]},
    )
    return {
        "profile": PROFILE,
        "software_commit": "1" * 40,
        "source_bindings": bindings,
        "artifact_records": [
            {
                "role": role,
                "profile": profile.value,
                "sha256": bindings[role],
                "payload": deepcopy(payload),
            }
            for role, (payload, profile) in source_values.items()
        ],
        "gate_records": [gate.to_dict() for gate in result.gates[:10]],
        "physical_claim": {"status": "UNTESTED", "records": []},
        "required_roles": ["design_spec", "material_profile", "crochet_ir"],
    }


def test_hash_valid_full_computational_bundle_never_claims_authenticity(
    design_spec: dict[str, Any], material_profile: dict[str, Any], closed_ir: dict[str, Any]
) -> None:
    result = inspect_provenance_chain(_bundle(design_spec, material_profile, closed_ir))

    assert result["integrity"] == "VALID"
    assert result["result"] == "INCOMPLETE"
    assert result["verification_authenticity"] == "NOT_ESTABLISHED"
    assert result["gate_ids"] == list(GATES[:10])
    assert "trusted_execution_attestation_required" in result["diagnostics"]


@pytest.mark.parametrize(
    "mutation",
    [
        "source",
        "gate_digest",
        "predecessor",
        "order",
        "missing_gate",
        "software_mix",
        "profile_mix",
    ],
)
def test_adversarial_chain_mutations_fail_closed(
    mutation: str,
    design_spec: dict[str, Any],
    material_profile: dict[str, Any],
    closed_ir: dict[str, Any],
) -> None:
    bundle = _bundle(design_spec, material_profile, closed_ir)
    if mutation == "source":
        bundle["artifact_records"][0]["payload"]["design_spec_id"] = "foreign"
    elif mutation == "gate_digest":
        bundle["gate_records"][2]["scope"] = "tampered"
    elif mutation == "predecessor":
        bundle["gate_records"][2]["input_hashes"]["prior_gate_evidence"] = "0" * 64
    elif mutation == "order":
        bundle["gate_records"][1], bundle["gate_records"][2] = (
            bundle["gate_records"][2],
            bundle["gate_records"][1],
        )
    elif mutation == "software_mix":
        bundle["gate_records"][3]["input_hashes"]["implementation_identity"] = "0" * 64
    elif mutation == "profile_mix":
        bundle["gate_records"][3]["verification_profile_version"] = "other"
    else:
        bundle["gate_records"].pop(4)

    with pytest.raises(ProvenanceChainError) as error:
        inspect_provenance_chain(bundle)
    assert error.value.code == "E_PROVENANCE"


def test_duplicate_artifact_role_is_rejected(
    design_spec: dict[str, Any], material_profile: dict[str, Any], closed_ir: dict[str, Any]
) -> None:
    bundle = _bundle(design_spec, material_profile, closed_ir)
    bundle["artifact_records"].append(deepcopy(bundle["artifact_records"][0]))
    with pytest.raises(ProvenanceChainError, match="unique"):
        inspect_provenance_chain(bundle)


def test_positive_physical_claim_is_incomplete_without_trusted_review(
    design_spec: dict[str, Any], material_profile: dict[str, Any], closed_ir: dict[str, Any]
) -> None:
    bundle = _bundle(design_spec, material_profile, closed_ir)
    bundle["physical_claim"]["status"] = "PHYSICALLY_VERIFIED"

    result = inspect_provenance_chain(bundle)
    assert result["result"] == "INCOMPLETE"
    assert "trusted_physical_review_binding" in result["missing_roles"]


def test_failed_bound_physical_trial_is_reported_as_failure(
    design_spec: dict[str, Any], material_profile: dict[str, Any], closed_ir: dict[str, Any]
) -> None:
    bundle = _bundle(design_spec, material_profile, closed_ir)
    payload = {
        "design_spec_sha256": bundle["source_bindings"]["design_spec"],
        "material_profile_sha256": bundle["source_bindings"]["material_profile"],
        "crochet_ir_sha256": bundle["source_bindings"]["crochet_ir"],
        "outcome": "FAIL",
        "failure_code": "E_PHYSICAL_VALIDATION",
    }
    profile = "PROVENANCE_ARTIFACT_JCS_V1"
    digest = sha256(
        b"Crochet.AI\0" + profile.encode() + b"\0" + __import__("rfc8785").dumps(payload)
    ).hexdigest()
    bundle["physical_claim"] = {
        "status": "PHYSICALLY_VERIFIED",
        "records": [
            {
                "role": "physical_trial_record",
                "profile": profile,
                "sha256": digest,
                "payload": payload,
            }
        ],
    }

    result = inspect_provenance_chain(bundle)
    assert result["result"] == "FAIL"
    assert "E_PHYSICAL_VALIDATION" in result["diagnostics"]


def test_foreign_physical_specimen_binding_is_rejected(
    design_spec: dict[str, Any], material_profile: dict[str, Any], closed_ir: dict[str, Any]
) -> None:
    bundle = _bundle(design_spec, material_profile, closed_ir)
    payload = {
        "design_spec_sha256": "0" * 64,
        "material_profile_sha256": bundle["source_bindings"]["material_profile"],
        "crochet_ir_sha256": bundle["source_bindings"]["crochet_ir"],
        "outcome": "FAIL",
        "failure_code": "E_PHYSICAL_VALIDATION",
    }
    profile = "PROVENANCE_ARTIFACT_JCS_V1"
    digest = sha256(
        b"Crochet.AI\0" + profile.encode() + b"\0" + __import__("rfc8785").dumps(payload)
    ).hexdigest()
    bundle["physical_claim"] = {
        "status": "PHYSICALLY_VERIFIED",
        "records": [
            {
                "role": "physical_trial_record",
                "profile": profile,
                "sha256": digest,
                "payload": payload,
            }
        ],
    }
    with pytest.raises(ProvenanceChainError, match="not bound"):
        inspect_provenance_chain(bundle)
