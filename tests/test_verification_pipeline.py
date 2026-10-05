from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from crochet_ai.diagnostics import Diagnostic, FailureCode
from crochet_ai.verification_pipeline import (
    BACKEND_SEMANTIC_CHECKPOINT_V1,
    GATES,
    GateOutcome,
    GateResult,
    OverallState,
    VerificationProfile,
    evidence_is_valid,
    validate_resumed_evidence,
    verify_artifacts,
    verify_runners,
)

HASH_A = "a" * 64
HASH_B = "b" * 64


def synthetic_result(outcome: GateOutcome, gate: str = "V0") -> GateResult:
    diagnostics = (
        (
            Diagnostic(
                FailureCode.PROVENANCE,
                gate,
                "synthetic.rejected",
                "Independent synthetic vector failure",
                HASH_A,
            ),
        )
        if outcome is GateOutcome.FAIL
        else ()
    )
    return GateResult(
        outcome, assertions=(("checked", outcome is not GateOutcome.FAIL),), diagnostics=diagnostics
    )


def all_pass_runners() -> dict[str, object]:
    return {
        gate: (lambda: GateResult(GateOutcome.PASS, assertions=(("checked", True),)))
        for gate in GATES
    }


def test_order_hashes_and_telemetry_exclusion() -> None:
    profile = VerificationProfile(
        "test", "1", GATES, calibrated=True, calibration_evidence_sha256=HASH_B
    )
    first = verify_runners(
        input_hashes={"z": HASH_B, "a": HASH_A},
        runners={
            gate: (
                lambda: GateResult(
                    GateOutcome.PASS,
                    assertions=(("checked", True),),
                    telemetry=(("elapsed_ms", "1"),),
                )
            )
            for gate in GATES
        },
        profile=profile,
        implementation_versions={gate: "synthetic-independent/1" for gate in GATES},
    )
    second = verify_runners(
        input_hashes={"a": HASH_A, "z": HASH_B},
        runners={
            gate: (
                lambda: GateResult(
                    GateOutcome.PASS,
                    assertions=(("checked", True),),
                    telemetry=(("elapsed_ms", "99"),),
                )
            )
            for gate in GATES
        },
        profile=profile,
        implementation_versions={gate: "synthetic-independent/1" for gate in GATES},
    )
    assert tuple(record.gate_id for record in first.gates) == GATES
    hashes = dict(first.gates[0].input_hashes)
    assert hashes["a"] == HASH_A and hashes["z"] == HASH_B
    assert len(hashes["implementation_identity"]) == 64
    assert tuple(sorted(hashes.items())) == first.gates[0].input_hashes
    assert first.evidence_bundle_hash == second.evidence_bundle_hash
    assert first.overall_state is OverallState.VERIFIED


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (GateOutcome.PASS, OverallState.EXPERIMENTAL),
        (GateOutcome.WARNING, OverallState.EXPERIMENTAL),
        (GateOutcome.FAIL, OverallState.REJECTED),
        (GateOutcome.INDETERMINATE, OverallState.NOT_VERIFIED),
        (GateOutcome.NOT_RUN, OverallState.NOT_VERIFIED),
    ],
)
def test_overall_states(outcome: GateOutcome, expected: OverallState) -> None:
    runners = all_pass_runners()
    runners["V0"] = lambda: synthetic_result(outcome)
    result = verify_runners(input_hashes={"artifact": HASH_A}, runners=runners)
    assert result.overall_state is expected


def test_fail_short_circuits_and_diagnostic_mode_retains_rejection() -> None:
    calls: list[str] = []
    runners = {
        gate: (
            lambda gate=gate: (
                calls.append(gate)
                or synthetic_result(GateOutcome.FAIL if gate == "V1" else GateOutcome.PASS, gate)
            )
        )
        for gate in GATES
    }
    short = verify_runners(input_hashes={"artifact": HASH_A}, runners=runners)
    assert calls == ["V0", "V1"]
    assert short.gates[2].outcome is GateOutcome.NOT_RUN
    calls.clear()
    diagnostic = verify_runners(
        input_hashes={"artifact": HASH_A}, runners=runners, diagnostic_mode=True
    )
    assert calls == list(GATES)
    assert diagnostic.overall_state is OverallState.REJECTED


def test_missing_runner_invalid_hash_and_profile_order_rejected() -> None:
    missing = verify_runners(input_hashes={"artifact": HASH_A}, runners={})
    assert all(record.outcome is GateOutcome.NOT_RUN for record in missing.gates)
    with pytest.raises(ValueError, match="SHA-256"):
        verify_runners(input_hashes={"artifact": "bad"}, runners={})
    with pytest.raises(ValueError, match="ordered"):
        verify_runners(
            input_hashes={"artifact": HASH_A},
            runners={},
            profile=VerificationProfile("bad", "1", ("V1", "V0"), False),
        )


