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
from .mesh_preflight import (
    MeshPreflightResult,
    MeshPreflightValidator,
    PreflightOutcome,
    preflight_mesh,
)
from .models import CrochetIR, DesignSpec, IndexedTriangleMesh, MaterialProfile
from .validation import SemanticValidator

__all__ = [
    "CanonicalProfile",
    "CrochetIR",
    "DesignSpec",
    "Diagnostic",
    "FailureCode",
    "IndexedTriangleMesh",
    "MaterialProfile",
    "MeshPreflightResult",
    "MeshPreflightValidator",
    "PreflightOutcome",
    "SemanticValidator",
    "ValidationReport",
    "are_semantically_equivalent",
    "canonical_bytes",
    "canonical_hash",
    "canonical_projection",
    "parse_json",
    "preflight_mesh",
    "semantic_projection",
]
