# Analytic search trace V1

This is producer evidence, not independent verification. `ANALYTIC_SEARCH_TRACE_V1`
is separate from canonical CrochetIR. V5 acceptance is unchanged in this task.
No physical, geometric, search-optimality or calibrated validity is inferred from
the trace hash. Existing untraced projects remain valid legacy test projects.

## Binding and immutable envelope

An admitted invocation records canonical DesignSpec and resolved MaterialProfile
hashes; target geometry hash under `ANALYTIC_SEARCH_TARGET_V1`; the sorted exact
run parameters under `ANALYTIC_SEARCH_RUN_CONFIG_V1`; compiler source snapshot
and software commit; solver/count/phase algorithm versions; and a null random
seed (the current implementation is deterministic and uses no RNG).
Target and run-config hashes cover JCS bytes with the standard
`Crochet.AI\0<PROFILE>\0` prefix. The target payload is the validated DesignSpec
geometry object, whose references are also bound by the full DesignSpec hash.
The run payload is the sorted name/value list emitted by `_parameters(config)`.
Exact rational values are encoded as reduced `numerator/denominator` strings.
Circumferences use the exact rational representation of the binary64 calculation,
not decimal rounding. These are solver inputs, not certified geometry bounds.

The separate [coordinate producer](ANALYTIC_COORDINATE_GENERATION_V1.md) uses this
same outer search/count/phase envelope. Coordinate-only samples additionally
record local signed axial_mm; the retained original proposal records the
EXPLICIT_COORDINATE_MERIDIAN_V1 sampler identity and numerical diagnostics.
DesignSpec/target hashes bind its complete authoritative knots. Older paths do
not acquire new fields or parameters. The subsequent
[independent coordinate audit](ANALYTIC_COORDINATE_REPLAY_V1.md) reconstructs these
samples and the staged search; the producer trace itself remains untrusted.

The immutable trace retains JCS bytes and a separate SHA-256 using
`Crochet.AI\0ANALYTIC_SEARCH_TRACE_V1\0`. `to_dict()` returns a fresh value.
API generation and durable jobs expose payload plus hash. Invalid admission
before target/material/config resolution returns null trace/hash, rather than
hashing invalid input or claiming a completed search. Once admitted, every
structured terminal outcome, including partial-batch exhaustion, retains a trace.

## Finite execution record

Course-count hypotheses execute in ascending order. Record the attempted course
count, samples (s/r in mm), exact circumference inputs, and every attempted
inclusive count window, including the first empty intersection.
Window minima/maxima are decimal integer strings, including out-of-range empty
windows; they are never coerced to rounded binary64/I-JSON numbers. Record whether
the complete hypothesis is finished; an interrupted hypothesis is not part of
the completed prefix. Record skipped empty windows and no-feasible count domains.

Count DP records, for both passes, each reached layer's retained-state count,
evaluated predecessor/successor pairs and whether that layer completed. An
interrupted layer is explicit. The first layer costs zero edges. Work counts
include unreachable tested pairs, as in ANALYTIC_COUNT_SEARCH.md. Record count
status/reason, completed passes, final counts/transitions and exact objective.
No partial path/objective is emitted after exhaustion.

Phase DP records each reached transition's variant/state counts, tested
transition and shaping-angle-pair work, and completion. Exhaustion carries these
records through GenerationError; counts and phase schedules are unchanged by
instrumentation. Record chosen phases and generation-only stacking/proximity
objective on success. No phase proposal is fabricated on failure.

Record per-hypothesis compilation outcome and canonical proposal IR hash. Batch
terminal status/reason, completed-prefix count, ordered proposal hashes and work
totals match the returned batch. Configuration-validation probe calls are outside
search work accounting, as before. No raw DP table/path labels are copied into IR.

The staged count-then-phase algorithm is recorded honestly. The batch does not
rank candidates by independent V0-V8 feasibility. It emits an ordered candidate
list; no globally verified selected candidate is declared.

## Resource bound and invariants

Existing deterministic numerical profiles and count/placement budgets remain
authoritative. Instrumentation adds no numerical tolerance. Trace storage reserves
each attempted hypothesis's full course count before sampling, with at most 8,192
reserved course slots per invocation. Before the next hypothesis would exceed
that bound, return SEARCH_BUDGET_EXHAUSTED with `budget.trace_course_slots` and
preserve only fully emitted candidates. This is a software memory ceiling owned
by the trace profile, not mathematical infeasibility. It is part of the trace's
recorded budget. At most 512 hypotheses and the existing 512-course bound apply.
Trace space is O(sum attempted course counts), apart from bounded proposal hashes;
it does not retain O(edges) or full state-label payloads. Runtime telemetry and
timestamps never enter the trace or affect search order.

## Prototype proposal-to-final link

For newly generated projects, persist the immutable producer trace/hash and a
separate generation link: proposal IR hash, final IR hash, producer trace hash,
`FIXED_ZERO_CONTINUOUS_V1`, proposal phases and actual final zero phases. Final
counts are identical to the proposal. Proposal optimized placement scores describe
only that proposal. This link is producer provenance, not proof that recompilation
preserves geometric quality. Neither canonical IR schema nor existing stored
project schema is migrated; absent legacy trace remains absent.

New projects also persist complete original proposal CrochetIR snapshots under
[PROTOTYPE_PROPOSAL_BUNDLE_V1](PROTOTYPE_PROPOSAL_BUNDLE_V1.md). Its separate
domain hash binds this unchanged link, trace, input hashes and ordered artifacts.
Legacy same-ID records are preserved. Snapshot admission is producer integrity;
the independent auditor still owns raw proposal/search checks, and the final
phase-policy relation remains an open independent verification task.

## Independent replay and remaining work

[ANALYTIC_TRACE_AUDIT_V1](ANALYTIC_TRACE_AUDIT_V1.md) now validates sphere and
equal-axis-ellipsoid trace envelopes, bindings, windows and actual DP work/prefix
claims independently, including interrupted passes and refreshed tampered hashes.
The separate coordinate audit and final-relation audit extend the documented
computational scopes. Broader samplers and physical feasible selection remain
open. Trace integrity alone cannot complete V5 or
replace V6-V8/V10 and physical calibration.
