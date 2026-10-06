from fractions import Fraction
from itertools import pairwise, product

import pytest

from crochet_ai.trace_count_replay import CountReplayBudget, replay_count_search
from crochet_ai.trace_verification_types import (
    TraceAuditInputError,
    TraceReplayBudgetExceeded,
    TraceReplayWork,
)


def _budget(edges: int = 1000, states: int = 256, courses: int = 512, values: int = 256):
    return CountReplayBudget(courses, values, states, edges)


@pytest.mark.parametrize(
    "args",
    [
        (0, 1, 1, 1),
        (513, 1, 1, 1),
        (1, True, 1, 1),
        (1, 1, 257, 1),
        (1, 1, 1, 2_000_001),
    ],
)
def test_budget_rejects_non_native_or_out_of_ceiling_values(args):
    with pytest.raises(TraceAuditInputError, match=r"trace_audit.count_budget"):
        CountReplayBudget(*args)


def _oracle(circumferences, pitch, windows, max_i, max_d):
    paths = []
    for path in product(*(range(lo, hi + 1) for lo, hi in windows)):
        transitions = []
        for before, after in pairwise(path):
            inc, dec = max(after - before, 0), max(before - after, 0)
            plain = before - inc - 2 * dec
            if plain < 0 or inc > max_i or dec > max_d:
                break
            transitions.append((plain, inc, dec))
        else:
            residuals = [abs(n * pitch - c) for n, c in zip(path, circumferences, strict=True)]
            paths.append(
                (
                    (
                        max(residuals),
                        sum((r * r for r in residuals), Fraction()),
                        sum(i + d for _, i, d in transitions),
                        path,
                    ),
                    transitions,
                )
            )
    return min(paths, default=None)


@pytest.mark.parametrize(
    "windows, max_i, max_d",
    [(((1, 3), (1, 3)), 1, 1), (((1, 4), (1, 4), (1, 4)), 2, 2), (((2, 3), (2, 3)), 1, 1)],
)
def test_replay_matches_independent_exhaustive_path_oracle(windows, max_i, max_d):
    circumferences = tuple(Fraction(x) for x in range(2, 2 + len(windows)))
    actual = replay_count_search(
        circumferences, Fraction(1), windows, max_i, max_d, _budget(), work=TraceReplayWork()
    )
    expected = _oracle(circumferences, Fraction(1), windows, max_i, max_d)
    if expected is None:
        assert actual.count_status == "NO_FEASIBLE_CONSTRUCTION"
    else:
        objective, transitions = expected
        assert actual.count_status == "OPTIMAL_COUNT_PROPOSAL"
        assert actual.counts == objective[3]
        assert actual.transitions == tuple(
            {"plain": p, "increases": i, "decreases": d} for p, i, d in transitions
        )
        assert actual.objective == {
            "maximum_residual_mm": f"{objective[0].numerator}/{objective[0].denominator}",
            "squared_residual_sum_mm2": f"{objective[1].numerator}/{objective[1].denominator}",
            "shaping_events": objective[2],
        }


def test_hand_case_retains_partial_second_pass_work_without_path():
    result = replay_count_search(
        (Fraction(2), Fraction(3)),
        Fraction(1),
        ((2, 3), (2, 3)),
        1,
        1,
        _budget(edges=4),
        work=TraceReplayWork(),
    )
    assert result.count_status == "SEARCH_BUDGET_EXHAUSTED"
    assert result.count_reason == "budget.transitions"
    assert result.count_completed_passes == 1
    assert [
        (x["pass"], x["retained_states"], x["transition_evaluations"], x["completed"])
        for x in result.count_layers
    ] == [(1, 2, 0, True), (1, 2, 4, True), (2, 1, 0, True), (2, 0, 0, False)]
    assert result.counts == result.transitions == () and result.objective is None
    assert result.used_transition_evaluations == 4


def test_first_pass_interruption_and_aggregate_work_exhaustion():
    limited = replay_count_search(
        (Fraction(2), Fraction(3)),
        Fraction(1),
        ((2, 3), (2, 3)),
        1,
        1,
        _budget(edges=1),
        work=TraceReplayWork(),
    )
    assert limited.count_completed_passes == 0
    assert limited.count_layers[-1]["completed"] is False
    with pytest.raises(TraceReplayBudgetExceeded):
        replay_count_search(
            (Fraction(2), Fraction(3)),
            Fraction(1),
            ((2, 3), (2, 3)),
            1,
            1,
            _budget(),
            work=TraceReplayWork(limit=1),
        )


@pytest.mark.parametrize(
    "budget, reason",
    [
        (_budget(courses=1), "budget.courses"),
        (_budget(values=1), "budget.count_values"),
        (_budget(states=1), "budget.dp_states"),
    ],
)
def test_resource_exhaustion_reasons(budget, reason):
    result = replay_count_search(
        (Fraction(2), Fraction(3)),
        Fraction(1),
        ((2, 3), (2, 3)),
        1,
        1,
        budget,
        work=TraceReplayWork(),
    )
    assert result.count_status == "SEARCH_BUDGET_EXHAUSTED"
    assert result.count_reason == reason
    assert not result.counts and result.objective is None


def test_impossible_domain_and_lexicographic_tie():
    impossible = replay_count_search(
        (Fraction(2), Fraction(9)),
        Fraction(1),
        ((2, 2), (9, 9)),
        0,
        0,
        _budget(),
        work=TraceReplayWork(),
    )
    assert impossible.count_status == "NO_FEASIBLE_CONSTRUCTION"
    tied = replay_count_search(
        (Fraction(5, 2), Fraction(5, 2)),
        Fraction(1),
        ((2, 3), (2, 3)),
        1,
        1,
        _budget(),
        work=TraceReplayWork(),
    )
    assert tied.counts == (2, 2)
