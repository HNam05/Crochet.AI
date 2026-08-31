"""Deterministic structured diagnostics shared by Milestone 0 gates."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from types import MappingProxyType
from typing import Any


class FailureCode(StrEnum):
    INPUT = "E_INPUT"
    SCHEMA = "E_SCHEMA"
    REFERENCE = "E_REFERENCE"
    COUNT = "E_COUNT"
    FRONTIER = "E_FRONTIER"
    TOPOLOGY = "E_TOPOLOGY"
    UNSUPPORTED_FEATURE = "E_UNSUPPORTED_FEATURE"
    EXPORT_ROUNDTRIP = "E_EXPORT_ROUNDTRIP"
    DETERMINISM = "E_DETERMINISM"
    PROVENANCE = "E_PROVENANCE"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: FailureCode
    gate: str
    message_key: str
    summary: str
    artifact_hash: str
    entity_refs: tuple[str, ...] = ()
    json_pointers: tuple[str, ...] = ()
    expected: Any = None
    observed: Any = None
    units: str | None = None
    tolerance_profile_id: str | None = None
    implementation_version: str = "milestone0.1"
    cause_ids: tuple[str, ...] = ()
    reproducibility: Mapping[str, Any] = field(default_factory=dict)
    severity: str = "ERROR"
    diagnostic_id: str = field(init=False)

    def __post_init__(self) -> None:
        reproducibility = dict(self.reproducibility)
        if not reproducibility:
            reproducibility = {
                "software_commit": "UNAVAILABLE_UNCOMMITTED_WORKTREE",
                "parameters_hash": f"sha256:{self.artifact_hash}",
                "random_seed": None,
            }
        object.__setattr__(self, "reproducibility", MappingProxyType(reproducibility))
        payload = "\x1f".join(
            (
                self.code,
                self.gate,
                self.message_key,
                self.artifact_hash,
                "\x1e".join(self.entity_refs),
                "\x1e".join(self.json_pointers),
            )
        ).encode("utf-8")
        object.__setattr__(self, "diagnostic_id", f"diag_{sha256(payload).hexdigest()[:24]}")

    def sort_key(self) -> tuple[Any, ...]:
        return (
            self.gate,
            self.code,
            self.message_key,
            self.json_pointers,
            self.entity_refs,
            self.diagnostic_id,
        )


@dataclass(frozen=True, slots=True)
class ValidationReport:
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.diagnostics

    @classmethod
    def from_iterable(cls, diagnostics: Iterable[Diagnostic]) -> ValidationReport:
        unique = {diagnostic.diagnostic_id: diagnostic for diagnostic in diagnostics}
        return cls(tuple(sorted(unique.values(), key=Diagnostic.sort_key)))


class ArtifactValidationError(ValueError):
    """Raised when a strict runtime artifact cannot be constructed or hashed."""

    def __init__(self, report: ValidationReport) -> None:
        self.report = report
        message = "; ".join(f"{item.code}:{item.message_key}" for item in report.diagnostics[:5])
        super().__init__(message or "artifact validation failed")
