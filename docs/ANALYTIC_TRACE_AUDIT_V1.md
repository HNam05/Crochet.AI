# Independent analytic trace audit V1

This verifier is separate from generation. It must not import analytic_solver,
analytic_counts, analytic_placement, analytic_compile, analytic_geometry,
balanced_course or the producer trace builder. SemanticValidator, canonical
hashing, the existing raw-IR candidate-claims auditor and standard arithmetic
are admissible common infrastructure, with the trust boundary recorded here.

## Complete bounded audit package

Inputs are validated DesignSpec, MaterialProfile, wire-format run config,
untrusted ANALYTIC_SEARCH_TRACE_V1 payload and complete proposal CrochetIR list.
The original API remains valid; trace evidence is an additive optional extension.
Standalone audit returns an immutable domain-hashed report; no client proof or
proof-budget overrides are accepted at the API boundary.

Recompute design/material/target/run-config digests. Validate all trace fields,
native scalar types, algorithm versions and null unused RNG seed. Bind source
commit/snapshot and run parameters to every supplied raw proposal's provenance.
Bound source tables before hashing and trace hypotheses, layers, rationals and
string lengths before replay. A refreshed malicious hash never substitutes for
recomputation. Missing proposal artifacts or unsupported target arithmetic leave
INDETERMINATE; false supported claims FAIL. Malformed input raises E_INPUT.

The first complete target scope is closed spheres, including equal-axis
ellipsoids. Resolve radius from the validated measurement reference. Independently
compute midpoint fractions (2i+1)/(2m), binary64 meridian length pi*radius,
folded symmetric sine radius (exact equatorial radius at midpoint), sample arc
coordinate and circumference 2*pi*radius. Match exact rational representations
of these deterministic binary64 results. This checks the declared arithmetic
policy, not real-number accuracy or physical fidelity. Other target samplers
remain explicitly unsupported; there is no invented numerical tolerance.

Rebuild integer windows using exact circumferences/pitch and the recorded
run constraints, including allowed shaping, initial ring and terminal bounds;
confirm the first empty intersection and all skip outcomes. Replay every reached
count and phase pass/layer independently and compare all work/state/completion
records, returned schedules, exact objectives and tie breaks. Count recurrence
and phase history conventions are normative in ANALYTIC_COUNT_SEARCH.md and
ANALYTIC_SOLVER.md. They must be implemented independently and tested against
separate tiny exhaustive oracles. No globally combined count-and-phase optimum
is claimed: this is a staged algorithm.

Confirm the ascending attempted prefix, reserved course slots, global remaining
work/candidate/hypothesis budgets, terminal cause and complete emitted proposal
hash order. Independently recompute each proposal's raw count/phase schedule and
construction bounds. Never trust a solver success flag or inferred partial path.
Missing source proposals are not synthesized from compiler output.

## Replay kernels and resource ownership

The independent count kernel takes exact circumference/pitch Fractions, inclusive
integer window tuples, shaping limits and its own CountReplayBudget. It returns
the producer-record-compatible count_status/reason/completed_passes/layers,
counts/transitions/objective mapping plus recomputed used edges. It covers no-path,
state/window/course exhaustion and either interrupted pass with no partial path.

The independent phase kernel takes count tuple, exact separation Fraction and
its own PhaseReplayBudget. It returns status/reason, compatible layers, phases/
stacking/proximity only on completion, and used transitions/pairs. Generate
balanced shaped base ordinals by independent integer reasoning, never calling
balanced_course. Sort state histories and exact ties as specified. Variants,
transition and pair exhaustion preserve exact interrupted-layer work.

Both kernels use TraceReplayWork from trace_verification_types: one proof unit
per replayed count/phase edge or angle pair, at most 6,000,000 for the whole audit.
This matches the existing aggregate software ceilings, has no physical meaning,
and is owned by this audit profile. Exhausted proof yields INDETERMINATE without
a partial accepted proof. Source/trace slots remain at most 8,192, courses 512,
proposals 128, source construction events 30,000 per proposal, and parameter
names/identity strings 128 ASCII; fraction/string values at most 4,096 characters.
Input Fractions honor existing 256-bit numerator/128-bit denominator limits for
the count kernel; result objective strings are exact reduced fractions.

PASS means every required check in this computational audit scope completed.
It never means V6-V8/V10, physical calibration or whole backend acceptance passed.
Source hashes are checked for consistency across the trace and proposal artifacts;
this is not source authentication or evidence that the claimed software executed.
Historical proposals need not match current HEAD. The report explicitly retains
source_authentication=NOT_VERIFIED and physical_status=UNTESTED; V10 remains open.
Prototype fixed-zero recompilation requires the original proposal artifact to
establish its source relation; a hash-only producer link remains incomplete.
The prior raw candidate-claims API and legacy untraced projects keep their status.

## Integration and independent oracles

Add standalone inspect_analytic_search_trace API/CLI/job operation. Optional
search_evidence on verify_candidate contains run_config, search_trace and
candidate_proposals. Existing requests remain accepted. V5 retains its original
raw-IR assertions; the independent audit contributes exact search evidence.
Do not accept a partial/scope-limited replay as a global feasible-selection proof.
The prototype can pass its stored trace for diagnostic replay while reporting
the missing original proposal artifact explicitly. No producer is changed here.

Adversarial fixtures must alter windows, work, prefix, source/config/material
bindings, phase ties and proposal hashes after refreshing envelope hashes.
Small hand/exhaustive oracles and supported real generated spheres are separate
tests. Gate routing, legacy compatibility and installed/HTTP evidence agreement
are integration checks. Keep the full physical/backend roadmap unchanged.
