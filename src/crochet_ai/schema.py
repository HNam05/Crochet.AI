"""Authoritative Draft 2020-12 schema loading and validation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from .canonical import CanonicalizationError, validate_ijson
from .diagnostics import Diagnostic, FailureCode, ValidationReport
from .json_types import JSONValue

SCHEMA_FILENAMES = {
    "design_spec": "design-spec.schema.json",
    "material_profile": "material-profile.schema.json",
    "crochet_ir": "crochet-ir.schema.json",
}


def _schema_directory() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "schemas"
        if all((candidate / name).is_file() for name in SCHEMA_FILENAMES.values()):
            return candidate
    candidate = Path.cwd() / "schemas"
    if all((candidate / name).is_file() for name in SCHEMA_FILENAMES.values()):
        return candidate
    raise RuntimeError("authoritative schemas directory not found")


@lru_cache(maxsize=1)
def _schemas() -> dict[str, dict[str, Any]]:
    directory = _schema_directory()
    loaded: dict[str, dict[str, Any]] = {}
    for kind, filename in SCHEMA_FILENAMES.items():
        schema = json.loads((directory / filename).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        loaded[kind] = schema
    return loaded


@lru_cache(maxsize=1)
def _registry() -> Registry[Any]:
    resources = []
    for schema in _schemas().values():
        resources.append((schema["$id"], Resource.from_contents(schema)))
    return Registry().with_resources(resources)


def artifact_fingerprint(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        encoded = f"{type(value).__qualname__}:{value!r}".encode("utf-8", "backslashreplace")
    return sha256(encoded).hexdigest()


def _json_pointer(parts: list[object]) -> str:
    if not parts:
        return ""
    escaped = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "/" + "/".join(escaped)


def validate_schema(kind: str, value: JSONValue) -> ValidationReport:
    fingerprint = artifact_fingerprint(value)
    try:
        validate_ijson(value)
    except CanonicalizationError as canonical_error:
        return ValidationReport.from_iterable(
            [
                Diagnostic(
                    code=FailureCode.INPUT,
                    gate="V1" if kind in {"design_spec", "material_profile"} else "V2",
                    message_key="input.not_ijson",
                    summary=str(canonical_error),
                    artifact_hash=fingerprint,
                )
            ]
        )
    schema = _schemas()[kind]
    validator = Draft202012Validator(
        schema,
        registry=_registry(),
        format_checker=FormatChecker(),
    )
    diagnostics = []
    errors = sorted(
        validator.iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.validator or "", error.message),
    )
    gate = "V1" if kind in {"design_spec", "material_profile"} else "V2"
    for error in errors:
        pointer = _json_pointer(list(error.absolute_path))
        diagnostics.append(
            Diagnostic(
                code=FailureCode.SCHEMA,
                gate=gate,
                message_key=f"schema.{error.validator or 'invalid'}",
                summary=error.message,
                artifact_hash=fingerprint,
                json_pointers=(pointer,),
                expected=error.validator_value,
                observed=error.instance,
            )
        )
    return ValidationReport.from_iterable(diagnostics)


def schema_documents() -> Mapping[str, Mapping[str, Any]]:
    """Return schema documents for read-only tooling and explicit schema checks."""
    return _schemas()
