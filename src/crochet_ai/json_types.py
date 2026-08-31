"""Immutable JSON value helpers."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import TypeAlias

JSONScalar: TypeAlias = bool | int | float | str | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
FrozenJSON: TypeAlias = JSONScalar | tuple["FrozenJSON", ...] | Mapping[str, "FrozenJSON"]


def freeze_json(value: JSONValue) -> FrozenJSON:
    if isinstance(value, dict):
        return MappingProxyType({key: freeze_json(child) for key, child in value.items()})
    if isinstance(value, list):
        return tuple(freeze_json(child) for child in value)
    return value


def thaw_json(value: FrozenJSON) -> JSONValue:
    if isinstance(value, Mapping):
        return {key: thaw_json(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(child) for child in value]
    return value
