from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from conftest import load_fixture, make_closed_ir
from test_calibration_store import campaign as campaign_template

from crochet_ai.calibration_campaign import CalibrationCampaign
from crochet_ai.calibration_registry import (
    PROFILE,
    SPECIMEN_DOMAIN,
    CalibrationRegistryError,
    CalibrationReviewRegistry,
    _digest,
)
from crochet_ai.canonical import CanonicalProfile, canonical_hash
from crochet_ai.validation import SemanticValidator


def _bundle(
    design_spec: dict[str, Any], material_profile: dict[str, Any], crochet_ir: dict[str, Any]
) -> dict[str, Any]:
    validator = SemanticValidator(
        design_specs={design_spec["design_spec_id"]: design_spec},
        material_profiles={material_profile["profile_id"]: material_profile},
    )
    artifacts = {
        "design_spec": (design_spec, CanonicalProfile.DESIGN_SPEC),
        "material_profile": (material_profile, CanonicalProfile.MATERIAL_PROFILE),
        "crochet_ir": (crochet_ir, CanonicalProfile.CROCHET_IR),
    }
    hashes = {
        role: canonical_hash(payload, profile, validator=validator)
        for role, (payload, profile) in artifacts.items()
    }
    bindings: dict[str, Any] = {
        "software_commit": "1" * 40,
        "source_snapshot_sha256": "a" * 64,
        "design_spec_sha256": hashes["design_spec"],
        "crochet_ir_sha256": hashes["crochet_ir"],
        "material_profile_sha256": hashes["material_profile"],
        "instructions_sha256": "b" * 64,
        "fixture_id": "fixture_tube_v1",
        "fixture_profile_id": "PHYSICAL_SPHERE_REVIEW_V1",
        "scenario_id": "pilot",
        "loading_recipe_sha256": "c" * 64,
        "verification_profile_id": "BACKEND_SEMANTIC_CHECKPOINT_V1",
        "threshold_profile_id": "threshold_profile_v1",
    }
    specimens = []
    for index in range(1, 4):
        specimens.append(
            _specimen(
                f"cal_tube_{index}",
                "CALIBRATION",
                "CALIBRATION_TUBE",
                {
                    "effective_stitch_pitch_mm": 4.0 + index / 100,
                    "effective_course_pitch_mm": 3.5 + index / 100,
                },
                {"effective_stitch_pitch_mm": "PASS", "effective_course_pitch_mm": "PASS"},
            )
        )
    specimens.append(
        _specimen(
            "heldout_sphere_1",
            "HOLDOUT",
            "SPHERE",
            {"diameter_x_mm": 40.0, "diameter_y_mm": 39.8, "diameter_z_mm": 40.1},
            {"diameters": "PASS", "closure": "PASS", "silhouettes": "PASS"},
        )
    )
    campaign_value = campaign_template().to_dict()
    campaign_value["software_commit"] = bindings["software_commit"]
    campaign_value["source_snapshot_sha256"] = bindings["source_snapshot_sha256"]
    campaign_value["scope"]["yarn_description"] = material_profile["yarn"]["description"]
    campaign_value["scope"]["yarn_lot"] = "fixture_lot"
    campaign_value["scope"]["hook_diameter_mm"] = material_profile["hook_diameter_mm"]
    campaign_value["scope"]["tension_profile_id"] = material_profile["calibration_responses"][0][
        "measurement_conditions"
    ]["tension_profile_id"]
    campaign_value["specimens"] = [
        {
            "specimen_id": f"cal_tube_{index}",
            "role": "CALIBRATION",
            "fixture": "CALIBRATION_TUBE",
        }
        for index in range(1, 4)
    ] + [{"specimen_id": "heldout_sphere_1", "role": "HOLDOUT", "fixture": "SPHERE"}]
    campaign_value["artifact_bindings"]["design_spec_sha256"] = hashes["design_spec"]
    campaign_value["artifact_bindings"]["crochet_ir_sha256"] = hashes["crochet_ir"]
    campaign_value["artifact_bindings"]["instructions_sha256"] = bindings["instructions_sha256"]
    campaign_value["artifact_bindings"]["verification_profile_id"] = bindings[
        "verification_profile_id"
    ]
    campaign_value["artifact_bindings"]["threshold_profile_id"] = bindings["threshold_profile_id"]
    campaign = CalibrationCampaign(campaign_value)
    bindings["campaign_sha256"] = campaign.sha256
    return {
        "profile": PROFILE,
        "record_version": "1.0.0",
        "record_id": "review_record_001",
        "evidence_class": "SYNTHETIC_TEST_ONLY",
        "claim": "PHYSICALLY_VERIFIED",
        "bindings": bindings,
        "campaign": {"payload": campaign.to_dict(), "sha256": campaign.sha256},
        "source_artifacts": {
            role: {"payload": deepcopy(payload), "sha256": hashes[role]}
            for role, (payload, _) in artifacts.items()
        },
        "specimens": specimens,
        "required_checks": ["diameters", "closure", "silhouettes"],
    }


