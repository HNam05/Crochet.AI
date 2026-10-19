from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, replace
from fractions import Fraction
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from test_analytic_solver import PROVENANCE
from test_analytic_solver import config as analytic_config
from test_analytic_trace import _config as trace_config
from test_analytic_trace_audit import evidence as trace_evidence
from test_backend_numerical_delivery import f0_request
from test_coordinate_target_adversarial import explicit_design
from test_numerical_verification import _context, _snapshot

from crochet_ai.analytic_selection import (
    AnalyticSelectionError,
    _fraction,
    _fraction_wire,
    _ranking,
    select_analytic_numerical_candidate,
)
from crochet_ai.analytic_solver import generate_analytic
from crochet_ai.canonical import CanonicalProfile, canonical_hash
from crochet_ai.validation import SemanticValidator
from crochet_ai.verification_pipeline import ANALYTIC_NUMERICAL_CANDIDATE_V1, GATES


def _mock_selection_request(*, empty: bool = False) -> dict[str, Any]:
    cfg = trace_config()
    if empty:
        cfg = replace(cfg, initial_ring_min=100, initial_ring_max=101)
    generated = trace_evidence(cfg)
    commit = "c" * 40
    context = _context()
    proposals = generated["candidate_proposals"]
    design = generated["design_spec"]
    return {
        "design_spec": design,
        "material_profile": generated["material_profile"],
        "search_evidence": {
            "run_config": generated["run_config"],
            "search_trace": generated["search_trace"],
            "candidate_proposals": proposals,
        },
        "numerical_run": context,
        "selection_policy": {
            "profile": "ANALYTIC_NUMERICAL_SELECTION_V1",
            "schema_version": "1.0.0",
            "max_candidate_evaluations": min(
                2, design["solver_options"]["max_candidate_evaluations"]
            ),
        },
        "software_commit": commit,
        "source_snapshot": _snapshot(commit),
    }


class _Verification:
    def __init__(self, value: dict[str, Any]) -> None:
        self.value = value

    def to_dict(self) -> dict[str, Any]:
        return self.value


def _verification_value(
    *, failure: str | None = None, false_assertion: bool = False
) -> dict[str, Any]:
    metrics = _raw_metrics(chamfer=0.1, hausdorff=0.2, iou=0.9)
    metrics["surface_normal_mean_degrees"] = 1.0
    metrics["surface_normal_p95_degrees"] = 2.0
    gates: list[dict[str, Any]] = []
    for index in range(11):
        gate: dict[str, Any] = {
            "gate_id": GATES[index],
            "outcome": "PASS",
            "missing_checks": [],
            "diagnostics": [],
            "assertions": [["test.assertion", True]],
            "metric_vector": metrics if index == 7 else {},
            "verification_profile_id": ANALYTIC_NUMERICAL_CANDIDATE_V1.profile_id,
            "verification_profile_version": ANALYTIC_NUMERICAL_CANDIDATE_V1.version,
            "verification_profile_hash": ANALYTIC_NUMERICAL_CANDIDATE_V1.content_hash,
        }
        if failure == "missing" and index == 6:
            gate["missing_checks"] = ["required check missing"]
        if failure == "outcome" and index == 6:
            gate["outcome"] = "INDETERMINATE"
        if false_assertion and index == 5:
            gate["assertions"] = [["test.false", False]]
        gates.append(gate)
    return {"verification_state": "EXPERIMENTAL", "physical_status": "UNTESTED", "gates": gates}


def _patch_verifier(
    monkeypatch: pytest.MonkeyPatch,
    *,
    failure=None,
    false_assertion=False,
    profile_mutation: str | None = None,
) -> None:
    import crochet_ai.analytic_selection as selection

    def fake_verifier(design, material, ir, **_kwargs):
        validator = SemanticValidator(
            design_specs={design["design_spec_id"]: design},
            material_profiles={material["profile_id"]: material},
        )
        ir_hash = canonical_hash(ir, CanonicalProfile.CROCHET_IR, validator=validator)
        value = {
            **_verification_value(failure=failure, false_assertion=false_assertion),
            "verification_profile_id": ANALYTIC_NUMERICAL_CANDIDATE_V1.profile_id,
            "profile_version": ANALYTIC_NUMERICAL_CANDIDATE_V1.version,
            "verification_state": "EXPERIMENTAL",
            "physical_status": "UNTESTED",
            "input_hashes": {"crochet_ir": ir_hash},
        }
        if profile_mutation == "wrong_profile":
            value["verification_profile_id"] = "BACKEND_SEMANTIC_CHECKPOINT_V1"
        if profile_mutation == "wrong_hash":
            value["input_hashes"]["crochet_ir"] = "0" * 64
        if profile_mutation == "wrong_order":
            value["gates"].reverse()
        return _Verification(value)

    monkeypatch.setattr(selection, "verify_artifacts", fake_verifier)


