from fractions import Fraction
from itertools import product

import pytest

from crochet_ai.analytic_placement import PlacementBudget, choose_phases
from crochet_ai.solver_types import GenerationError, GenerationStatus


def test_phase_dp_matches_hand_derived_full_enumeration() -> None:
    # 4->6 increases at bases 1,3. 6->4 decreases at pairs (1,2),(4,5).
    # These angles are derived without the production placement/arity helpers.
    labels = []
    separation = Fraction(1, 5)
    for first, second, third in product(range(4), range(6), range(4)):
        angles = [
            tuple((x + Fraction(phase, n)) % 1 for x in base)
            for base, phase, n in (
                ((Fraction(3, 8), Fraction(7, 8)), first, 4),
                ((Fraction(1, 3), Fraction(5, 6)), second, 6),
                ((Fraction(3, 8), Fraction(7, 8)), third, 4),
            )
        ]
        distances = [
            min(abs(a - b), 1 - abs(a - b))
            for i in (0, 1)
            for a in angles[i]
            for b in angles[i + 1]
        ]
        labels.append(
            (
                sum(d == 0 for d in distances),
                sum((max(Fraction(0), separation - d) for d in distances), Fraction(0)),
                (first, second, third),
            )
        )
    result = choose_phases((4, 6, 4, 6), separation, PlacementBudget(64, 10000, 100000))
    assert (result.stacking_pairs, result.proximity_penalty_turns, result.phases) == min(labels)


@pytest.mark.parametrize(
    "budget,reason",
    [
        (PlacementBudget(1, 100, 100), "placement.variants"),
        (PlacementBudget(64, 1, 100), "placement.transitions"),
        (PlacementBudget(64, 100, 1), "placement.pairs"),
    ],
)
def test_phase_budget_reports_consumed_work(budget: PlacementBudget, reason: str) -> None:
    with pytest.raises(GenerationError) as error:
        choose_phases((4, 6, 4), Fraction(1, 5), budget)
    assert error.value.status == GenerationStatus.SEARCH_BUDGET_EXHAUSTED
    assert error.value.reason == reason
    assert error.value.work["placement_transitions"] <= budget.max_transition_evaluations
    assert error.value.work["placement_pairs"] <= budget.max_pair_evaluations
