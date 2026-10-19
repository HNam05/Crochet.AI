from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from copy import deepcopy

import pytest
from conftest import load_fixture, make_closed_ir, resolved_artifacts
from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import FormatChecker

import crochet_ai.schema as schemas
import crochet_ai.schema_session as sessions
import crochet_ai.verification_pipeline as pipeline


def material():
    return load_fixture("material-profile.minimal.valid.json")


def test_only_success_is_reused_and_every_lookup_still_admits_ijson(monkeypatch):
    value = material()
    calls = []
    original = schemas.validate_ijson

    def admit(candidate):
        calls.append(candidate)
        return original(candidate)

    monkeypatch.setattr(schemas, "validate_ijson", admit)
    with sessions.schema_validation_session() as session:
        assert schemas.validate_schema("material_profile", value).ok
        assert schemas.validate_schema("material_profile", deepcopy(value)).ok
        assert session.hits == 1 and session.evaluations == 1
        value["hook_diameter_mm"] = "invalid"
        expected = schemas.validate_schema("material_profile", value)
        repeated = schemas.validate_schema("material_profile", value)
        assert expected == repeated and not expected.ok
        assert expected.diagnostics[0].code == "E_SCHEMA"
        assert session.evaluations == 3 and session.hits == 1
        assert len(calls) == 4
    assert sessions.active_schema_session() is None
    assert session.entries == 0 and session.payload_bytes == 0


@given(st.one_of(st.booleans(), st.integers(max_value=0), st.text(max_size=15)))
@settings(max_examples=30)
def test_mutated_nested_input_keeps_uncached_diagnostics(invalid_pitch):
    """Independent oracle is the unchanged cold validator; generated defects keep their type."""
    value = material()
    invalid = deepcopy(value)
    invalid["calibration_responses"][0]["effective_gauge"]["effective_stitch_pitch_mm"] = (
        invalid_pitch
    )
    baseline = schemas.validate_schema("material_profile", invalid)
    assert not baseline.ok
    with sessions.schema_validation_session() as session:
        assert schemas.validate_schema("material_profile", value).ok
        value["calibration_responses"][0]["effective_gauge"]["effective_stitch_pitch_mm"] = (
            invalid_pitch
        )
        report = schemas.validate_schema("material_profile", value)
        assert report == baseline
        assert all(d.gate == "V1" for d in report.diagnostics)
        assert any(
            "effective_stitch_pitch_mm" in p for d in report.diagnostics for p in d.json_pointers
        ) or any(
            d.code == "E_INPUT"
            and d.message_key == "input.not_ijson"
            and "effective_stitch_pitch_mm" in d.summary
            for d in report.diagnostics
        )
        assert session.hits == 0


def test_numeric_types_and_array_order_are_not_normalized_into_hits():
    value = material()
    with sessions.schema_validation_session() as session:
        assert schemas.validate_schema("material_profile", value).ok
        value["revision"] = 1.0
        assert schemas.validate_schema("material_profile", value).ok
        assert session.hits == 0 and session.evaluations == 2
        value["revision"] = True
        assert not schemas.validate_schema("material_profile", value).ok
        value["revision"] = 1
        value["provenance"]["source_record_ids"].append("record_second")
        assert schemas.validate_schema("material_profile", value).ok
        value["provenance"]["source_record_ids"].reverse()
        assert schemas.validate_schema("material_profile", value).ok
        assert session.hits == 0


@pytest.mark.parametrize("invalid_text", ["\ud800", "\udfff", "\ud83d\ude00"])
def test_snapshot_never_repairs_invalid_unicode_before_admission(invalid_text):
    value = material()
    value["yarn"]["description"] = "\U0001f600"
    invalid = deepcopy(value)
    invalid["yarn"]["description"] = invalid_text
    cold = schemas.validate_schema("material_profile", invalid)
    assert not cold.ok and cold.diagnostics[0].message_key == "input.not_ijson"
    with sessions.schema_validation_session() as session:
        assert schemas.validate_schema("material_profile", value).ok
        owned, _ = session.snapshot(invalid)
        assert owned["yarn"]["description"] == invalid_text
        assert schemas.validate_schema("material_profile", invalid) == cold
        assert session.hits == 0
        invalid[invalid_text] = "invalid key"
        keyed = schemas.validate_schema("material_profile", invalid)
        assert keyed.diagnostics[0].message_key == "input.not_ijson"


