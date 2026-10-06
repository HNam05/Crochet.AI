# Verification pipeline checkpoint

`VERIFICATION_PIPELINE_V1` adds ordered V0–V10 orchestration around the currently
available validators. It records a versioned gate result with the profile, implementation,
input hashes, structured diagnostics, assertion counts, missing checks, produced
artifact hashes and a domain-separated canonical
evidence hash. Runtime telemetry is serialized separately and excluded from evidence and
bundle hashes. Evidence can be resumed only when its digest, exact input hash set, profile
content hash, implementation version, and contiguous gate ordering still match.
Each later gate also binds the predecessor evidence hash. Resumption is an
internal trusted-cache interface; API clients cannot submit evidence, runners,
calibrated profiles or server provenance. Hashes establish integrity links, not
authenticity or proof that an arbitrary internal callback did substantive work.
The orchestrator adds a server-owned `implementation_identity` hash covering the
shared source/schema snapshot and Python/jsonschema/rfc8785 runtime bindings;
changing implementation content invalidates cached evidence even if a declared
runner version was accidentally left unchanged. These names and the predecessor
hash name are reserved. The existing CLI snapshot algorithm is reused through
`backend_provenance.py`; compilation contracts and approved goldens are unchanged.

The built-in `BACKEND_SEMANTIC_CHECKPOINT_V1` requires every gate and is explicitly
uncalibrated. Thus passing available computational checks can at most produce
`EXPERIMENTAL`; absent, indeterminate, or unrun required gates produce `NOT_VERIFIED`,
and a mandatory failure produces `REJECTED`. `VERIFIED` requires all required gates to
pass under a calibrated profile with a calibration evidence hash, known runner
versions, V10 provenance and no warnings. No real calibrated profile is registered
in this checkpoint. Physical validation remains `UNTESTED`.

The artifact adapter validates DesignSpec and MaterialProfile using the bundled
`SemanticValidator`, then uses its one CrochetIR pass and routes diagnostics by their
declared V2, V3, and V4 gate. This attribution does not mean those gates have separate
implementations. Mesh V0 invokes `inspect_v0_mesh_v2` only when supported raw mesh bytes,
budgets, and a schema-valid DesignSpec are present. Analytic V0 separately admits
closed sphere/ellipsoid targets through `ANALYTIC_TARGET_V1`: explicit parameter/frame
resolution, positive finite semiaxes/extent, finite distinct cardinal positions and
the regular ideal primitive topology. Its profile is `V0_ANALYTIC_SHAPE_V1`; the
cardinal predicate count is six, not a complete validation/hash work budget.
The API JSON limits and job watchdog still bound transport and operational work.
It does not infer geometry from schema success or a sampled point cloud.
For admitted closed SC constructions, V4 now builds target-free cells and runs
the independent [surface topology auditor](SURFACE_TOPOLOGY_AUDIT_V1.md).
It checks edge incidence/orientation, connected vertex links, Euler characteristic
and rational Betti dimensions. The separate [source-cell conformance checker](CLOSED_CELL_CONFORMANCE_V1.md)
reads validated raw CrochetIR and checks every face slot against stitch base/top
references, frontier cycles and cap events. V4 passes only when both proofs pass
and the DesignSpec requires compatible closed single-component SC amigurumi
topology. Defective surfaces or mappings fail V4; unsupported construction stays
indeterminate. The adapter version is `closed-cell-source-adapter/1.0.0`.
V4 evidence links projection, cell, audit and conformance hashes, exact budgets
and metrics. `linked_evidence.surface_topology` and `linked_evidence.cell_conformance`
retain the complete separate proof payloads.
V5 now audits [recorded analytic candidate claims](ANALYTIC_CANDIDATE_CLAIMS_V1.md)
only after V1-V4 pass. It independently derives count transitions, balanced
shaping positions, phases and construction quantities from raw source; checks
parameter digests, recorded bounds, material conditions and optional prototype
schedule metadata; and retains a separate immutable proof hash. Known false
claims fail V5. Valid reconstructed claims remain `INDETERMINATE`, because complete
input-bound search work/completion, count-window admission and deterministic
selection evidence are unavailable. Work-counter range checks are not an audit
of actual search execution. The adapter is `analytic-claims-adapter/1.0.0`.
V6-V8 and V10 have no adapter runners and remain `NOT_RUN`.
The separate producer [search trace](ANALYTIC_SEARCH_TRACE_V1.md) is emitted
on new admitted runs. Optional search_evidence now invokes the independent
[trace audit](ANALYTIC_TRACE_AUDIT_V1.md), replaying count windows, count/phase
objectives and exact ties, work, ascending prefix and terminal causes for sphere
and equal-axis-ellipsoid samplers. Original raw proposal IRs bind complete emitted
hashes and schedules. Its own PASS establishes the bounded computational scope;
V5 remains INDETERMINATE pending physical feasible-selection evidence. False
trace claims FAIL V5. Stored prototype hash-only original proposals remain
explicitly incomplete. Legacy untraced requests retain their prior behavior;
no source proposal or search execution evidence is synthesized for them.
V9 performs real single-yarn M1A DE/US/UK text export, parsing, binding from frozen
external metadata and canonical semantic comparison. It retains text hashes.
Multi-yarn V9 and broader M1B/PDF acceptance are still open. A schema failure
prevents V3/V4 execution, including in diagnostic mode.

V0 retains the raw mesh hash, server-owned budget hash, normalized mesh hash and
complete linked preflight evidence (including numerical profile, normalization,
predicates, thresholds, measurements and work budget). No source URI is fetched.
Failed V0 diagnostics remain structured. Native cylinder/cone interface/cap semantics
and generic radial-profile axial signs remain unsupported for this admission;
their V0 is INDETERMINATE. The six existing prototype forms still have their
separate exploratory generation contract. Ideal target topology does not prove
the candidate IR topology or any physical/geometric fidelity gate.

API 1.0 `verify_candidate` requires DesignSpec, MaterialProfile, CrochetIR,
`mesh_json` (null or exact source text), and boolean `diagnostic_mode`.
Optional `search_evidence` has exactly run_config, search_trace and
candidate_proposals. This input is bound into the verification bundle hash.
It always uses `BACKEND_SEMANTIC_CHECKPOINT_V1`. CLI `request` and local durable
jobs expose the same operation. A job's `SUCCEEDED` means the operation completed;
the result can still be NOT_VERIFIED or REJECTED. The prototype adds CSRF-protected
`POST /api/verify` with an exact saved `project_id` and read-only capability
discovery at `/api/capabilities`.

The generic runner API permits later implementations to register typed gate functions,
but does not claim independent verification merely because functions are separately
registered. Runner ownership, common-mode review, calibrated acceptance profiles, full
provenance, forward simulation, comparison, robustness, export round trips, and physical
records remain follow-on work. No numerical tolerances are introduced here.
