from copy import deepcopy
from dataclasses import replace
from fractions import Fraction

import pytest
from conftest import resolved_artifacts

from crochet_ai.analytic_compile import CompileProvenance
from crochet_ai.analytic_counts import CountSearchBudget
from crochet_ai.analytic_geometry import MeridianNumerics
from crochet_ai.analytic_placement import PlacementBudget
from crochet_ai.analytic_solver import AnalyticRunConfig, generate_analytic
from crochet_ai.canonical import CanonicalProfile, canonical_hash
from crochet_ai.pattern import TerminologyProfile, verify_semantic_round_trip
from crochet_ai.pattern_context import PatternParseContext, PatternYarnBinding
from crochet_ai.solver_types import GenerationStatus
from crochet_ai.validation import SemanticValidator


def config() -> AnalyticRunConfig:
    return AnalyticRunConfig(
        "solver_params_fixture_minimal",
        "tension_fixture_default",
        "RELAXED_UNSTUFFED",
        MeridianNumerics(0.05, 1e-8, 10000, 1e-9),
        CountSearchBudget(32, 32, 32, 10000),
        PlacementBudget(64, 10000, 100000),
        3,
        4,
        2,
        2,
        2,
        32,
        2,
        6,
        6,
        6,
        6,
        Fraction(1, 12),
        2,
        200,
    )


def inputs():
    design, material = resolved_artifacts()
    design["dimensions"]["measurements"][0]["value_mm"] = 4
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    design["solver_options"]["max_candidate_evaluations"] = 2
    return design, material


PROVENANCE = CompileProvenance("a" * 40, "b" * 64, (("test_profile", "synthetic"),))


def test_missing_source_provenance_is_rejected_before_any_search() -> None:
    design, material = inputs()
    run = replace(config(), initial_ring_min=100, initial_ring_max=101)
    batch = generate_analytic(design, material, run, replace(PROVENANCE, software_commit=""))
    assert batch.status == GenerationStatus.INVALID_SOLVER_INPUT
    assert batch.reason == "compiler.source_provenance"
    assert batch.count_transition_evaluations == batch.completed_course_hypotheses == 0


def test_sphere_pipeline_emits_complete_deterministic_unverified_candidates() -> None:
    design, material = inputs()
    untouched = deepcopy(design), deepcopy(material)
    batch = generate_analytic(design, material, config(), PROVENANCE)
    assert batch.status == GenerationStatus.CANDIDATES_EMITTED, batch.reason
    assert len(batch.candidates) == 2 and batch.completed_course_hypotheses == 2
    validator = SemanticValidator(
        material_profiles={material["profile_id"]: material},
        design_specs={design["design_spec_id"]: design},
    )
    context = PatternParseContext(
        design, (PatternYarnBinding("Yarn A", material, "Natural", "#C8B08A"),)
    )
    rerun = generate_analytic(design, material, config(), PROVENANCE)
    for candidate, repeat in zip(batch.candidates, rerun.candidates, strict=True):
        value = candidate.crochet_ir.to_dict()
        assert validator.validate_crochet_ir(value).ok
        assert canonical_hash(
            value, CanonicalProfile.CROCHET_IR, validator=validator
        ) == canonical_hash(
            repeat.crochet_ir.to_dict(), CanonicalProfile.CROCHET_IR, validator=validator
        )
        assert verify_semantic_round_trip(
            value, TerminologyProfile.DE_DE, context=context, validator=validator
        ).ok
    assert (design, material) == untouched


@pytest.mark.parametrize(
    "kind",
    [
        "response",
        "loading",
        "profile",
        "hypotheses",
        "candidates",
        "count",
        "placement",
        "pairs",
        "empty",
    ],
)
def test_pipeline_failures_never_claim_verified_success(kind: str) -> None:
    design, material = inputs()
    run = config()
    if kind == "response":
        run = replace(run, tension_profile_id="missing")
    elif kind == "loading":
        run = replace(run, fabric_state="STUFFED")
    elif kind == "profile":
        run = replace(run, parameter_profile_id="wrong")
    elif kind == "hypotheses":
        run = replace(run, max_course_hypotheses=1)
    elif kind == "candidates":
        run = replace(run, max_emitted_candidates=1)
    elif kind == "count":
        run = replace(run, count_budget=replace(run.count_budget, max_transition_evaluations=1))
    elif kind == "placement":
        run = replace(
            run, placement_budget=replace(run.placement_budget, max_transition_evaluations=1)
        )
    elif kind == "pairs":
        run = replace(run, placement_budget=replace(run.placement_budget, max_pair_evaluations=1))
    else:
        run = replace(run, initial_ring_min=100, initial_ring_max=101)
    batch = generate_analytic(design, material, run, PROVENANCE)
    if kind in {"hypotheses", "candidates"}:
        assert batch.status == GenerationStatus.SEARCH_BUDGET_EXHAUSTED
        assert len(batch.candidates) == 1
    else:
        assert not batch.candidates
        expected = (
            GenerationStatus.NO_FEASIBLE_CONSTRUCTION
            if kind == "empty"
            else GenerationStatus.NOT_APPLICABLE
            if kind == "loading"
            else GenerationStatus.INVALID_SOLVER_INPUT
            if kind in {"response", "profile"}
            else GenerationStatus.SEARCH_BUDGET_EXHAUSTED
        )
        assert batch.status == expected, batch.reason
    if kind == "pairs":
        assert batch.placement_pair_evaluations == 1


def test_forbidden_shaping_is_excluded_from_search_not_silently_emitted() -> None:
    design, material = inputs()
    design["difficulty_constraints"]["allowed_shaping"] = []
    batch = generate_analytic(design, material, config(), PROVENANCE)
    assert batch.status == GenerationStatus.CANDIDATES_EMITTED
    for candidate in batch.candidates:
        assert all(s["shaping"] == "PLAIN" for s in candidate.crochet_ir.to_dict()["stitches"])
