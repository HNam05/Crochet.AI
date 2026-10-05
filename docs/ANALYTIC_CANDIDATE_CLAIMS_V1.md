# Independent analytic candidate claims V1

`ANALYTIC_CANDIDATE_CLAIMS_V1` independently audits candidate claims already
recorded in CrochetIR. It does not invoke the analytic solver, compiler,
balanced-course helper, placement optimizer, geometry decoder or cell verifier.
It reads transport-admitted source artifacts and the populated SemanticValidator
registry, validates the source and computes its canonical hash itself.
Generation, existing semantic validation, schemas and golden files are unchanged.

## Scope and exact predicates

Construction quantities are recomputed from validated raw operations: one sewn
seam per `JOIN` with `join_method=SEWN`, one cut per `CUT_YARN`, one reattachment
per `ATTACH` with nonempty input frontier IDs. These must meet DesignSpec maxima.

The schedule profile is `analytic-closed-sc` generator version `1`, family
`ANALYTIC`, closed single-component/branch/yarn SC amigurumi, MAGIC_RING then
continuous clockwise cyclic courses then CLOSE. Wider valid construction remains
unsupported. No topology proof is inferred here; V5 orchestration requires V4 PASS.

Source course order and member events are authoritative. Recompute ring size,
every course's output count, ordered stitch bases/tops, phase (first base's index
in the declared input cycle), and each plain/increase/decrease count. Every course
covers its entire input cycle exactly once in cyclic order, starting at that phase.
The output frontier is an anchored rotation of produced tops. The initial course
is plain, phase zero, and has the ring size. Final CLOSE consumes the final cycle.
No unaccounted event or stitch is admitted.

For consecutive counts B and A, exact binary SC reachability requires
`B = S + I + 2D`, `A = S + 2I + D`, nonnegative S/I/D and `I*D=0`.
Recomputed counts must obey the recorded per-course shaping maxima. For M stitch
operations and Q shaping events, the balanced convention independently requires
shaped operation indices `ceil(k*M/Q)-1`, for k=1..Q; Q=0 means none. This is a
predicate on source event positions, not a regenerated stitch plan.

The parameter array is sorted by name before recomputing the existing
`ANALYTIC_COMPILER_PARAMETERS_V1` domain hash. Duplicate names are rejected.
Recorded integer bounds reject booleans and must stay inside the existing
version-1 implementation ceilings. Independently compare observed course count,
count range, initial/terminal count, stitch-node count and shaping counts against
`run.*` bounds and `solver.course_count`. Parameter profile and analytic-family
authorization bind to DesignSpec. The selected material response must uniquely
match `solver.material_response_id`, `run.tension_profile_id`, `run.fabric_state`,
SINGLE_CROCHET/CYCLIC conditions and DesignSpec stuffing intent.

When present, `prototype.count_schedule`, `prototype.final_phases` and
`prototype.phase_policy=FIXED_ZERO_CONTINUOUS_V1` must match actual source values.
Absence of all three is a normal solver candidate; partial metadata is incomplete
evidence, not an invented policy. Present unsupported policy remains indeterminate.

Recorded work counters are checked only for integer range and declared budget
consistency. This does not establish their actual work consumption. The compiler's
`CANDIDATE_EVALUATIONS` 1/1 record concerns this compilation, not the full search.
No count-window, geometric reachability, global optimality, search completion,
phase optimality or candidate tie-break claim is accepted from these fields.

## Failure, resources and evidence

Known false source/parameter/hash/limit claims produce FAIL with stable diagnostic
codes/reasons. Missing parameters or missing trace produce INDETERMINATE; valid
wider schedule scope gives NOT_APPLICABLE. A hard construction-limit violation
remains FAIL even outside the analytic schedule scope. Unsupported or missing
evidence never becomes PASS. Full V5 remains INDETERMINATE while the required
input-bound trace, independently confirmed search work/completion, count-window
admission and deterministic candidate-selection evidence are unavailable.

Exact software budgets: 30,000 events, 512 courses, 256 parameters; source
top-level tables and ID reference lists at most 30,000 entries before hashing.
Identifiers/names at most 128 ASCII characters; parameter string values at most
4,096 characters. Internal callers preserve API JSON byte/node/depth admission.
All arithmetic for schedule predicates is integral. No tolerance or target
coordinate enters this audit. Budgets have no physical meaning.

Immutable JCS evidence binds canonical DesignSpec, MaterialProfile and CrochetIR
hashes, assertions, recomputed schedule/construction summary, checked parameter
bounds, diagnostics, missing checks and work budgets. Its hash uses the separate
`Crochet.AI\0ANALYTIC_CANDIDATE_CLAIMS_V1\0` domain. Telemetry is excluded.
Hand-authored IR fixtures and refreshed-parameter-hash mutations are mandatory
oracles, alongside ordinary solver/prototype integration cases.

## Next producer and verifier steps

The separate [producer trace](ANALYTIC_SEARCH_TRACE_V1.md) now records versioned
evidence outside canonical IR: DesignSpec/material/target/run-config hashes,
algorithm versions, exact count windows, hypothesis prefix, per-pass work/state
accounting, terminal reason and ordered proposal hashes. New prototype projects
link final phase-zero IR to the original proposal without claiming the proposal's
optimized placement score for that final IR. Legacy projects have no such trace.

A subsequent independent verifier task must check the trace against bounded
recomputation or explicit exhaustive small-domain oracles, verify the documented
staged count-then-phase choice, and separate its limited optimum from final
V0-V8 feasibility/candidate selection. Missing full geometry gates cannot be
replaced by generation residuals or trace integrity. No such trace is synthesized
by this audit. Its V5 adapter still does not admit producer traces, and both
legacy and newly traced projects remain explicitly incomplete until that
independent task is implemented.
