# Local calibration and physical review registry V1

`CalibrationReviewRegistry` stores immutable evidence packages and explicit
review attestations in a separate SQLite database. It supplements the pilot
capture and draft derivation described in [`CALIBRATION_CAMPAIGNS.md`](CALIBRATION_CAMPAIGNS.md).
The requested `DATASET_PLAN.md` is absent from this checkout; the implemented
scope follows [`PHYSICAL_VALIDATION.md`](PHYSICAL_VALIDATION.md),
[`MATERIAL_MODEL.md`](MATERIAL_MODEL.md), and the existing campaign contract.

The registry accepts only `CALIBRATION_PHYSICAL_REVIEW_REGISTRY_V1` records
with closed fields, finite I-JSON values, a 40-character software commit,
content-bound DesignSpec, MaterialProfile, and CrochetIR, explicit source and
scenario bindings, and unique specimen IDs. Each specimen contains raw numeric
observations with units/method IDs, a timezone-aware observed time, media hashes
with privacy/license metadata, checks, and its own domain-separated digest.
The submitted source payloads are semantically validated and rehashed using the
existing canonical DesignSpec, MaterialProfile, and CrochetIR profiles.
The embedded `CalibrationCampaign` is revalidated with its existing constructor;
its digest, source bindings, software commit, snapshot, scenario ID, protocol,
and complete preassigned specimen-role/fixture set must match the review record.
For measured calibration or holdout claims, the tube measurements must exactly
match the three independent specimen observations in the MaterialProfile and
the profile must use the V1 replicate-uncertainty basis.

An accepted evidence package must name at least three distinct
`CALIBRATION_TUBE` specimens and at least one separately identified holdout.
Tube evidence can support only `effective_stitch_pitch_mm` and
`effective_course_pitch_mm`. Sphere, hourglass, and branch holdouts have
separate narrow check vocabularies. This admission does not infer bending,
friction, stretch, or stuffing behavior from tube measurements. A physical
verification claim requires every declared holdout check to pass. A failed
holdout must retain a failed check and is surfaced as `FAIL` with
`E_PHYSICAL_VALIDATION` after review.

Registration only returns `PENDING_REVIEW`; a record's own claim cannot promote
it. An operator separately constructs the registry with a trusted reviewer ID
allowlist, then calls `approve` or `reject` with the exact record hash, reviewer
ID, decision, nonempty note, and explicit timezone-aware attestation time.
`lookup` requires the complete exact binding set and reports the stored claim
only after an approval. Reviewer IDs are allowlist-checked strings supplied by
the local caller. This local implementation does not authenticate the caller,
cryptographically sign approvals, prove that specimens existed, or verify the
truth of measurements. Every lookup therefore reports reviewer identity and
source authenticity as `NOT_ESTABLISHED`; registry approval is an asserted
human-review event, not proof of origin.

Packages marked `SYNTHETIC_TEST_ONLY` remain `SYNTHETIC_TEST_ONLY` after
approval and never produce a physical status. No secret key or network service
is used. The SQLite database uses an application ID, versioned exact table
layout, transactions, unique record/reviewer identities, and append-only rows.
It refuses traversal and symlink paths, unknown databases, record-ID changes,
and conflicting repeat reviews. The path's parent must already exist.

Example:

```python
with CalibrationReviewRegistry(
    Path("artifacts/calibration/review.sqlite3"),
    trusted_reviewers=("reviewer-alice", "reviewer-bob"),
) as registry:
    admission = registry.register(review_package)
    registry.approve(
        admission["record_sha256"],
        reviewer_id="reviewer-alice",
        decision="APPROVE",
        note="Reviewed source hashes, specimen records, and frozen threshold scope.",
        attested_at="2026-10-08T12:00:00Z",
        expected_record_sha256=admission["record_sha256"],
    )
    result = registry.lookup(review_package["bindings"])
```

All timestamps are caller-provided and included in canonical content; the
registry does not derive a current time. No existing schema, API, fixtures, or
goldens are changed. This registry is a local admission primitive, not a V10
runner or a physical validation result by itself.


Primary admission review: every holdout must contain the complete frozen check
set for its fixture family, not a caller-selected nonempty subset. Duplicate
measurement identifiers are invalid; span counts are native positive integers
with dimensionless/count units. A reported calibration pitch must equal its
own declared span/count ratio exactly, in addition to binding the raw readings
into the canonical profile.

Allowlisted reviewer IDs are local attestations, not authenticated identities.
Positive approvals expose `state=REVIEWED_CLAIM` and a separately named
`reviewed_claim`; they leave `physical_status=UNTESTED` and
`release_eligible=false`. A production consumer needs independently established
reviewer/source authenticity before promoting a physical claim. Synthetic
records remain SYNTHETIC_TEST_ONLY and failed trials remain FAIL.
