# Complete prototype proposal snapshots V1

This is a producer/persistence package. It does not change the solver, compiler,
canonical CrochetIR schema, independent trace auditor or V5 gate decisions.
Retain complete original proposals; never regenerate absent historical artifacts.

## Representation and identity

For newly generated local projects, add generation.proposal_bundle and
generation.proposal_bundle_sha256. Bundle fields are exactly:

- profile = PROTOTYPE_PROPOSAL_BUNDLE_V1;
- design_spec_sha256, material_profile_sha256, run_config_sha256 copied from the
  actual emitted trace's bindings;
- search_trace_sha256, proposal_to_final_sha256, final_crochet_ir_sha256;
- proposal_ir_sha256: complete ordered trace terminal proposal-hash list;
- candidate_proposals: original complete raw CrochetIR snapshots in that order.

The bundle hash is SHA256 of ASCII("Crochet.AI") + NUL +
ASCII("PROTOTYPE_PROPOSAL_BUNDLE_V1") + NUL + JCS(bundle). This snapshot profile
preserves the original wire arrays; it does not substitute for the canonical
CrochetIR hash or introduce an alternative construction representation. The
proposal and final canonical hashes retain their existing profiles. The existing
PROTOTYPE_GENERATION_LINK_V1 is retained unchanged and bound into the snapshot.
No numerical tolerance or physical fidelity claim is introduced.

## Bounds, admission and atomic persistence

Use existing PrototypeStore.save_project: project, native snapshot and initial
session are saved atomically in the same SQLite row/transaction. Existing
4 MiB per-project, 64 MiB total payload and 100-project ceilings remain unchanged.
They include complete snapshots and feedback; no new table or database migration
is needed. Oversized new generation fails explicitly; it never stores only a
proposal hash and pretends the original artifact was retained.

Before JCS snapshot hashing, bound nested inputs to 100,000 JSON nodes, depth 64,
128 proposals, strings 4,096 characters and identity keys 128 characters. Native
artifact lists and hashes have equal nonzero lengths and must match trace order.
Identity/hash strings are lowercase SHA256; no permissive scalar coercions.
These are software memory/transport ceilings owned by this snapshot profile.

Read admission checks exact field/version sets, snapshot digest, trace digest,
trace input bindings and ordered proposal hashes, the existing link digest,
selected proposal hash, final/project identity and phase-policy link. Independent
verification of raw IR semantics and staged search claims remains the
responsibility of the unchanged independent auditor. Hash consistency is producer integrity,
not proof of the proposal-to-final semantic relation or authenticated execution.
Link count/proposal-phase arrays must agree with the selected trace hypothesis;
final phases are exact integer zeros, with the fixed policy also present in the
project run configuration. Reject boolean substitutes even when Python numeric
equality would consider them equal. These are internal consistency checks, not
independent proof that final recompilation preserves the original construction.

Absent bundle AND digest means historical hash-only evidence: return no original
proposal artifacts. A partially present or malformed bundle, changed digest or
contradicted binding is an explicit integrity failure, never a legacy fallback.
Repeated generation of an existing project ID returns the existing saved project
and session unchanged, including an older hash-only generation record. Session
and feedback writes retain the original snapshot. No backfill or silent migration.

## Delivery and acceptance

The saved project JSON carries its original snapshots through existing GET,
download, restart and session behavior. The CSRF-protected POST /api/verify uses
these retained proposals as candidate_proposals in search_evidence. Legacy
projects still provide an empty list. Keep API 1.0 request ceilings (2 MB,
100,000 nodes) and server-owned proof budgets unchanged; an oversized verification
request fails explicitly. Do not truncate snapshots to obtain verification.

For admitted new spheres, the unchanged standalone trace audit can now PASS;
prototype V5 remains INDETERMINATE pending independently verified final relation,
physical feasible selection and later gates. Other target samplers remain open.
NOT_VERIFIED and UNTESTED remain visible in the prototype and PDF.

Tests must cover actual producer snapshots/hash order, restart/session/feedback,
historical collisions without backfill, corrupted/refreshed manifest bindings,
partial absence, bounds before hashing, transactional rollback, HTTP delivery to
the unchanged audit, and explicit API-size failure. No golden changes.
