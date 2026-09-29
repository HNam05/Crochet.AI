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
from .pattern import (
    PatternDocument,
    PatternFormatError,
    TerminologyProfile,
    UnresolvedPatternSemantics,
    bind_pattern_semantics,
    build_certification_manifest,
    export_pattern,
    parse_pattern,
    parse_pattern_text,
    verify_semantic_round_trip,
)
from .pattern_context import PatternParseContext, PatternYarnBinding
from .validation import SemanticValidator

__all__ = [
    "CanonicalProfile",
    "CrochetIR",
    "DesignSpec",
    "Diagnostic",
    "FailureCode",
    "MaterialProfile",
    "PatternDocument",
    "PatternFormatError",
    "PatternParseContext",
    "PatternYarnBinding",
    "SemanticValidator",
    "TerminologyProfile",
    "UnresolvedPatternSemantics",
    "ValidationReport",
    "are_semantically_equivalent",
    "bind_pattern_semantics",
    "build_certification_manifest",
    "canonical_bytes",
    "canonical_hash",
    "canonical_projection",
    "export_pattern",
    "parse_json",
    "parse_pattern",
    "parse_pattern_text",
    "semantic_projection",
    "verify_semantic_round_trip",
]
