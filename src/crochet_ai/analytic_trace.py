"""Immutable canonical envelope for deterministic analytic producer evidence."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, cast

import rfc8785

from .json_types import JSONValue

TRACE_VERSION = "ANALYTIC_SEARCH_TRACE_V1"
TRACE_DOMAIN = b"Crochet.AI\x00ANALYTIC_SEARCH_TRACE_V1\x00"


@dataclass(frozen=True, slots=True, init=False)
class AnalyticSearchTrace:
    """JCS bytes are the immutable source of both payload and digest."""

    _payload_bytes: bytes
    sha256: str

    def __init__(self, payload: dict[str, Any]) -> None:
        encoded = rfc8785.dumps(cast(JSONValue, payload))
        object.__setattr__(self, "_payload_bytes", encoded)
        object.__setattr__(self, "sha256", sha256(TRACE_DOMAIN + encoded).hexdigest())

    def to_dict(self) -> dict[str, Any]:
        """Return a fresh JSON-compatible payload."""
        import json

        return cast(dict[str, Any], json.loads(self._payload_bytes))

    @property
    def payload_bytes(self) -> bytes:
        return self._payload_bytes