def test_resume_binding_and_tamper_detection() -> None:
    profile = VerificationProfile("test", "1", ("V0",), calibrated=False)
    versions = {"V0": "runner/1"}
    result = verify_runners(
        input_hashes={"artifact": HASH_A},
        runners={"V0": lambda: GateResult(GateOutcome.PASS, assertions=(("checked", True),))},
        profile=profile,
        implementation_versions=versions,
    )
    evidence = result.gates
    assert evidence_is_valid(evidence[0])
    assert validate_resumed_evidence(
        evidence,
        expected_input_hashes={"artifact": HASH_A},
        profile=profile,
        implementation_versions=versions,
    )
    assert not validate_resumed_evidence(
        evidence,
        expected_input_hashes={"artifact": HASH_B},
        profile=profile,
        implementation_versions=versions,
    )
    assert not validate_resumed_evidence(
        evidence,
        expected_input_hashes={"artifact": HASH_A},
        profile=replace(profile, version="2"),
        implementation_versions=versions,
    )
    assert not validate_resumed_evidence(
        evidence,
        expected_input_hashes={"artifact": HASH_A},
        profile=profile,
        implementation_versions={"V0": "runner/2"},
    )
    assert not evidence_is_valid(replace(evidence[0], outcome=GateOutcome.FAIL))
    assert not evidence_is_valid(replace(evidence[0], assertions=(("checked", False),)))


def test_evidence_storage_is_deeply_immutable() -> None:
    result = verify_runners(input_hashes={"artifact": HASH_A}, runners={})
    evidence = result.gates[0]
    with pytest.raises((AttributeError, TypeError)):
        evidence.input_hashes[0][0] = "changed"  # type: ignore[index]
    payload = evidence.to_dict()
    payload["input_hashes"]["artifact"] = HASH_B  # type: ignore[index]
    assert dict(evidence.input_hashes)["artifact"] == HASH_A


def test_adapter_admits_ideal_sphere_v0_but_keeps_v5_and_v4_incomplete(
    design_spec: dict[str, object],
    material_profile: dict[str, object],
    closed_ir: dict[str, object],
) -> None:
    result = verify_artifacts(design_spec, material_profile, closed_ir)
    by_gate = {record.gate_id: record for record in result.gates}
    assert by_gate["V0"].outcome is GateOutcome.PASS
    assert dict(by_gate["V0"].produced_artifact_hashes)["analytic_target"]
    assert by_gate["V4"].outcome is GateOutcome.INDETERMINATE
    assert by_gate["V5"].outcome is GateOutcome.NOT_RUN
    assert result.overall_state is not OverallState.VERIFIED
    assert result.physical_validation_status == "UNTESTED"


def test_malformed_inputs_fail_closed() -> None:
    result = verify_artifacts({}, {}, {})
    assert result.overall_state in {OverallState.REJECTED, OverallState.NOT_VERIFIED}
    assert result.overall_state is not OverallState.VERIFIED
    assert BACKEND_SEMANTIC_CHECKPOINT_V1.required_gates == GATES


def test_profile_contents_and_predecessor_chain_bind_resume() -> None:
    profile = VerificationProfile("test", "1", ("V0", "V1"), calibrated=False)
    versions = {"V0": "synthetic/1", "V1": "synthetic/1"}
    result = verify_runners(
        input_hashes={"artifact": HASH_A},
        runners=all_pass_runners(),
        profile=profile,
        implementation_versions=versions,
    )
    assert result.gates[1].input_hashes == (
        ("artifact", HASH_A),
        ("implementation_identity", dict(result.gates[0].input_hashes)["implementation_identity"]),
        ("prior_gate_evidence", result.gates[0].evidence_hash),
    )
    assert not validate_resumed_evidence(
        result.gates[1:],
        expected_input_hashes={"artifact": HASH_A},
        profile=profile,
        implementation_versions=versions,
    )
    assert not validate_resumed_evidence(
        result.gates,
        expected_input_hashes={"artifact": HASH_A},
        profile=replace(profile, calibrated=True),
        implementation_versions=versions,
    )
    called: list[str] = []
    resumed = verify_runners(
        input_hashes={"artifact": HASH_A},
        runners={"V0": lambda: called.append("unexpected")},
        profile=profile,
        implementation_versions=versions,
        resumed_evidence=result.gates,
    )
    assert called == []
    assert resumed.evidence_bundle_hash == result.evidence_bundle_hash


def test_pass_cannot_carry_failed_or_missing_assertions() -> None:
    for result in (
        GateResult(GateOutcome.PASS),
        GateResult(GateOutcome.PASS, assertions=(("exact_count", False),)),
        GateResult(GateOutcome.PASS, assertions=(("schema", True),), missing_checks=("topology",)),
    ):
        with pytest.raises(ValueError, match="invalid runner evidence"):
            verify_runners(
                input_hashes={"artifact": HASH_A}, runners={"V0": lambda result=result: result}
            )