def test_changed_referenced_schema_and_checker_cannot_reuse_success(monkeypatch):
    design, _ = resolved_artifacts()
    with sessions.schema_validation_session() as session:
        assert schemas.validate_schema("design_spec", design).ok
        document = schemas.schema_documents()["material_profile"]
        monkeypatch.setitem(document, "required", [*document["required"], "missing_test_field"])
        report = schemas.validate_schema("design_spec", design)
        assert not report.ok and session.hits == 0
        assert any("/material_profile" in d.json_pointers for d in report.diagnostics)
    assert report == schemas.validate_schema("design_spec", design)
    monkeypatch.undo()
    value = material()
    with sessions.schema_validation_session() as session:
        assert schemas.validate_schema("material_profile", value).ok
        monkeypatch.setitem(FormatChecker.checkers, "date-time", (lambda _: False, ()))
        report = schemas.validate_schema("material_profile", value)
        assert not report.ok and session.hits == 0
        assert any(d.message_key == "schema.format" for d in report.diagnostics)


def test_native_subclasses_and_nonstring_keys_never_enter_success_memo():
    class CustomDict(dict):
        pass

    with sessions.schema_validation_session() as session:
        assert schemas.validate_schema("material_profile", CustomDict(material())).ok
        assert schemas.validate_schema("material_profile", CustomDict(material())).ok
        assert session.hits == 0 and session.entries == 0
        value = {1: "value"}
        assert session.snapshot(value)[1] is None


def test_snapshot_is_owned_and_byte_and_entry_limits_are_enforced(monkeypatch):
    value = material()
    session = sessions.SchemaValidationSession()
    copied, encoded = session.snapshot(value)
    value["calibration_responses"][0]["observations"][0]["stitch_span_count"] = 99
    assert copied != value and encoded is not None
    monkeypatch.setattr(sessions, "_MAX_ENTRIES", 2)
    monkeypatch.setattr(sessions, "_MAX_PAYLOAD_BYTES", 32)
    assert session.snapshot(material())[1] is None
    for index in range(4):
        session.remember(("kind", b"schema", str(index).encode(), ()))
    assert session.entries == 2 and session.payload_bytes <= 32
    assert not session.contains(("other", b"schema", b"3", ()))
    session.remember(("kind", b"x" * 33, b"v", ()))
    assert session.entries == 2 and session.payload_bytes <= 32


def test_nested_exception_and_thread_scopes_do_not_share_entries():
    def worker():
        assert sessions.active_schema_session() is None
        with sessions.schema_validation_session() as session:
            assert schemas.validate_schema("material_profile", material()).ok
            assert session.hits == 0
            assert schemas.validate_schema("material_profile", material()).ok
            assert session.hits == 1
        assert sessions.active_schema_session() is None
        return session.entries

    with sessions.schema_validation_session() as outer:
        assert schemas.validate_schema("material_profile", material()).ok
        with (
            pytest.raises(RuntimeError, match="test cleanup"),
            sessions.schema_validation_session() as inner,
        ):
            assert inner is not outer
            assert schemas.validate_schema("material_profile", material()).ok
            assert inner.hits == 0
            raise RuntimeError("test cleanup")
        assert sessions.active_schema_session() is outer and inner.entries == 0
        with ThreadPoolExecutor(max_workers=2) as executor:
            assert list(executor.map(lambda _: worker(), range(2))) == [0, 0]
        assert schemas.validate_schema("material_profile", material()).ok
        assert outer.hits == 1


def test_pipeline_evidence_matches_cold_validation(monkeypatch):
    design, profile = resolved_artifacts()
    ir = make_closed_ir()
    reused = pipeline.verify_artifacts(design, profile, ir, diagnostic_mode=True)
    monkeypatch.setattr(pipeline, "schema_validation_session", nullcontext)
    cold = pipeline.verify_artifacts(design, profile, ir, diagnostic_mode=True)
    assert reused.evidence_bundle_hash == cold.evidence_bundle_hash
    assert [g.canonical_payload() for g in reused.gates] == [
        g.canonical_payload() for g in cold.gates
    ]
