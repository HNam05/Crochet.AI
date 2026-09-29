"""Typed external linker inputs for payload-free Pattern V1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PatternYarnBinding:
    """The only Yarn A-style external identity a Pattern V1 binder may resolve."""

    symbol: str
    material_profile: dict[str, Any]
    color_label: str
    srgb_hex: str


@dataclass(frozen=True, slots=True)
class PatternParseContext:
    """A linker environment, deliberately incapable of carrying construction data."""

    design_spec: dict[str, Any]
    yarn_bindings: tuple[PatternYarnBinding, ...]

    def binding(self, symbol: str) -> PatternYarnBinding:
        matches = tuple(binding for binding in self.yarn_bindings if binding.symbol == symbol)
        if len(matches) != 1:
            raise ValueError(f"Pattern V1 requires exactly one binding for {symbol!r}")
        return matches[0]
