from __future__ import annotations

from copy import deepcopy

import pytest
from conftest import make_closed_ir, resolved_artifacts
from test_pattern_adversarial import TEXT
from test_reserve_compile import inputs

from crochet_ai.canonical import CanonicalProfile, canonical_hash
from crochet_ai.equivalence import semantic_bytes
from crochet_ai.pattern import PatternFormatError, TerminologyProfile, parse_pattern
from crochet_ai.pattern_context import PatternParseContext, PatternYarnBinding
from crochet_ai.pattern_m1b import export_pattern_m1b, parse_pattern_m1b
from crochet_ai.reserve_compile import compile_reserve_schedule
from crochet_ai.validation import SemanticValidator


def opening_fixture():
    design, material = resolved_artifacts()
    design["domain_constraints"]["surface_mode"] = "DECLARED_OPENINGS"
    design["construction_constraints"]["intentional_openings"] = [
        {
            "opening_requirement_id": "opening_req_test",
            "purpose": "OTHER",
            "boundary_landmark_ids": [],
            "closure_expectation": "REMAIN_OPEN",
        }
    ]
    value = make_closed_ir()
    value["design_spec_ref"]["sha256"] = canonical_hash(design, CanonicalProfile.DESIGN_SPEC)
    op = value["construction_operations"][-1]
    op.update(
        operation_type="DECLARE_OPENING",
        opening_id="opening_test",
        design_requirement_id="opening_req_test",
    )
    before = value["frontiers"][-2]["attachment_location_ids"]
    value["frontiers"][-1].update(
        lifecycle_state="DECLARED_OPEN",
        attachment_location_ids=list(before),
        anchor_attachment_location_id=before[0],
    )
    value["frontier_transitions"][-1].update(
        transition_type="DECLARE_OPENING",
        retired_attachment_location_ids=[],
        opening_id="opening_test",
    )
    value["openings"] = [
        {
            "opening_id": "opening_test",
            "component_id": "component_fixture_main",
            "design_requirement_id": "opening_req_test",
            "declared_by_operation_id": op["operation_id"],
            "boundary_attachment_location_ids": list(before),
            "purpose": "OTHER",
            "closure_expectation": "REMAIN_OPEN",
            "derivation_id": "deriv_opening_test",
        }
    ]
    value["derivations"].append(
        {
            "derivation_id": "deriv_opening_test",
            "method": "MANUAL_BOOTSTRAP",
            "rule_id": "test.opening",
            "rule_version": "1",
            "parameter_sha256": "0" * 64,
            "subject_refs": [{"entity_type": "OPENING", "opening_id": "opening_test"}],
        }
    )
    return value, design, material


@pytest.mark.parametrize("profile", list(TerminologyProfile))
def test_declared_opening_is_visible_and_round_trips_against_real_design_requirement(profile):
    value, design, material = opening_fixture()
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={material["profile_id"]: material},
    )
    assert validator.validate_crochet_ir(value).ok
    context = PatternParseContext(
        design, (PatternYarnBinding("Yarn A", material, "Natural", "#C8B08A"),)
    )
    text = export_pattern_m1b(value, profile, validator=validator)
    assert "Leave open" in text and "opening_req_test" in text
    parsed = parse_pattern_m1b(text, context=context)
    assert semantic_bytes(parsed, validator=validator) == semantic_bytes(value, validator=validator)
    with pytest.raises(PatternFormatError):
        parse_pattern_m1b(text.replace("opening_req_test", "opening_req_invented"), context=context)


def test_actual_multisite_reserve_compiler_and_later_decrease_round_trip():
    design, material, provenance = inputs()
    design["material_profile"] = {
        "binding_type": "REFERENCE",
        "profile_id": material["profile_id"],
        "revision": material["revision"],
        "sha256": canonical_hash(material, CanonicalProfile.MATERIAL_PROFILE),
    }
    design["difficulty_constraints"]["allowed_shaping"].append("DECREASE")
    value = compile_reserve_schedule(design, material, 6, 2, (4, 3), (1, 2), provenance)
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={material["profile_id"]: material},
    )
    context = PatternParseContext(
        design, (PatternYarnBinding("Yarn A", material, "Natural", "#C8B08A"),)
    )
    text = export_pattern_m1b(value, TerminologyProfile.US_EN, validator=validator)
    assert "Core: 1.1.0" in text and "Work 1 sc decrease" in text
    assert semantic_bytes(
        parse_pattern_m1b(text, context=context), validator=validator
    ) == semantic_bytes(value, validator=validator)


def test_shared_color_binding_does_not_silently_override_labels():
    design, material = resolved_artifacts()
    context = PatternParseContext(
        design,
        (
            PatternYarnBinding("Yarn A", material, "Natural", "#C8B08A"),
            PatternYarnBinding("Yarn B", material, "Natural", "#C8B08A"),
        ),
    )
    text = TEXT.replace(
        "Yarn A: external material binding.",
        "Yarn A: external material binding.\nYarn B: external material binding.",
    ).replace("Work 1 sc. (1)", "Work 1 sc. (1)\nChange to Yarn B.\nWork 1 sc. (1)")
    source = parse_pattern(text, context=context)
    validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={material["profile_id"]: material},
    )
    m1b = export_pattern_m1b(source, TerminologyProfile.US_EN, validator=validator)
    shared = m1b.replace("Yarn B: Yarn; color Color B", "Yarn B: Yarn; color Color A")
    parsed = parse_pattern_m1b(shared, context=context)
    assert len(parsed["colors"]) == 1
    wrong = PatternParseContext(
        deepcopy(design),
        (
            context.yarn_bindings[0],
            PatternYarnBinding("Yarn B", material, "Red", "#C8B08A"),
        ),
    )
    with pytest.raises(PatternFormatError):
        parse_pattern_m1b(shared, context=wrong)
