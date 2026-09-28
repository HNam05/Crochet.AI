"""Executable closed-pole analytic proposals with explicit, bounded run configuration.

No returned candidate has passed independent physical/geometry verification.
Generation and verification outcomes must remain separate at the API boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from fractions import Fraction
from math import ceil, floor, isfinite, pi
from typing import Any

from .analytic_compile import CompileProvenance, compile_closed_schedule
from .analytic_counts import (
    CountSearchBudget,
    CountSearchInput,
    CountSearchResult,
    CountSearchStatus,
    CountWindow,
    search_counts,
)
from .analytic_geometry import MeridianNumerics, MeridianPoint, decode_meridian
from .analytic_placement import PlacementBudget, PlacementResult, choose_phases
from .canonical import CanonicalProfile, canonical_hash
from .diagnostics import ArtifactValidationError
from .models import CrochetIR
from .solver_types import GenerationError, GenerationStatus
from .validation import SemanticValidator


@dataclass(frozen=True, slots=True)
class AnalyticRunConfig:
    parameter_profile_id: str
    tension_profile_id: str
    fabric_state: str
    numerics: MeridianNumerics
    count_budget: CountSearchBudget
    placement_budget: PlacementBudget
    min_courses: int
    max_courses: int
    max_course_hypotheses: int
    count_window_radius: int
    min_count: int
    max_count: int
    initial_ring_min: int
    initial_ring_max: int
    max_terminal_count: int
    max_increases_per_course: int
    max_decreases_per_course: int
    minimum_shaping_separation_turns: Fraction
    max_emitted_candidates: int
    max_stitches: int

    def validate(self) -> None:
        self.numerics.validate()
        integer_bounds = {
            "min_courses": (1, 512),
            "max_courses": (self.min_courses, 512),
            "max_course_hypotheses": (1, 512),
            "count_window_radius": (0, 127),
            "min_count": (1, 512),
            "max_count": (self.min_count, 512),
            "initial_ring_min": (2, 512),
            "initial_ring_max": (self.initial_ring_min, 512),
            "max_terminal_count": (1, 512),
            "max_increases_per_course": (0, 512),
            "max_decreases_per_course": (0, 512),
            "max_emitted_candidates": (1, 128),
            "max_stitches": (1, 10_000),
        }
        for name, (low, high) in integer_bounds.items():
            value = getattr(self, name)
            if type(value) is not int or type(low) is not int or not low <= value <= high:
                raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, f"config.{name}")
        if self.fabric_state not in {"RELAXED_UNSTUFFED", "BLOCKED_UNSTUFFED", "STUFFED"}:
            raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "config.fabric_state")
        if not self.parameter_profile_id or not self.tension_profile_id:
            raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "config.profile_identity")
        for limit in (
            self.placement_budget.max_transition_evaluations,
            self.placement_budget.max_pair_evaluations,
        ):
            if type(limit) is not int or limit < 1:
                raise GenerationError(
                    GenerationStatus.INVALID_SOLVER_INPUT, "config.placement_budget"
                )
        # Validate placement budgets even when there are no shaping transitions.
        choose_phases((2,), self.minimum_shaping_separation_turns, self.placement_budget)
        check = search_counts(
            CountSearchInput(
                (Fraction(2),),
                Fraction(1),
                (CountWindow(2, 2),),
                self.max_increases_per_course,
                self.max_decreases_per_course,
                self.count_budget,
            )
        )
        if check.status == CountSearchStatus.INVALID_SOLVER_INPUT:
            raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, check.reason)


@dataclass(frozen=True, slots=True)
class AnalyticCandidate:
    crochet_ir: CrochetIR
    count_search: CountSearchResult
    placement: PlacementResult
    samples: tuple[MeridianPoint, ...]
    course_spacing_residual_mm: float
    material_response_id: str


@dataclass(frozen=True, slots=True)
class AnalyticGenerationResult:
    status: GenerationStatus
    reason: str
    candidates: tuple[AnalyticCandidate, ...]
    completed_course_hypotheses: int
    count_transition_evaluations: int
    placement_transition_evaluations: int
    placement_pair_evaluations: int


def _parameters(config: AnalyticRunConfig) -> tuple[tuple[str, str | int | float | bool], ...]:
    result: list[tuple[str, str | int | float | bool]] = []
    for field in fields(config):
        value = getattr(config, field.name)
        if field.name in {"numerics", "count_budget", "placement_budget"}:
            result.extend(
                (f"{field.name}.{nested.name}", getattr(value, nested.name))
                for nested in fields(value)
            )
        elif isinstance(value, Fraction):
            result.append((field.name, f"{value.numerator}/{value.denominator}"))
        else:
            result.append((field.name, value))
    return tuple(result)


def generate_analytic(
    design: dict[str, Any],
    material: dict[str, Any],
    config: AnalyticRunConfig,
    provenance: CompileProvenance,
) -> AnalyticGenerationResult:
    """Generate complete unverified candidates; preserve partial batch on exhaustion."""
    candidates: list[AnalyticCandidate] = []
    completed = count_used = placement_used = pairs_used = 0

    def result(status: GenerationStatus, reason: str) -> AnalyticGenerationResult:
        return AnalyticGenerationResult(
            status, reason, tuple(candidates), completed, count_used, placement_used, pairs_used
        )

    try:
        provenance.validate()
        config.validate()
        validator = SemanticValidator(
            material_profiles={material.get("profile_id", ""): material},
            design_specs={design.get("design_spec_id", ""): design},
        )
        for report in (
            validator.validate_material_profile(material),
            validator.validate_design_spec(design),
        ):
            if not report.ok:
                raise ArtifactValidationError(report)
        if config.parameter_profile_id != design["solver_options"]["parameter_profile_id"]:
            raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "solver.parameter_profile")
        if "ANALYTIC" not in design["solver_options"]["allowed_solver_families"]:
            raise GenerationError(GenerationStatus.NOT_APPLICABLE, "solver.family_disallowed")
        if config.max_emitted_candidates > design["solver_options"]["max_candidate_evaluations"]:
            raise GenerationError(
                GenerationStatus.INVALID_SOLVER_INPUT, "solver.design_candidate_budget"
            )
        bound = design["material_profile"]
        binding_hash = (
            canonical_hash(bound["profile"], CanonicalProfile.MATERIAL_PROFILE)
            if bound["binding_type"] == "INLINE"
            else bound["sha256"]
        )
        if canonical_hash(material, CanonicalProfile.MATERIAL_PROFILE) != binding_hash:
            raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "solver.material_binding")
        if design["project_type"] != "AMIGURUMI_3D":
            raise GenerationError(GenerationStatus.NOT_APPLICABLE, "solver.domain")
        if (design["domain_constraints"]["stuffing_level"] == "NONE") == (
            config.fabric_state == "STUFFED"
        ):
            raise GenerationError(GenerationStatus.NOT_APPLICABLE, "solver.fabric_loading_mismatch")
        responses = [
            r
            for r in material["calibration_responses"]
            if r["measurement_conditions"]
            == {
                "canonical_stitch_type": "SINGLE_CROCHET",
                "course_mode": "CYCLIC",
                "tension_profile_id": config.tension_profile_id,
                "fabric_state": config.fabric_state,
            }
        ]
        if len(responses) != 1:
            raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "solver.material_response")
        response = responses[0]
        gauge = response["effective_gauge"]
        stitch_pitch = Fraction(float(gauge["effective_stitch_pitch_mm"]))
        course_pitch = float(gauge["effective_course_pitch_mm"])
        meridian = decode_meridian(design, config.numerics, validator=validator)
        if (meridian.start_kind, meridian.end_kind) != ("CLOSED_POLE", "CLOSED_POLE"):
            raise GenerationError(GenerationStatus.NOT_APPLICABLE, "solver.closed_poles_only")
        if any(name.startswith(("solver.", "run.")) for name, _ in provenance.parameters):
            raise GenerationError(
                GenerationStatus.INVALID_SOLVER_INPUT, "solver.reserved_provenance_parameter"
            )
        recorded = replace(
            provenance,
            parameters=provenance.parameters
            + tuple((f"run.{k}", v) for k, v in _parameters(config)),
        )
        # Enumerate the complete explicit course-count domain in ascending order.
        for course_count in range(config.min_courses, config.max_courses + 1):
            if completed == config.max_course_hypotheses:
                return result(GenerationStatus.SEARCH_BUDGET_EXHAUSTED, "budget.course_hypotheses")
            if len(candidates) == config.max_emitted_candidates:
                return result(GenerationStatus.SEARCH_BUDGET_EXHAUSTED, "budget.emitted_candidates")
            samples = tuple(
                meridian.sample(Fraction(2 * i + 1, 2 * course_count)) for i in range(course_count)
            )
            circumferences = tuple(2 * pi * p.radius_mm for p in samples)
            if not all(isfinite(c) for c in circumferences):
                raise GenerationError(GenerationStatus.NUMERICAL_FAILURE, "solver.circumference")
            windows = []
            for i, circumference in enumerate(circumferences):
                q = Fraction(circumference) / stitch_pitch
                low = max(config.min_count, floor(q) - config.count_window_radius)
                high = min(config.max_count, ceil(q) + config.count_window_radius)
                if i == 0:
                    low, high = (
                        max(low, config.initial_ring_min),
                        min(high, config.initial_ring_max),
                    )
                if i == course_count - 1:
                    high = min(high, config.max_terminal_count)
                if low > high:
                    break
                windows.append(CountWindow(low, high))
            if len(windows) != course_count:
                completed += 1
                continue
            if count_used == config.count_budget.max_transition_evaluations:
                return result(GenerationStatus.SEARCH_BUDGET_EXHAUSTED, "budget.count_transitions")
            count_budget = replace(
                config.count_budget,
                max_transition_evaluations=config.count_budget.max_transition_evaluations
                - count_used,
            )
            search = search_counts(
                CountSearchInput(
                    tuple(Fraction(c) for c in circumferences),
                    stitch_pitch,
                    tuple(windows),
                    config.max_increases_per_course
                    if "INCREASE" in design["difficulty_constraints"]["allowed_shaping"]
                    else 0,
                    config.max_decreases_per_course
                    if "DECREASE" in design["difficulty_constraints"]["allowed_shaping"]
                    else 0,
                    count_budget,
                )
            )
            count_used += search.transition_evaluations
            if search.status in {
                CountSearchStatus.INVALID_SOLVER_INPUT,
                CountSearchStatus.SEARCH_BUDGET_EXHAUSTED,
            }:
                return result(GenerationStatus(search.status.value), search.reason)
            if search.status == CountSearchStatus.NO_FEASIBLE_CONSTRUCTION:
                completed += 1
                continue
            placement_budget = replace(
                config.placement_budget,
                max_transition_evaluations=config.placement_budget.max_transition_evaluations
                - placement_used,
                max_pair_evaluations=config.placement_budget.max_pair_evaluations - pairs_used,
            )
            placement = choose_phases(
                search.counts, config.minimum_shaping_separation_turns, placement_budget
            )
            placement_used += placement.transition_evaluations
            pairs_used += placement.pair_evaluations
            candidate_provenance = replace(
                recorded,
                parameters=(
                    *recorded.parameters,
                    ("solver.course_count", course_count),
                    ("solver.count_transitions", search.transition_evaluations),
                    ("solver.placement_transitions", placement.transition_evaluations),
                    ("solver.placement_pairs", placement.pair_evaluations),
                    ("solver.arc_panels", meridian.arc_panels),
                    ("solver.arc_error_bound_mm", meridian.exact_arithmetic_arc_error_bound_mm),
                    ("solver.material_response_id", response["response_id"]),
                ),
            )
            value = compile_closed_schedule(
                design,
                material,
                search.counts,
                placement.phases,
                candidate_provenance,
                max_stitches=config.max_stitches,
            )
            candidates.append(
                AnalyticCandidate(
                    CrochetIR.from_dict(value),
                    search,
                    placement,
                    samples,
                    meridian.length_mm / course_count - course_pitch,
                    response["response_id"],
                )
            )
            completed += 1
    except GenerationError as error:
        placement_used += error.work.get("placement_transitions", 0)
        pairs_used += error.work.get("placement_pairs", 0)
        return result(error.status, error.reason)
    return result(
        GenerationStatus.CANDIDATES_EMITTED
        if candidates
        else GenerationStatus.NO_FEASIBLE_CONSTRUCTION,
        "domain.complete",
    )
