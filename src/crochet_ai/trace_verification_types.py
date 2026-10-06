"""Proof-work budget shared only by independent analytic trace auditors."""

from dataclasses import dataclass


class TraceAuditInputError(ValueError):
    """Malformed untrusted audit input."""


class TraceReplayBudgetExceeded(ValueError):
    """Independent proof could not finish within its deterministic work budget."""


@dataclass(slots=True)
class TraceReplayWork:
    limit: int = 6_000_000
    consumed: int = 0

    def __post_init__(self) -> None:
        if type(self.limit) is not int or not 1 <= self.limit <= 6_000_000:
            raise TraceAuditInputError("trace_audit.replay_budget")
        if type(self.consumed) is not int or self.consumed != 0:
            raise TraceAuditInputError("trace_audit.initial_work")

    def spend(self) -> None:
        if self.consumed == self.limit:
            raise TraceReplayBudgetExceeded("trace_audit.replay_budget_exhausted")
        self.consumed += 1
