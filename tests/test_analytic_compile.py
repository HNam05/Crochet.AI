from copy import deepcopy

import pytest
from conftest import resolved_artifacts
from hypothesis import given, settings
from hypothesis import strategies as st

from crochet_ai.analytic_compile import CompileProvenance, balanced_course, compile_closed_schedule
from crochet_ai.equivalence import semantic_bytes
from crochet_ai.pattern import TerminologyProfile, export_pattern, parse_pattern
from crochet_ai.pattern_context import PatternParseContext, PatternYarnBinding
from crochet_ai.solver_types import GenerationError, GenerationStatus
from crochet_ai.validation import SemanticValidator


@given(st.integers(1, 64), st.integers(1, 64), st.integers(0, 63))
@settings(max_examples=150, deadline=None)
def test_balanced_course_exact_coverage_and_spacing(before: int, after: int, phase: int) -> None:
    phase %= before
    if not (before + 1) // 2 <= after <= 2 * before:
        with pytest.raises(GenerationError) as error:
            balanced_course(before, after, phase)
        assert error.value.status == GenerationStatus.NO_FEASIBLE_CONSTRUCTION
        return
    plan = balanced_course(before, after, phase)
    coverage = [index for stitch in plan for index in stitch.base_indices]
    assert coverage == [(phase + i) % before for i in range(before)]
    assert sum(stitch.top_count for stitch in plan) == after
    shaped = sorted(
        stitch.base_indices[0] for stitch in plan if len(stitch.base_indices) != stitch.top_count
    )
    assert len(shaped) == abs(after - before)
    if shaped:
        gaps = [
            (shaped[(i + 1) % len(shaped)] - shaped[i]) % before or before
            for i in range(len(shaped))
        ]
        assert max(gaps) - min(gaps) <= 1


@pytest.mark.parametrize(
    "counts,phases", [((6,), ()), ((6, 12, 6), (0, 11)), ((5, 8, 4, 3), (2, 7, 1)), ((2, 1), (1,))]
)
@pytest.mark.parametrize("terminology", tuple(TerminologyProfile))
def test_direct_compiler_independent_validation_and_text_round_trip(
    counts: tuple[int, ...], phases: tuple[int, ...], terminology: TerminologyProfile
) -> None:
    design, material = resolved_artifacts()
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE", "DECREASE"]
    original = deepcopy(design)
    value = compile_closed_schedule(
        design,
        material,
        counts,
        phases,
        CompileProvenance("a" * 40, "b" * 64, (("test_profile", "synthetic"),)),
        max_stitches=100,
    )
    assert design == original
    validator = SemanticValidator(
        material_profiles={material["profile_id"]: material},
        design_specs={design["design_spec_id"]: design},
    )
    assert validator.validate_crochet_ir(value).ok
    context = PatternParseContext(
        design, (PatternYarnBinding("Yarn A", material, "Natural", "#C8B08A"),)
    )
    rebound = parse_pattern(
        export_pattern(value, terminology, validator=validator), context=context
    )
    assert semantic_bytes(value, validator=validator) == semantic_bytes(
        rebound, validator=validator
    )
    assert value["provenance"]["solver_parameters_sha256"] != "0" * 64
    assert all(
        d["parameter_sha256"] == value["provenance"]["solver_parameters_sha256"]
        for d in value["derivations"]
    )


def test_compiler_honors_stitch_budget_and_design_techniques() -> None:
    design, material = resolved_artifacts()
    provenance = CompileProvenance("a" * 40, "b" * 64, ())
    with pytest.raises(GenerationError) as error:
        compile_closed_schedule(design, material, (6, 12), (0,), provenance, max_stitches=100)
    assert error.value.reason == "compiler.design_techniques"
    design["difficulty_constraints"]["allowed_construction_operations"].append("CLOSE")
    design["difficulty_constraints"]["allowed_shaping"] = ["INCREASE"]
    with pytest.raises(GenerationError) as error:
        compile_closed_schedule(design, material, (6, 12), (0,), provenance, max_stitches=11)
    assert error.value.status == GenerationStatus.SEARCH_BUDGET_EXHAUSTED
