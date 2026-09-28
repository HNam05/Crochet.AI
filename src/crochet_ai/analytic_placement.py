"""Global phase choice for a fixed count schedule and one-course shaping history."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise

from .analytic_compile import balanced_course
from .solver_types import GenerationError, GenerationStatus


@dataclass(frozen=True, slots=True)
class PlacementBudget:
    max_variants_per_transition: int
    max_transition_evaluations: int
    max_pair_evaluations: int


@dataclass(frozen=True, slots=True)
class PlacementResult:
    phases: tuple[int, ...]
    stacking_pairs: int
    proximity_penalty_turns: Fraction
    transition_evaluations: int
    pair_evaluations: int


def choose_phases(
    counts: tuple[int, ...], minimum_separation_turns: Fraction, budget: PlacementBudget
) -> PlacementResult:
    if not (
        isinstance(counts, tuple)
        and 1 <= len(counts) <= 512
        and all(type(n) is int and 1 <= n <= 512 for n in counts)
        and isinstance(minimum_separation_turns, Fraction)
        and 0 <= minimum_separation_turns <= Fraction(1, 2)
        and minimum_separation_turns.denominator.bit_length() <= 128
        and type(budget.max_variants_per_transition) is int
        and 1 <= budget.max_variants_per_transition <= 512
        and type(budget.max_transition_evaluations) is int
        and 0 <= budget.max_transition_evaluations <= 2_000_000
        and type(budget.max_pair_evaluations) is int
        and 0 <= budget.max_pair_evaluations <= 2_000_000
    ):
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "placement.input")
    # State = last phase's shaping angles, label = additive penalties and full
    # phase trace. Identical angle states have identical future costs.
    states: dict[tuple[Fraction, ...], tuple[int, Fraction, tuple[int, ...]]] = {
        (): (0, Fraction(0), ())
    }
    used = 0
    pairs_used = 0

    def exhausted(reason: str, consumed: int) -> GenerationError:
        return GenerationError(
            GenerationStatus.SEARCH_BUDGET_EXHAUSTED,
            reason,
            consumed,
            work={"placement_transitions": used, "placement_pairs": pairs_used},
        )

    for before, after in pairwise(counts):
        variants = before if before != after else 1
        if variants > budget.max_variants_per_transition:
            raise exhausted("placement.variants", used)
        next_states: dict[tuple[Fraction, ...], tuple[int, Fraction, tuple[int, ...]]] = {}
        for phase in range(variants):
            plan = balanced_course(before, after, phase)
            angles = tuple(
                sorted(
                    (
                        Fraction(2 * stitch.base_indices[0] + len(stitch.base_indices), 2 * before)
                        % 1
                    )
                    for stitch in plan
                    if len(stitch.base_indices) != stitch.top_count
                )
            )
            for history, (stack, penalty, trace) in sorted(states.items()):
                if used == budget.max_transition_evaluations:
                    raise exhausted("placement.transitions", used)
                used += 1
                extra_stack = 0
                extra_penalty = Fraction(0)
                for angle in angles:
                    for previous in history:
                        if pairs_used == budget.max_pair_evaluations:
                            raise exhausted("placement.pairs", pairs_used)
                        pairs_used += 1
                        delta = abs(angle - previous)
                        distance = min(delta, 1 - delta)
                        extra_stack += distance == 0
                        extra_penalty += max(Fraction(0), minimum_separation_turns - distance)
                label = (stack + extra_stack, penalty + extra_penalty, (*trace, phase))
                if angles not in next_states or label < next_states[angles]:
                    next_states[angles] = label
        states = next_states
    stack, penalty, phases = min(states.values())
    return PlacementResult(phases, stack, penalty, used, pairs_used)
