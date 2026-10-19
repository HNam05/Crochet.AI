"""Bounded positive schema reuse owned by one verification invocation."""

from __future__ import annotations

import json
from collections import OrderedDict
from collections.abc import Hashable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, field

from .json_types import JSONValue

_MAX_ENTRIES = 32
_MAX_PAYLOAD_BYTES = 8 * 1024 * 1024
SchemaKey = tuple[str, bytes, bytes, Hashable]


def _plain_json(value: object) -> bool:
    if type(value) in {type(None), bool, int, float, str}:
        return True
    if type(value) is list:
        return all(_plain_json(item) for item in value)
    if type(value) is dict:
        return all(type(key) is str and _plain_json(item) for key, item in value.items())
    return False


@dataclass(slots=True)
class SchemaValidationSession:
    """No diagnostics or caller-owned containers are retained."""

    hits: int = 0
    evaluations: int = 0
    _keys: OrderedDict[SchemaKey, int] = field(default_factory=OrderedDict)
    _payload_bytes: int = 0

    @property
    def entries(self) -> int:
        return len(self._keys)

    @property
    def payload_bytes(self) -> int:
        return self._payload_bytes

    def snapshot(self, value: JSONValue) -> tuple[JSONValue, bytes | None]:
        if not _plain_json(value):
            return value, None
        owned = deepcopy(value)
        try:
            # Preserve insertion order and numeric types, including 1 vs 1.0.
            encoded = json.dumps(
                owned, ensure_ascii=True, allow_nan=False, separators=(",", ":")
            ).encode("utf-8")
        except (TypeError, ValueError):
            return value, None
        if len(encoded) > _MAX_PAYLOAD_BYTES:
            return value, None
        # A cold validation and its key read the same owned snapshot.
        return owned, encoded

    def contains(self, key: SchemaKey) -> bool:
        if key not in self._keys:
            return False
        self._keys.move_to_end(key)
        self.hits += 1
        return True

    def remember(self, key: SchemaKey) -> None:
        size = len(key[0].encode("utf-8")) + len(key[1]) + len(key[2])
        if size > _MAX_PAYLOAD_BYTES or key in self._keys:
            return
        while self._keys and (
            len(self._keys) >= _MAX_ENTRIES or self._payload_bytes + size > _MAX_PAYLOAD_BYTES
        ):
            _, removed_size = self._keys.popitem(last=False)
            self._payload_bytes -= removed_size
        self._keys[key] = size
        self._payload_bytes += size

    def clear(self) -> None:
        self._keys.clear()
        self._payload_bytes = 0


_ACTIVE: ContextVar[SchemaValidationSession | None] = ContextVar(
    "schema_validation_session", default=None
)


def active_schema_session() -> SchemaValidationSession | None:
    return _ACTIVE.get()


@contextmanager
def schema_validation_session() -> Iterator[SchemaValidationSession]:
    """Always create a fresh scope, including nested verification calls."""
    session = SchemaValidationSession()
    token = _ACTIVE.set(session)
    try:
        yield session
    finally:
        session.clear()
        _ACTIVE.reset(token)
