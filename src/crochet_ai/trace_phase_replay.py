"""Independent bounded phase replay for ANALYTIC_SEARCH_TRACE_V1."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise
from typing import Any

from .trace_verification_types import (
    TraceAuditInputError,
    TraceReplayBudgetExceeded,
    TraceReplayWork,
)

MAX_VARIANTS = 512
MAX_EVALUATIONS = 2_000_000


@dataclass(frozen=True, slots=True)
class PhaseReplayBudget:
    max_variants_per_transition: int = 128
    max_transition_evaluations: int = 100_000
    max_pair_evaluations: int = 1_000_000

    def __post_init__(self) -> None:
        if (
            type(self.max_variants_per_transition) is not int
            or not 1 <= self.max_variants_per_transition <= MAX_VARIANTS
            or type(self.max_transition_evaluations) is not int
            or not 0 <= self.max_transition_evaluations <= MAX_EVALUATIONS
            or type(self.max_pair_evaluations) is not int
            or not 0 <= self.max_pair_evaluations <= MAX_EVALUATIONS
        ):
            raise TraceAuditInputError("trace_audit.phase_budget")


@dataclass(frozen=True, slots=True)
class PhaseReplayResult:
    status: str
    reason: str
    layers: tuple[dict[str, Any], ...]
    used_transition_evaluations: int
    used_pair_evaluations: int
    phases: tuple[int, ...] | None = None
    stacking_pairs: int | None = None
    proximity_penalty_turns: Fraction | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"layers": [dict(layer) for layer in self.layers]}
        if self.status == "PASS":
            assert self.phases is not None
            assert self.stacking_pairs is not None
            assert self.proximity_penalty_turns is not None
            result.update(
                phases=list(self.phases),
                stacking_pairs=self.stacking_pairs,
                proximity_penalty_turns=(
                    f"{self.proximity_penalty_turns.numerator}/"
                    f"{self.proximity_penalty_turns.denominator}"
                ),
            )
        return result


def _event_angles(before: int, after: int, phase: int) -> tuple[Fraction, ...]:
    """Build shaping centers from integer spacing and an independent cursor."""
    delta = after - before
    event_count = abs(delta)
    if event_count == 0:
        return ()
    decrease = delta < 0
    operations = before - (event_count if decrease else 0)
    if event_count > operations:
        raise TraceAuditInputError("trace_audit.phase_arity")
    centers: list[Fraction] = []
    cursor = phase
    for ordinal in range(operations):
        shaped = ((ordinal + 1) * event_count // operations) > (ordinal * event_count // operations)
        if shaped:
            base_ordinal = cursor
            arity = 2 if decrease else 1
            centers.append(Fraction(2 * base_ordinal + arity, 2 * before) % 1)
        cursor += 2 if shaped and decrease else 1
    if cursor - phase != before:
        raise TraceAuditInputError("trace_audit.phase_cursor")
    return tuple(sorted(centers))


def replay_phase_search(
    counts: tuple[int, ...],
    separation: Fraction,
    budget: PhaseReplayBudget,
    *,
    work: TraceReplayWork,
) -> PhaseReplayResult:
    if not (
        isinstance(counts, tuple)
        and 1 <= len(counts) <= 512
        and all(type(value) is int and 1 <= value <= 512 for value in counts)
        and isinstance(separation, Fraction)
        and 0 <= separation <= Fraction(1, 2)
        and separation.denominator.bit_length() <= 128
        and isinstance(budget, PhaseReplayBudget)
        and isinstance(work, TraceReplayWork)
    ):
        raise TraceAuditInputError("trace_audit.phase_input")

    # State is prior shaping centers; values retain the exact best history label.
    states: dict[tuple[Fraction, ...], tuple[int, Fraction, tuple[int, ...]]] = {
        (): (0, Fraction(0), ())
    }
    layers: list[dict[str, Any]] = []
    used_transitions = 0
    used_pairs = 0

    def interrupted(reason: str) -> PhaseReplayResult:
        return PhaseReplayResult(
            "SEARCH_BUDGET_EXHAUSTED", reason, tuple(layers), used_transitions, used_pairs
        )

    for index, (before, after) in enumerate(pairwise(counts)):
        variants = before if before != after else 1
        input_count = len(states)
        next_states: dict[tuple[Fraction, ...], tuple[int, Fraction, tuple[int, ...]]] = {}
        layer_transitions = 0
        layer_pairs = 0

        def record(
            completed: bool,
            transition_index: int,
            variant_total: int,
            state_count: int,
            output_count: int,
            transition_work: int,
            pair_work: int,
        ) -> None:
            layers.append(
                {
                    "transition": transition_index,
                    "variants": variant_total,
                    "input_states": state_count,
                    "output_states": output_count,
                    "transition_evaluations": transition_work,
                    "pair_evaluations": pair_work,
                    "completed": completed,
                }
            )

        if variants > budget.max_variants_per_transition:
            record(False, index, variants, input_count, 0, 0, 0)
            return interrupted("placement.variants")
        for phase in range(variants):
            angles = _event_angles(before, after, phase)
            for history, (stack, penalty, path) in sorted(states.items()):
                if used_transitions >= budget.max_transition_evaluations:
                    record(
                        False,
                        index,
                        variants,
                        input_count,
                        len(next_states),
                        layer_transitions,
                        layer_pairs,
                    )
                    return interrupted("placement.transitions")
                try:
                    work.spend()
                except TraceReplayBudgetExceeded:
                    record(
                        False,
                        index,
                        variants,
                        input_count,
                        len(next_states),
                        layer_transitions,
                        layer_pairs,
                    )
                    return interrupted("trace_audit.replay_budget_exhausted")
                used_transitions += 1
                layer_transitions += 1
                extra_stack = 0
                extra_penalty = Fraction(0)
                for angle in angles:
                    for previous in history:
                        if used_pairs >= budget.max_pair_evaluations:
                            record(
                                False,
                                index,
                                variants,
                                input_count,
                                len(next_states),
                                layer_transitions,
                                layer_pairs,
                            )
                            return interrupted("placement.pairs")
                        try:
                            work.spend()
                        except TraceReplayBudgetExceeded:
                            record(
                                False,
                                index,
                                variants,
                                input_count,
                                len(next_states),
                                layer_transitions,
                                layer_pairs,
                            )
                            return interrupted("trace_audit.replay_budget_exhausted")
                        used_pairs += 1
                        layer_pairs += 1
                        delta = abs(angle - previous)
                        distance = min(delta, 1 - delta)
                        extra_stack += distance == 0
                        extra_penalty += max(Fraction(0), separation - distance)
                label = (stack + extra_stack, penalty + extra_penalty, (*path, phase))
                if angles not in next_states or label < next_states[angles]:
                    next_states[angles] = label
        states = next_states
        record(
            True, index, variants, input_count, len(next_states), layer_transitions, layer_pairs
        )

    best = min(states.values())
    return PhaseReplayResult(
        "PASS",
        "phase.complete",
        tuple(layers),
        used_transitions,
        used_pairs,
        best[2],
        best[0],
        best[1],
    )
