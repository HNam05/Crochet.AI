"""Detached V1 export evidence; never an input to parsing or binding."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CertificationManifest:
    pattern_format_version: int
    source_ir_hash: str
    semantic_projection_hash: str
    pattern_document_hash: str
    terminology_profile: str
    exporter_version: str
    validator_version: str
