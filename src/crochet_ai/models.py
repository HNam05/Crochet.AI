"""Strict immutable runtime wrappers around the frozen JSON contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar, Self

from .canonical import parse_json
from .diagnostics import ArtifactValidationError
from .json_types import FrozenJSON, JSONValue, freeze_json, thaw_json
from .schema import validate_schema


@dataclass(frozen=True, slots=True)
class ArtifactModel:
    _data: FrozenJSON
    schema_kind: ClassVar[str]

    @classmethod
    def from_dict(cls, value: JSONValue) -> Self:
        report = validate_schema(cls.schema_kind, value)
        if not report.ok:
            raise ArtifactValidationError(report)
        return cls(freeze_json(value))

    @classmethod
    def from_json(cls, text: str | bytes) -> Self:
        value = parse_json(text)
        return cls.from_dict(value)

    def to_dict(self) -> dict[str, JSONValue]:
        value = thaw_json(self._data)
        if not isinstance(value, dict):
            raise TypeError("artifact root must be an object")
        return value

    def __getitem__(self, key: str) -> FrozenJSON:
        if not isinstance(self._data, Mapping):
            raise TypeError("artifact root must be an object")
        return self._data[key]


@dataclass(frozen=True, slots=True)
class DesignSpec(ArtifactModel):
    schema_kind: ClassVar[str] = "design_spec"


@dataclass(frozen=True, slots=True)
class MaterialProfile(ArtifactModel):
    schema_kind: ClassVar[str] = "material_profile"


@dataclass(frozen=True, slots=True)
class CrochetIR(ArtifactModel):
    schema_kind: ClassVar[str] = "crochet_ir"


@dataclass(frozen=True, slots=True)
class IndexedTriangleMesh(ArtifactModel):
    """Immutable runtime value for the canonical V0 triangle-surface schema."""

    schema_kind: ClassVar[str] = "indexed_triangle_mesh"
