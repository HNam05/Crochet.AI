"""Milestone 0 runtime for deterministic crochet artifacts."""

from .canonical import (
    CanonicalProfile,
    canonical_bytes,
    canonical_hash,
    canonical_projection,
    parse_json,
)
from .diagnostics import Diagnostic, FailureCode, ValidationReport
from .equivalence import are_semantically_equivalent, semantic_projection
from .models import CrochetIR, DesignSpec, MaterialProfile
from .validation import SemanticValidator

__all__ = [
    "CanonicalProfile",
    "CrochetIR",
    "DesignSpec",
    "Diagnostic",
    "FailureCode",
    "MaterialProfile",
    "SemanticValidator",
    "ValidationReport",
    "are_semantically_equivalent",
    "canonical_bytes",
    "canonical_hash",
    "canonical_projection",
    "parse_json",
    "semantic_projection",
]