def _specimen(
    specimen_id: str,
    role: str,
    fixture_family: str,
    measurements: dict[str, float],
    checks: dict[str, str],
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "specimen_id": specimen_id,
        "role": role,
        "fixture_family": fixture_family,
        "observed_at": "2026-10-07T12:00:00Z",
        "outcome": "PASS",
        "measurements": [
            {
                "metric_id": metric,
                "value": number,
                "units": "mm",
                "method_id": "direct_measurement_v1",
            }
            for metric, number in measurements.items()
        ],
        "checks": checks,
        "media": [
            {
                "sha256": "d" * 64,
                "view": "scale_photo",
                "privacy_status": "CONSENTED",
                "license_status": "REPOSITORY_RESTRICTED",
            }
        ],
    }
    value["evidence_sha256"] = _digest(SPECIMEN_DOMAIN, value)
    return value


@pytest.fixture
def valid_bundle() -> dict[str, Any]:
    material = load_fixture("material-profile.minimal.valid.json")
    design = load_fixture("design-spec.analytic-sphere.valid.json")
    design["material_profile"] = {"binding_type": "INLINE", "profile": deepcopy(material)}
    ir = make_closed_ir()
    # The independent fixture helper resolves these exact source artifacts.
    return _bundle(design, material, ir)


def _approve(
    registry: CalibrationReviewRegistry, digest: str, *, reviewer: str = "reviewer_1"
) -> None:
    registry.approve(
        digest,
        reviewer_id=reviewer,
        decision="APPROVE",
        note="Reviewed fixture package and exact bindings.",
        attested_at="2026-10-08T12:00:00Z",
        expected_record_sha256=digest,
    )


def test_approved_synthetic_record_remains_nonproduction(
    tmp_path: Path, valid_bundle: dict[str, Any]
) -> None:
    with CalibrationReviewRegistry(
        tmp_path / "review.sqlite3", trusted_reviewers=["reviewer_1"]
    ) as registry:
        admitted = registry.register(valid_bundle)
        assert admitted["state"] == "PENDING_REVIEW"
        _approve(registry, admitted["record_sha256"])
        result = registry.lookup(valid_bundle["bindings"])

    assert result is not None
    assert result["state"] == "SYNTHETIC_TEST_ONLY"
    assert result["review_attestation"] == "PRESENT"
    assert result["reviewer_identity_authenticity"] == "NOT_ESTABLISHED"
    assert result["source_authenticity"] == "NOT_ESTABLISHED"


@pytest.mark.parametrize(
    "defect",
    ["duplicate", "only_two_calibration", "no_holdout", "bad_digest", "scope", "tube_bending"],
)
def test_record_admission_rejects_invalid_specimen_sets_and_bindings(
    valid_bundle: dict[str, Any], defect: str
) -> None:
    bundle = deepcopy(valid_bundle)
    if defect == "duplicate":
        bundle["specimens"][3]["specimen_id"] = bundle["specimens"][0]["specimen_id"]
        specimen = {
            key: value for key, value in bundle["specimens"][3].items() if key != "evidence_sha256"
        }
        bundle["specimens"][3]["evidence_sha256"] = _digest(SPECIMEN_DOMAIN, specimen)
    elif defect == "only_two_calibration":
        bundle["specimens"] = bundle["specimens"][1:]
    elif defect == "no_holdout":
        bundle["specimens"].pop()
    elif defect == "bad_digest":
        bundle["source_artifacts"]["crochet_ir"]["sha256"] = "e" * 64
    elif defect == "scope":
        bundle["bindings"]["material_profile_sha256"] = "e" * 64
    else:
        bundle["required_checks"] = ["bending"]

    with pytest.raises(CalibrationRegistryError):
        _validate_for_test(bundle)