def test_calibration_flag_and_disallowed_warning_cannot_certify() -> None:
    runners = all_pass_runners()
    versions = {gate: "synthetic/1" for gate in GATES}
    profile = VerificationProfile("synthetic", "1", GATES, calibrated=True)
    without_proof = verify_runners(
        input_hashes={"artifact": HASH_A},
        runners=runners,
        profile=profile,
        implementation_versions=versions,
    )
    assert without_proof.overall_state is not OverallState.VERIFIED
    runners["V8"] = lambda: GateResult(GateOutcome.WARNING)
    result = verify_runners(
        input_hashes={"artifact": HASH_A},
        runners=runners,
        profile=profile,
        implementation_versions=versions,
    )
    assert result.overall_state is OverallState.NOT_VERIFIED
    with pytest.raises(ValueError, match="nonempty"):
        VerificationProfile("empty", "1", (), calibrated=True)


def test_actual_semantic_error_has_structured_location_and_short_circuits(
    design_spec,
    material_profile,
    closed_ir,
) -> None:
    invalid = deepcopy(closed_ir)
    invalid["design_spec_ref"]["sha256"] = HASH_A
    result = verify_artifacts(design_spec, material_profile, invalid)
    by_gate = {gate.gate_id: gate for gate in result.gates}
    assert result.overall_state is OverallState.REJECTED
    assert by_gate["V2"].outcome is GateOutcome.FAIL
    assert by_gate["V3"].outcome is GateOutcome.NOT_RUN
    diagnostic = by_gate["V2"].to_dict()["diagnostics"][0]
    assert diagnostic["code"] == "E_REFERENCE"
    assert diagnostic["json_pointers"] == ["/design_spec_ref"]
    assert diagnostic["expected"] and diagnostic["observed"]
    assert diagnostic["diagnostic_id"]
    diagnostic_mode = verify_artifacts(design_spec, material_profile, invalid, diagnostic_mode=True)
    assert diagnostic_mode.overall_state is OverallState.REJECTED


def test_v9_checks_all_locales_and_links_export_hashes(
    design_spec, material_profile, closed_ir
) -> None:
    result = verify_artifacts(design_spec, material_profile, closed_ir)
    gate = result.gates[9]
    assert gate.outcome is GateOutcome.PASS
    assert gate.assertions == (
        ("semantic_round_trip.DE_DE", True),
        ("semantic_round_trip.UK_EN", True),
        ("semantic_round_trip.US_EN", True),
    )
    assert len(gate.produced_artifact_hashes) == 3
    assert result.overall_state is OverallState.NOT_VERIFIED


@given(st.lists(st.sampled_from(tuple(GateOutcome)), min_size=11, max_size=11))
@settings(max_examples=80, deadline=None)
def test_independent_outcome_vector_precedence(outcomes: list[GateOutcome]) -> None:
    # Diagnostic mode executes every synthetic gate, so later FAIL cannot be hidden by missing data.
    def runner(outcome: GateOutcome, gate: str):
        return lambda: synthetic_result(outcome, gate)

    result = verify_runners(
        input_hashes={"artifact": HASH_A},
        runners={
            gate: runner(outcome, gate) for gate, outcome in zip(GATES, outcomes, strict=True)
        },
        diagnostic_mode=True,
    )
    if GateOutcome.FAIL in outcomes:
        expected = OverallState.REJECTED
    elif any(outcome in (GateOutcome.NOT_RUN, GateOutcome.INDETERMINATE) for outcome in outcomes):
        expected = OverallState.NOT_VERIFIED
    else:
        expected = OverallState.EXPERIMENTAL
    assert result.overall_state is expected


def test_source_identity_change_invalidates_cached_evidence(monkeypatch) -> None:
    from crochet_ai import verification_pipeline as pipeline

    profile = VerificationProfile("synthetic", "1", ("V0",), calibrated=False)
    versions = {"V0": "unchanged-declared-version/1"}
    monkeypatch.setattr(pipeline, "implementation_identity_hash", lambda: HASH_A)
    result = verify_runners(
        input_hashes={"artifact": HASH_A},
        runners=all_pass_runners(),
        profile=profile,
        implementation_versions=versions,
    )
    monkeypatch.setattr(pipeline, "implementation_identity_hash", lambda: HASH_B)
    assert not validate_resumed_evidence(
        result.gates,
        expected_input_hashes={"artifact": HASH_A},
        profile=profile,
        implementation_versions=versions,
    )
    with pytest.raises(ValueError, match="reserved"):
        verify_runners(input_hashes={"implementation_identity": HASH_A}, runners={})