def native_cylinder_selection_request(
    *, radius: float = 4, height: float = 40, count: int = 6, sectors: int = 11
) -> dict[str, Any]:
    """Real two-member explicit-cylinder batch and synthetic plumbing policies."""
    design, material = explicit_design([(0, 0), (radius, 0), (radius, height), (0, height)])
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    design["solver_options"]["max_candidate_evaluations"] = 2
    run = replace(
        analytic_config(),
        min_courses=3,
        max_courses=4,
        max_course_hypotheses=2,
        count_window_radius=0,
        min_count=count,
        max_count=count,
        initial_ring_min=count,
        initial_ring_max=count,
        max_terminal_count=count,
        max_emitted_candidates=2,
    )
    batch = generate_analytic(design, material, run, PROVENANCE)
    assert batch.search_trace is not None
    run_config = asdict(run)
    fraction = run.minimum_shaping_separation_turns
    run_config["minimum_shaping_separation_turns"] = f"{fraction.numerator}/{fraction.denominator}"
    proposals = [candidate.crochet_ir.to_dict() for candidate in batch.candidates]
    assert len(proposals) == 2, batch.reason
    context = _context()
    context["forward_run"] = f0_request()["forward_run"]
    context["target_sampling"] = {
        "profile": "ANALYTIC_TARGET_SURFACE_SAMPLING_V1",
        "schema_version": "1.0.0",
        "azimuth_sectors": sectors,
        "linear_segment_subdivisions": 1,
    }
    context["rigid_alignment"] = [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, -1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    for name, threshold in context["comparison_policy"]["hard_thresholds"].items():
        threshold["value"] = (
            0
            if name == "topology_match"
            else 0.001
            if name == "silhouette_iou_min"
            else 180
            if "degrees" in name
            else 1e6
        )
        threshold["owner"] = "synthetic numerical selection plumbing fixture"
        threshold["rationale"] = "deliberately permissive plumbing test; not physical validity"
        threshold["validation_path"] = "test_analytic_selection"
    commit = "c" * 40
    return {
        "design_spec": design,
        "material_profile": material,
        "search_evidence": {
            "run_config": run_config,
            "search_trace": batch.search_trace.to_dict(),
            "candidate_proposals": proposals,
        },
        "numerical_run": context,
        "selection_policy": {
            "profile": "ANALYTIC_NUMERICAL_SELECTION_V1",
            "schema_version": "1.0.0",
            "max_candidate_evaluations": 2,
        },
        "software_commit": commit,
        "source_snapshot": _snapshot(commit),
    }


@given(
    left=st.floats(allow_nan=False, allow_infinity=False, width=64),
    right=st.floats(allow_nan=False, allow_infinity=False, width=64),
)
def test_binary64_ranking_conversion_is_exact(left: float, right: float) -> None:
    left_rank = _fraction(left)
    right_rank = _fraction(right)
    assert left_rank == Fraction.from_float(left)
    assert right_rank == Fraction.from_float(right)
    assert (left_rank < right_rank) == (left < right)
    wire = _fraction_wire(left_rank)
    assert len(wire) == 2
    assert Fraction(int(wire[0]), int(wire[1])) == left_rank


def test_global_policy_validation_rejects_before_numerical_execution() -> None:
    with pytest.raises(AnalyticSelectionError) as error:
        select_analytic_numerical_candidate(
            {},
            {},
            {},
            {},
            {
                "profile": "ANALYTIC_NUMERICAL_SELECTION_V1",
                "schema_version": "1.0.0",
                "max_candidate_evaluations": 0,
            },
            software_commit="c" * 40,
            source_snapshot={
                "source_snapshot_sha256": "d" * 64,
                "implementation_identity": "e" * 64,
            },
        )
    assert error.value.code == "E_INPUT" or error.value.code == "E_SCHEMA"


def _raw_gate(metrics: dict[str, object]) -> list[dict[str, object]]:
    return [{"gate_id": "V7", "metric_vector": metrics}]


def _raw_ir(
    *,
    stitches: int,
    courses: int = 2,
    operations: list[dict[str, object]] | None = None,
    shaping: int = 0,
) -> dict[str, object]:
    return {
        "stitches": [
            {"shaping": "INCREASE" if index < shaping else "PLAIN"} for index in range(stitches)
        ],
        "courses": [{} for _ in range(courses)],
        "construction_operations": [] if operations is None else operations,
    }


def _raw_metrics(*, chamfer: float, hausdorff: float, iou: float) -> dict[str, float]:
    return {
        "symmetric_chamfer_normalized": chamfer,
        "robust_hausdorff_normalized": hausdorff,
        "silhouette_iou_min": iou,
        "surface_normal_mean_degrees": 1.0,
        "surface_normal_p95_degrees": 2.0,
        "section_error_normalized": 0.01,
        "curvature_error_normalized": 0.02,
        "relative_volume_error": 0.03,
        "landmark_max_normalized": 0.04,
    }


def test_exact_total_order_uses_first_incomparable_metric_and_hash_tie_break() -> None:
    left_ir = _raw_ir(stitches=10)
    right_ir = _raw_ir(stitches=8)
    left, _ = _ranking(
        left_ir, _raw_gate(_raw_metrics(chamfer=0.2, hausdorff=0.9, iou=0.8)), "a" * 64
    )
    right, _ = _ranking(
        right_ir, _raw_gate(_raw_metrics(chamfer=0.3, hausdorff=0.1, iou=0.9)), "b" * 64
    )
    assert left < right  # first metric wins despite later metric/complexity tradeoffs

    # Equal raw vectors and construction counts resolve only by the canonical IR digest.
    same_metrics = _raw_gate(_raw_metrics(chamfer=0.2, hausdorff=0.3, iou=0.8))
    same_a, _ = _ranking(_raw_ir(stitches=10), same_metrics, "a" * 64)
    same_b, _ = _ranking(_raw_ir(stitches=10), same_metrics, "b" * 64)
    assert same_a < same_b


def test_rank_order_uses_native_cost_fields_shaping_and_exact_metric_values() -> None:
    costly = _raw_ir(
        stitches=4,
        courses=1,
        operations=[
            {"operation_type": "JOIN", "join_method": "SEWN"},
            {"operation_type": "CUT_YARN"},
            {"operation_type": "ATTACH", "input_frontier_ids": ["f0"]},
        ],
        shaping=0,
    )
    cheap = _raw_ir(stitches=5, courses=2, shaping=2)
    worse_metrics = _raw_gate(_raw_metrics(chamfer=0.9, hausdorff=0.9, iou=0.1))
    better_metrics = _raw_gate(_raw_metrics(chamfer=0.1, hausdorff=0.1, iou=0.9))
    # Construction costs are the first tuple elements and dominate geometry.
    costly_key, costly_evidence = _ranking(costly, better_metrics, "a" * 64)
    cheap_key, cheap_evidence = _ranking(cheap, worse_metrics, "b" * 64)
    assert cheap_key < costly_key
    assert costly_evidence["construction_counts"] == {
        "sewn_seams": 1,
        "yarn_cuts": 1,
        "yarn_reattachments": 1,
        "stitches": 4,
        "courses": 1,
        "shaping_nodes": 0,
    }
    assert cheap_evidence["construction_counts"]["shaping_nodes"] == 2

    # Deliberately contradictory duplicate evidence catches extraction from the wrong field.
    adversarial_gate = _raw_gate(_raw_metrics(chamfer=0.2, hausdorff=0.3, iou=0.7))[0]
    adversarial_gate["linked_evidence"] = {"metrics": {"symmetric_chamfer_normalized": 999.0}}
    actual_key, _ = _ranking(cheap, [adversarial_gate], "c" * 64)
    expected_key = (
        0,
        0,
        0,
        Fraction.from_float(0.2),
        Fraction.from_float(0.3),
        Fraction(1) - Fraction.from_float(0.7),
        Fraction.from_float(1.0),
        Fraction.from_float(2.0),
        Fraction.from_float(0.01),
        Fraction.from_float(0.02),
        Fraction.from_float(0.03),
        Fraction.from_float(0.04),
        5,
        2,
        2,
        "c" * 64,
    )
    assert actual_key == expected_key


def test_lexicographic_extension_respects_coordinatewise_metric_dominance() -> None:
    better_metrics = _raw_metrics(chamfer=0.2, hausdorff=0.3, iou=0.8)
    worse_metrics = _raw_metrics(chamfer=0.3, hausdorff=0.4, iou=0.7)
    better, _ = _ranking(_raw_ir(stitches=8), _raw_gate(better_metrics), "a" * 64)
    worse, _ = _ranking(_raw_ir(stitches=8), _raw_gate(worse_metrics), "b" * 64)
    better_vector = (
        better_metrics["symmetric_chamfer_normalized"],
        better_metrics["robust_hausdorff_normalized"],
        1.0 - better_metrics["silhouette_iou_min"],
    )
    worse_vector = (
        worse_metrics["symmetric_chamfer_normalized"],
        worse_metrics["robust_hausdorff_normalized"],
        1.0 - worse_metrics["silhouette_iou_min"],
    )
    assert all(left <= right for left, right in zip(better_vector, worse_vector, strict=True))
    assert better_vector != worse_vector
    assert better < worse


def test_ranking_rejects_missing_or_nonbinary64_required_observation() -> None:
    metrics = _raw_metrics(chamfer=0.2, hausdorff=0.3, iou=0.8)
    del metrics["relative_volume_error"]
    with pytest.raises(AnalyticSelectionError) as missing:
        _ranking(_raw_ir(stitches=2), _raw_gate(metrics), "a" * 64)
    assert missing.value.code == "E_PROVENANCE"

    metrics = dict(_raw_metrics(chamfer=0.2, hausdorff=0.3, iou=0.8))
    metrics["relative_volume_error"] = None
    with pytest.raises(AnalyticSelectionError) as invalid:
        _ranking(_raw_ir(stitches=2), _raw_gate(metrics), "a" * 64)
    assert invalid.value.code == "E_INPUT"


def test_iou_complement_is_exact_for_binary64_value() -> None:
    observed_iou = 0.1
    exact_complement = Fraction(1) - Fraction.from_float(observed_iou)
    assert exact_complement != Fraction.from_float(1.0 - observed_iou)


@pytest.mark.parametrize("failure", ["missing", "outcome"])
@pytest.mark.parametrize("false_assertion", [False, True])
def test_missing_failed_or_false_gate_evidence_never_selects(
    monkeypatch: pytest.MonkeyPatch, failure: str, false_assertion: bool
) -> None:
    _patch_verifier(monkeypatch, failure=failure, false_assertion=false_assertion)
    result = select_analytic_numerical_candidate(**_mock_selection_request())
    assert result["selected_crochet_ir"] is None
    assert result["status"] == "INDETERMINATE"
    assert all(
        isinstance(candidate, dict) and candidate.get("eligible") is False
        for candidate in result["candidate_results"]
    )


@pytest.mark.parametrize("mutation", ["wrong_profile", "wrong_hash", "wrong_order"])
def test_profile_order_and_candidate_hash_binding_are_mandatory(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    _patch_verifier(monkeypatch, profile_mutation=mutation)
    result = select_analytic_numerical_candidate(**_mock_selection_request())
    assert result["selected_crochet_ir"] is None
    assert result["status"] == "INDETERMINATE"


def test_policy_prefix_accounts_for_unreached_candidates_and_never_selects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_verifier(monkeypatch)
    request = _mock_selection_request()
    assert len(request["search_evidence"]["candidate_proposals"]) == 2
    request["selection_policy"]["max_candidate_evaluations"] = 1
    result = select_analytic_numerical_candidate(**request)
    assert result["status"] == "BUDGET_EXHAUSTED"
    assert result["selected_crochet_ir"] is None
    assert result["candidate_results"][0]["eligible"] is True
    assert result["candidate_results"][1]["status"] == "NOT_RUN"


def test_empty_complete_generation_has_truthful_terminal_and_no_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_verifier(monkeypatch)
    request = _mock_selection_request(empty=True)
    result = select_analytic_numerical_candidate(**request)
    assert result["status"] == "NO_FEASIBLE_CANDIDATE"
    assert result["candidate_results"] == []
    assert result["selected_crochet_ir"] is None
    assert result["generation_terminal"] == request["search_evidence"]["search_trace"]["terminal"]


def test_request_digest_is_deterministic_and_binds_admitted_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_verifier(monkeypatch)
    request = _mock_selection_request()
    first = select_analytic_numerical_candidate(**request)
    repeated = select_analytic_numerical_candidate(**request)
    assert first["status"] == "SELECTED"
    assert first["verification_state"] == "EXPERIMENTAL"
    for candidate in first["candidate_results"]:
        assert (
            candidate["candidate_crochet_ir_sha256"]
            == candidate["verification"]["input_hashes"]["crochet_ir"]
        )
        assert candidate["verification"]["verification_profile_id"] == (
            ANALYTIC_NUMERICAL_CANDIDATE_V1.profile_id
        )
        assert [gate["gate_id"] for gate in candidate["verification"]["gates"]] == list(GATES)
    assert first["selection_evidence_sha256"] == repeated["selection_evidence_sha256"]
    assert (
        first["selection_evidence"]["request_sha256"]
        == repeated["selection_evidence"]["request_sha256"]
    )

    changed = _mock_selection_request()
    changed["numerical_run"]["comparison_policy"]["hard_thresholds"][
        "symmetric_chamfer_normalized"
    ]["value"] = 99.0
    mutated = select_analytic_numerical_candidate(**changed)
    assert (
        first["selection_evidence"]["request_sha256"]
        != mutated["selection_evidence"]["request_sha256"]
    )


def test_selection_uses_owned_request_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_verifier(monkeypatch)
    request = _mock_selection_request()
    before = deepcopy(request)
    select_analytic_numerical_candidate(**request)
    assert request == before


def test_selection_digest_excludes_only_gate_telemetry(monkeypatch: pytest.MonkeyPatch) -> None:
    import crochet_ai.analytic_selection as selection

    _patch_verifier(monkeypatch)
    verifier = selection.verify_artifacts
    elapsed = 1.0
    authoritative_observation = 0

    def with_telemetry(*args, **kwargs):
        verification = verifier(*args, **kwargs)
        for gate in verification.value["gates"]:
            gate["telemetry"] = {"elapsed_seconds": elapsed}
        verification.value["gates"][0]["linked_evidence"] = {
            "authoritative_observation": authoritative_observation
        }
        return verification

    monkeypatch.setattr(selection, "verify_artifacts", with_telemetry)
    request = _mock_selection_request()
    first = select_analytic_numerical_candidate(**request)
    elapsed = 99.0
    repeated = select_analytic_numerical_candidate(**request)
    assert first["status"] == repeated["status"] == "SELECTED"
    assert first["selected_verification"] != repeated["selected_verification"]
    assert first["candidate_results"] != repeated["candidate_results"]
    assert first["selection_evidence_sha256"] == repeated["selection_evidence_sha256"]
    authoritative_observation = 1
    changed = select_analytic_numerical_candidate(**request)
    assert changed["selection_evidence_sha256"] != first["selection_evidence_sha256"]


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("design", "E_SCHEMA"),
        ("material", "E_SCHEMA"),
        ("source", "E_PROVENANCE"),
        ("context", "E_BUDGET"),
    ],
)
def test_global_malformed_inputs_fail_before_verification(
    monkeypatch: pytest.MonkeyPatch, mutation: str, code: str
) -> None:
    called = False

    def unexpected_verifier(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("candidate verification must not run")

    import crochet_ai.analytic_selection as selection

    monkeypatch.setattr(selection, "verify_artifacts", unexpected_verifier)
    request = _mock_selection_request()
    if mutation == "design":
        request["design_spec"]["solver_options"] = "malformed"
    elif mutation == "material":
        del request["material_profile"]["revision"]
    elif mutation == "source":
        request["source_snapshot"]["source_snapshot_sha256"] = "0" * 64
    else:
        request["numerical_run"]["max_scenario_runs"] = 6
    with pytest.raises(AnalyticSelectionError) as error:
        select_analytic_numerical_candidate(**request)
    assert error.value.code == code
    assert not called


def test_tampered_native_proposal_membership_is_rejected_before_forward_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def unexpected_verifier(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("tampered search evidence must not reach candidate verification")

    import crochet_ai.analytic_selection as selection

    monkeypatch.setattr(selection, "verify_artifacts", unexpected_verifier)
    request = _mock_selection_request()
    request["search_evidence"]["candidate_proposals"].reverse()
    result = select_analytic_numerical_candidate(**request)
    assert result["status"] == "REJECTED"
    assert result["selected_crochet_ir"] is None
    assert not called


def test_two_native_cylinder_candidates_run_through_fresh_numerics() -> None:
    request = native_cylinder_selection_request()
    result = select_analytic_numerical_candidate(**request)
    assert len(result["candidate_results"]) == 2
    assert any(
        isinstance(candidate, dict)
        and "verification" in candidate
        and candidate.get("eligible") is True
        for candidate in result["candidate_results"]
    )
    assert result["physical_status"] == "UNTESTED"
    assert result["status"] == "SELECTED", result["candidate_results"]
    assert result["verification_state"] == "EXPERIMENTAL"
    assert isinstance(result["selected_crochet_ir"], dict)


def test_two_fully_passing_candidates_are_ranked_by_independent_metric_oracle():
    # A distinct small fixture tests two eligible geometries. Keep the original
    # larger rejected-plus-eligible fixture above as a real failure regression.
    request = native_cylinder_selection_request(radius=2, height=12, count=3, sectors=4)
    result = select_analytic_numerical_candidate(**request)
    assert result["status"] == "SELECTED"
    assert result["selection_scope"] == "AUDITED_EMITTED_BATCH_ONLY"
    assert all(candidate["eligible"] for candidate in result["candidate_results"])
    assert len(result["candidate_results"]) == 2
    independent_order = []
    for candidate, ir in zip(
        result["candidate_results"], request["search_evidence"]["candidate_proposals"], strict=True
    ):
        gates = candidate["verification"]["gates"]
        assert [g["gate_id"] for g in gates] == [f"V{i}" for i in range(11)]
        assert all(g["outcome"] == "PASS" for g in gates)
        metrics = next(g["metric_vector"] for g in gates if g["gate_id"] == "V7")
        # This oracle reads raw returned observations without the selector's
        # extraction/construction/ranking helpers. Both fixtures have no seams,
        # cuts, reattachments or shaping nodes by explicit raw construction.
        key = (
            Fraction(metrics["symmetric_chamfer_normalized"]),
            Fraction(metrics["robust_hausdorff_normalized"]),
            1 - Fraction(metrics["silhouette_iou_min"]),
            Fraction(metrics["surface_normal_mean_degrees"]),
            Fraction(metrics["surface_normal_p95_degrees"]),
            Fraction(metrics["section_error_normalized"]),
            Fraction(metrics["curvature_error_normalized"]),
            Fraction(metrics["relative_volume_error"]),
            Fraction(metrics["landmark_max_normalized"]),
            len(ir["stitches"]),
            len(ir["courses"]),
            0,
            candidate["candidate_crochet_ir_sha256"],
        )
        independent_order.append(key)
    expected = [row[-1] for row in sorted(independent_order)]
    assert result["selected_crochet_ir_sha256"] == expected[0]
    assert [
        entry["ranking"]["canonical_crochet_ir_sha256"]
        for entry in result["selection_evidence"]["eligible_candidate_order"]
    ] == expected


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_nonfinite_observation_cannot_enter_ranking(value):
    with pytest.raises(AnalyticSelectionError, match=r"ranking\.metric_not_binary64"):
        _fraction(value)
