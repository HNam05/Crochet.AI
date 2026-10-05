"""Explicit failures shared by deterministic generation stages."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .analytic_placement import PlacementLayerTrace


class GenerationStatus(StrEnum):
    CANDIDATES_EMITTED = "CANDIDATES_EMITTED"
    INVALID_SOLVER_INPUT = "INVALID_SOLVER_INPUT"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NO_FEASIBLE_CONSTRUCTION = "NO_FEASIBLE_CONSTRUCTION"
    SEARCH_BUDGET_EXHAUSTED = "SEARCH_BUDGET_EXHAUSTED"
    NUMERICAL_FAILURE = "NUMERICAL_FAILURE"


class GenerationError(ValueError):
    def __init__(
        self,
        status: GenerationStatus,
        reason: str,
        consumed: int = 0,
        *,
        work: Mapping[str, int] | None = None,
        trace: tuple[PlacementLayerTrace, ...] = (),
    ) -> None:
        self.status = status
        self.reason = reason
        self.consumed = consumed
        self.work = MappingProxyType(dict(work or {}))
        self.trace = trace
        super().__init__(f"{status}:{reason}")
