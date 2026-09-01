from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from conftest import load_fixture, resolved_validator

from crochet_ai.canonical import (
    CanonicalProfile,
    canonical_bytes,
    canonical_hash,
    canonical_projection,
)
from crochet_ai.diagnostics import ArtifactValidationError
from crochet_ai.schema import validate_schema

VECTORS_PATH = Path(__file__).parent / "conformance" / "canonical-vectors.json"
NEGATIVE_IR_FIXTURE = "tests/fixtures/schema-valid/crochet-ir.magic-ring-single-course.valid.json"


def _vectors() -> list[dict[str, Any]]:
    return json.loads(VECTORS_PATH.read_text(encoding="utf-8"))


def _vector(identifier: str) -> dict[str, Any]:
    return next(vector for vector in _vectors() if vector["id"] == identifier)


def _load_vector_value(vector: dict[str, Any]) -> dict[str, Any]:
    if "input_file" in vector:
        value = json.loads(Path(vector["input_file"]).read_text(encoding="utf-8"))
    else:
        value = vector["input"]
    if "inline_material_file" in vector:
        value["material_profile"] = {
            "binding_type": "INLINE",
            "profile": json.loads(Path(vector["inline_material_file"]).read_text(encoding="utf-8")),
        }
    return value


def test_all_python_conformance_vectors_match_static_values() -> None:
    for vector in _vectors():
        profile = CanonicalProfile(vector["profile"])
        value = _load_vector_value(vector)
        validator = resolved_validator() if profile == CanonicalProfile.CROCHET_IR else None
        encoded = canonical_bytes(value, profile, validator=validator)
        digest = canonical_hash(value, profile, validator=validator)

        if "expected_canonical_json" in vector:
            assert encoded == vector["expected_canonical_json"].encode("utf-8"), vector["id"]
        if "expected_canonical_file" in vector:
            expected = Path(vector["expected_canonical_file"]).read_bytes().rstrip(b"\r\n")
            assert encoded == expected, vector["id"]
        assert digest == vector["expected_sha256"], vector["id"]


def test_valid_crochet_ir_vector_is_semantic_before_canonicalization() -> None:
    vector = _vector("crochet-ir-closed-semantic-valid")
    value = _load_vector_value(vector)
    validator = resolved_validator()

    assert validate_schema("crochet_ir", value).ok
    assert validator.validate_crochet_ir(value).ok

    profile = CanonicalProfile(vector["profile"])
    projection = canonical_projection(value, profile, validator=validator)
    encoded = canonical_bytes(value, profile, validator=validator)
    expected = Path(vector["expected_canonical_file"]).read_bytes().rstrip(b"\r\n")
    assert encoded == expected
    assert json.loads(encoded) == projection

    prefix = vector["expected_preimage_prefix_ascii"].encode("ascii")
    assert prefix == b"Crochet.AI\x00CROCHET_IR_CANONICAL_JSON_V1\x00"
    preimage = prefix + encoded
    assert sha256(preimage).hexdigest() == vector["expected_sha256"]
    assert canonical_hash(value, profile, validator=validator) == vector["expected_sha256"]


def test_schema_valid_but_semantically_invalid_ir_cannot_be_hashed() -> None:
    value = load_fixture("crochet-ir.magic-ring-single-course.valid.json")
    assert validate_schema("crochet_ir", value).ok

    validator = resolved_validator()
    report = validator.validate_crochet_ir(value)
    keys = {diagnostic.message_key for diagnostic in report.diagnostics}
    codes = {diagnostic.code for diagnostic in report.diagnostics}
    assert not report.ok
    assert {
        "design_spec_ref.content_mismatch",
        "material_profile_ref.content_mismatch",
        "yarn_path.work_membership",
        "yarn_segment.event_order",
        "frontier.unintended_terminal_boundary",
    } <= keys
    assert {"E_REFERENCE", "E_COUNT", "E_FRONTIER"} <= codes

    with pytest.raises(ArtifactValidationError) as error:
        canonical_hash(value, CanonicalProfile.CROCHET_IR, validator=validator)
    assert {diagnostic.code for diagnostic in error.value.report.diagnostics} >= codes


def test_positive_crochet_ir_vector_never_reuses_the_negative_fixture() -> None:
    assert all(
        vector.get("input_file") != NEGATIVE_IR_FIXTURE
        for vector in _vectors()
    )
