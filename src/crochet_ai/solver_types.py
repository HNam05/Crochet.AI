"""Explicit failures shared by deterministic generation stages."""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType


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
    ) -> None:
        self.status = status
        self.reason = reason
        self.consumed = consumed
        self.work = MappingProxyType(dict(work or {}))
        super().__init__(f"{status}:{reason}")
