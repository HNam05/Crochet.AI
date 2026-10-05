"""Shared runtime/source identity for local compilation and evidence reuse."""

from __future__ import annotations

import platform
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path

import rfc8785

from .analytic_compile import CompileProvenance
from .schema import schema_documents


def runtime_provenance(commit: str) -> CompileProvenance:
    source_hashes = {
        path.name: sha256(path.read_bytes()).hexdigest()
        for path in sorted(Path(__file__).parent.glob("*.py"))
    }
    schema_hashes = {
        name: sha256(rfc8785.dumps(document)).hexdigest()
        for name, document in schema_documents(include_additive_versions=True).items()
    }
    snapshot = sha256(
        b"Crochet.AI\0BACKEND_SOURCE_SNAPSHOT_V1\0"
        + rfc8785.dumps({"sources": source_hashes, "schemas": schema_hashes})
    ).hexdigest()
    return CompileProvenance(
        commit,
        snapshot,
        (
            ("runtime.python", platform.python_version()),
            ("runtime.platform", platform.system()),
            ("runtime.jsonschema", version("jsonschema")),
            ("runtime.rfc8785", version("rfc8785")),
            ("source.checkout_status", "UNCONFIRMED"),
        ),
    )


def implementation_identity_hash() -> str:
    provenance = runtime_provenance("")
    return sha256(
        b"Crochet.AI\0BACKEND_IMPLEMENTATION_IDENTITY_V1\0"
        + rfc8785.dumps(
            {
                "source_snapshot_sha256": provenance.source_snapshot_sha256,
                "runtime_bindings": dict(provenance.parameters),
            }
        )
    ).hexdigest()
