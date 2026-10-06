from fractions import Fraction
from itertools import pairwise, product

import pytest

from crochet_ai.trace_phase_replay import PhaseReplayBudget, replay_phase_search
from crochet_ai.trace_verification_types import TraceAuditInputError, TraceReplayWork


def test_replay_matches_independent_exhaustive_phase_oracle() -> None:
    separation = Fraction(1, 5)
    labels = []
    # Explicit centers from hand enumeration: 4->6 increases at bases 1,3;
    # 6->4 decreases consume pairs (1,2),(4,5); 4->6 repeats the first layout.
    layouts = (
        (Fraction(3, 8), Fraction(7, 8)),
        (Fraction(1, 3), Fraction(5, 6)),
    )
    for phases in product(range(4), range(6)):
        shifted = [
            tuple(sorted((angle + Fraction(phase, count)) % 1 for angle in layout))
                for layout, phase, count in zip(layouts, phases, (4, 6), strict=True)
        ]
        distances = [
            min(abs(a - b), 1 - abs(a - b))
            for left, right in pairwise(shifted)
            for a in left
            for b in right
        ]
        labels.append(
            (
                sum(distance == 0 for distance in distances),
                sum((max(Fraction(0), separation - d) for d in distances), Fraction(0)),
                phases,
            )
        )
    replay = replay_phase_search(
        (4, 6, 4), separation, PhaseReplayBudget(6, 1000, 1000), work=TraceReplayWork()
    )
    assert (replay.stacking_pairs, replay.proximity_penalty_turns, replay.phases) == min(labels)


def test_decrease_arity_matches_manual_orbit_oracle() -> None:
    separation = Fraction(1, 12)
    base = (Fraction(1, 6), Fraction(1, 2), Fraction(5, 6))
    labels = []
    for increase_phase, decrease_phase in product(range(3), range(6)):
        increasing = tuple(
            sorted((angle + Fraction(increase_phase, 3)) % 1 for angle in base)
        )
        decreasing = tuple(
            sorted((angle + Fraction(decrease_phase, 6)) % 1 for angle in base)
        )
        distances = [
            min(abs(left - right), 1 - abs(left - right))
            for left in increasing
            for right in decreasing
        ]
        labels.append(
            (
                sum(distance == 0 for distance in distances),
                sum((max(Fraction(0), separation - d) for d in distances), Fraction(0)),
                (increase_phase, decrease_phase),
            )
        )
    replay = replay_phase_search(
        (3, 6, 3), separation, PhaseReplayBudget(6, 1000, 1000), work=TraceReplayWork()
    )
    assert min(labels) == (0, Fraction(0), (0, 1))
    assert (replay.stacking_pairs, replay.proximity_penalty_turns, replay.phases) == min(labels)


def test_exact_work_records_and_pair_interruption_have_no_schedule() -> None:
    complete = replay_phase_search(
        (2, 3, 2), Fraction(0), PhaseReplayBudget(8, 100, 100), work=TraceReplayWork()
    )
    assert (complete.used_transition_evaluations, complete.used_pair_evaluations) == (8, 6)
    assert complete.status == "PASS"
    assert complete.to_dict()["layers"] == [
        {
            "transition": 0,
            "variants": 2,
            "input_states": 1,
            "output_states": 2,
            "transition_evaluations": 2,
            "pair_evaluations": 0,
            "completed": True,
        },
        {
            "transition": 1,
            "variants": 3,
            "input_states": 2,
            "output_states": 3,
            "transition_evaluations": 6,
            "pair_evaluations": 6,
            "completed": True,
        },
    ]

    partial = replay_phase_search(
        (2, 3, 2), Fraction(0), PhaseReplayBudget(8, 100, 3), work=TraceReplayWork()
    )
    assert (partial.used_transition_evaluations, partial.used_pair_evaluations) == (6, 3)
    assert partial.layers[-1]["completed"] is False
    assert partial.to_dict().get("phases") is None
    assert "stacking_pairs" not in partial.to_dict()


def test_zero_budgets_and_unchanged_counts() -> None:
    empty = replay_phase_search(
        (2,), Fraction(0), PhaseReplayBudget(1, 0, 0), work=TraceReplayWork()
    )
    assert empty.status == "PASS"
    assert empty.layers == ()
    assert empty.phases == ()
    assert (empty.used_transition_evaluations, empty.used_pair_evaluations) == (0, 0)

    interrupted = replay_phase_search(
        (2, 3), Fraction(0), PhaseReplayBudget(1, 1, 1), work=TraceReplayWork(limit=1)
    )
    assert interrupted.status == "SEARCH_BUDGET_EXHAUSTED"
    assert interrupted.layers[0]["completed"] is False
    assert interrupted.to_dict().get("phases") is None


@pytest.mark.parametrize(
    "values",
    [
        (0, 0, 0),
        (513, 0, 0),
        (1, -1, 0),
        (1, 0, 2_000_001),
    ],
)
def test_budget_rejects_values_outside_owned_ceilings(values: tuple[int, int, int]) -> None:
    with pytest.raises(TraceAuditInputError):
        budget = PhaseReplayBudget(*values)
        replay_phase_search((2, 3), Fraction(0), budget, work=TraceReplayWork())