def _validate_for_test(value: dict[str, Any]) -> str:
    from crochet_ai.calibration_registry import _validate_record

    return _validate_record(value)[1]


def test_untrusted_reviewers_cannot_approve_and_status_is_pending(
    tmp_path: Path, valid_bundle: dict[str, Any]
) -> None:
    with CalibrationReviewRegistry(
        tmp_path / "review.sqlite3", trusted_reviewers=["reviewer_1"]
    ) as registry:
        digest = registry.register(valid_bundle)["record_sha256"]
        with pytest.raises(CalibrationRegistryError, match="untrusted_reviewer"):
            _approve(registry, digest, reviewer="caller_claimed_reviewer")
        result = registry.lookup(valid_bundle["bindings"])
    assert result is not None and result["state"] == "PENDING_REVIEW"
    assert result["review_attestation"] == "ABSENT"


def test_lookup_is_exact_immutable_and_survives_reopen(
    tmp_path: Path, valid_bundle: dict[str, Any]
) -> None:
    path = tmp_path / "review.sqlite3"
    with CalibrationReviewRegistry(path, trusted_reviewers=["reviewer_1"]) as registry:
        digest = registry.register(valid_bundle)["record_sha256"]
        _approve(registry, digest)
        with pytest.raises(CalibrationRegistryError, match="record_id_conflict"):
            changed = deepcopy(valid_bundle)
            changed["bindings"]["fixture_id"] = "another_fixture_instance"
            registry.register(changed)
    changed_lookup = dict(valid_bundle["bindings"])
    changed_lookup["crochet_ir_sha256"] = "f" * 64
    with CalibrationReviewRegistry(path, trusted_reviewers=["reviewer_1"]) as reopened:
        assert reopened.lookup(changed_lookup) is None
        result = reopened.lookup(valid_bundle["bindings"])
    assert result is not None and result["state"] == "SYNTHETIC_TEST_ONLY"


def test_attestation_conflict_rolls_back_and_does_not_overwrite(
    tmp_path: Path, valid_bundle: dict[str, Any]
) -> None:
    with CalibrationReviewRegistry(
        tmp_path / "review.sqlite3", trusted_reviewers=["reviewer_1"]
    ) as registry:
        digest = registry.register(valid_bundle)["record_sha256"]
        _approve(registry, digest)
        with pytest.raises(CalibrationRegistryError, match="attestation_conflict"):
            registry.approve(
                digest,
                reviewer_id="reviewer_1",
                decision="REJECT",
                note="Conflicting second decision.",
                attested_at="2026-10-08T13:00:00Z",
                expected_record_sha256=digest,
            )
        result = registry.lookup(valid_bundle["bindings"])
    assert result is not None and result["state"] == "SYNTHETIC_TEST_ONLY"


def test_failed_exact_candidate_trial_surfaces_physical_failure(
    tmp_path: Path, valid_bundle: dict[str, Any]
) -> None:
    bundle = deepcopy(valid_bundle)
    bundle["claim"] = "FAILED_PHYSICAL_TRIAL"
    bundle["evidence_class"] = "MEASURED_EVIDENCE"
    holdout = bundle["specimens"][-1]
    holdout["outcome"] = "FAIL"
    holdout["checks"]["silhouettes"] = "FAIL"
    evidence = {key: value for key, value in holdout.items() if key != "evidence_sha256"}
    holdout["evidence_sha256"] = _digest(SPECIMEN_DOMAIN, evidence)
    with CalibrationReviewRegistry(
        tmp_path / "review.sqlite3", trusted_reviewers=["reviewer_1"]
    ) as registry:
        digest = registry.register(bundle)["record_sha256"]
        _approve(registry, digest)
        result = registry.lookup(bundle["bindings"])
    assert result is not None
    assert result["state"] == "FAIL"
    assert "E_PHYSICAL_VALIDATION" in result["diagnostics"]


