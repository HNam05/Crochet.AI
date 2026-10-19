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
from .schema_session import SchemaKey, active_schema_session

SCHEMA_FILENAMES = {
    "design_spec": "design-spec.schema.json",
    "design_spec_1_1": "design-spec-1.1.schema.json",
    "design_spec_1_2": "design-spec-1.2.schema.json",
    "material_profile": "material-profile.schema.json",
    "crochet_ir": "crochet-ir.schema.json",
    "crochet_ir_1_1": "crochet-ir-1.1.schema.json",
    "indexed_triangle_mesh": "indexed-triangle-mesh.schema.json",
    "numerical_geometry_profile": "numerical-geometry-profile.schema.json",
    "numerical_geometry_profile_1_1": "numerical-geometry-profile-1.1.schema.json",
}


def _schema_directory() -> Path:
    bundled = Path(__file__).resolve().parent / "schemas"
    if all((bundled / name).is_file() for name in SCHEMA_FILENAMES.values()):
        return bundled
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
    session = active_schema_session()
    encoded = None
    if session is not None:
        value, encoded = session.snapshot(value)
    if kind == "design_spec" and isinstance(value, dict):
        if value.get("schema_version") == "1.1.0":
            kind = "design_spec_1_1"
        elif value.get("schema_version") == "1.2.0":
            kind = "design_spec_1_2"
    if (
        kind == "numerical_geometry_profile"
        and isinstance(value, dict)
        and value.get("schema_version") == "1.1.0"
    ):
        kind = "numerical_geometry_profile_1_1"
    if kind == "crochet_ir" and isinstance(value, dict) and value.get("schema_version") == "1.1.0":
        kind = "crochet_ir_1_1"
    fingerprint = artifact_fingerprint(value)
    try:
        validate_ijson(value)
    except CanonicalizationError as canonical_error:
        return ValidationReport.from_iterable(
            [
                Diagnostic(
                    code=FailureCode.INPUT,
                    gate=(
                        "V0"
                        if kind
                        in {
                            "indexed_triangle_mesh",
                            "numerical_geometry_profile",
                            "numerical_geometry_profile_1_1",
                        }
                        else "V1"
                        if kind
                        in {"design_spec", "design_spec_1_1", "design_spec_1_2", "material_profile"}
                        else "V2"
                    ),
                    message_key="input.not_ijson",
                    summary=str(canonical_error),
                    artifact_hash=fingerprint,
                )
            ]
        )
    schema = _schemas()[kind]
    registry = _registry()
    format_checker = FormatChecker()
    validator = Draft202012Validator(
        schema,
        registry=registry,
        format_checker=format_checker,
    )
    key: SchemaKey | None = None
    if session is not None and encoded is not None:
        # Bind the root and the actual resolved resources, not just their URIs.
        resources = {uri: registry.contents(uri) for uri in registry}
        schemas = json.dumps(
            {"root": schema, "resources": resources},
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        implementation = (
            type(validator),
            type(validator).iter_errors,
            type(validator).descend,
            type(validator).evolve,
            type(validator).TYPE_CHECKER,
            tuple(sorted(type(validator).VALIDATORS.items())),
            type(format_checker),
            type(format_checker).check,
            type(format_checker).conforms,
            tuple(sorted(format_checker.checkers.items())),
        )
        try:
            hash(implementation)
        except TypeError:
            pass  # Unusual native custom checkers use the unchanged cold path.
        else:
            key = (kind, schemas, encoded, implementation)
            if session.contains(key):
                return ValidationReport()
    if session is not None:
        session.evaluations += 1
    diagnostics = []
    errors = sorted(
        validator.iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.validator or "", error.message),
    )
    gate = (
        "V0"
        if kind
        in {
            "indexed_triangle_mesh",
            "numerical_geometry_profile",
            "numerical_geometry_profile_1_1",
        }
        else "V1"
        if kind in {"design_spec", "design_spec_1_1", "design_spec_1_2", "material_profile"}
        else "V2"
    )
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
    report = ValidationReport.from_iterable(diagnostics)
    if report.ok and session is not None and key is not None:
        session.remember(key)
    return report


def schema_documents(
    *,
    include_additive_versions: bool = False,
) -> Mapping[str, Mapping[str, Any]]:
    """Return schema documents; additive versions are opt-in for tooling compatibility."""
    if include_additive_versions:
        return _schemas()
    legacy_kinds = {
        "design_spec",
        "material_profile",
        "crochet_ir",
        "crochet_ir_1_1",
        "indexed_triangle_mesh",
        "numerical_geometry_profile",
    }
    return {kind: schema for kind, schema in _schemas().items() if kind in legacy_kinds}