def test_symlink_and_traversal_paths_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(CalibrationRegistryError, match="path_traversal"):
        CalibrationReviewRegistry(
            tmp_path / ".." / "outside.sqlite3", trusted_reviewers=["reviewer_1"]
        )
    target = tmp_path / "target.sqlite3"
    target.write_bytes(b"existing bytes")
    link = tmp_path / "alias.sqlite3"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("filesystem does not permit symlink creation")
    before = target.read_bytes()
    with pytest.raises(CalibrationRegistryError, match="symlink_path"):
        CalibrationReviewRegistry(link, trusted_reviewers=["reviewer_1"])
    assert target.read_bytes() == before


def test_existing_nonregistry_database_is_not_overwritten(tmp_path: Path) -> None:
    target = tmp_path / "target.sqlite3"
    target.write_bytes(b"existing bytes")
    before = target.read_bytes()
    with pytest.raises(CalibrationRegistryError, match="unrecognized_database"):
        CalibrationReviewRegistry(target, trusted_reviewers=["reviewer_1"])
    assert target.read_bytes() == before


def test_self_chosen_partial_holdout_checks_cannot_mint_review_claim(
    valid_bundle: dict[str, Any],
) -> None:
    bundle = deepcopy(valid_bundle)
    bundle["required_checks"] = ["diameters"]
    holdout = bundle["specimens"][-1]
    holdout["checks"] = {"diameters": "PASS"}
    payload = {key: value for key, value in holdout.items() if key != "evidence_sha256"}
    holdout["evidence_sha256"] = _digest(SPECIMEN_DOMAIN, payload)
    with pytest.raises(CalibrationRegistryError, match="unsupported_claim_capability"):
        _validate_for_test(bundle)


def test_duplicate_measurement_is_rejected_even_with_recomputed_specimen_hash(
    valid_bundle: dict[str, Any],
) -> None:
    bundle = deepcopy(valid_bundle)
    specimen = bundle["specimens"][0]
    specimen["measurements"].append(deepcopy(specimen["measurements"][0]))
    payload = {key: value for key, value in specimen.items() if key != "evidence_sha256"}
    specimen["evidence_sha256"] = _digest(SPECIMEN_DOMAIN, payload)
    with pytest.raises(CalibrationRegistryError, match="duplicate_measurement"):
        _validate_for_test(bundle)


def test_raw_span_and_reported_pitch_must_agree_independently() -> None:
    from crochet_ai.calibration_registry import _check_profile_matches_tubes

    observations = [
        {
            "specimen_id": f"tube_{i}",
            "stitch_span_count": 10,
            "stitch_span_length_mm": 30,
            "course_span_count": 10,
            "course_span_length_mm": 20,
        }
        for i in range(3)
    ]
    record = {
        "source_artifacts": {
            "material_profile": {
                "payload": {
                    "calibration_responses": [
                        {
                            "measurement_conditions": {
                                "canonical_stitch_type": "SINGLE_CROCHET",
                                "course_mode": "CYCLIC",
                            },
                            "uncertainty": {"basis": "REPLICATE_COMBINED_STANDARD_UNCERTAINTY"},
                            "observations": observations,
                        }
                    ]
                }
            }
        }
    }
    specimens = [
        {
            "specimen_id": observation["specimen_id"],
            "role": "CALIBRATION",
            "measurements": [
                {"metric_id": key, "value": value}
                for key, value in observation.items()
                if key != "specimen_id"
            ]
            + [
                {"metric_id": "effective_stitch_pitch_mm", "value": 3},
                {"metric_id": "effective_course_pitch_mm", "value": 2},
            ],
        }
        for observation in observations
    ]
    _check_profile_matches_tubes(record, specimens)
    specimens[0]["measurements"][-2]["value"] = 300
    with pytest.raises(CalibrationRegistryError, match="profile_pitch_measurement_mismatch"):
        _check_profile_matches_tubes(record, specimens)
