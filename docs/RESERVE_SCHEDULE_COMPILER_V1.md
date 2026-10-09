# Explicit Reserve Schedule Compiler V1

## Scope

`compile_reserve_schedule` compiles one finite, explicit cyclic single-crochet
schedule into complete CrochetIR using the approved core 1.1 profile. The
supported sequence is a magic-ring initial course, exactly one ordered
`RESERVE` partition into a nonempty active prefix and nonempty reserved suffix,
one or more active-prefix SC courses, then `CLOSE` of both terminal frontiers.
Continued courses use the existing deterministic balanced binary SC shaping
rule with caller-supplied counts and phases. No search or numerical tolerance
is used.

The initial course reuses `compile_closed_schedule`'s core lowering privately,
then removes only that temporary terminal close and its associated event,
frontier, transition, derivation, and yarn event membership. The temporary IR
is never returned. The reserve compiler adds the actual reserve, continuation,
and close lifecycle and independently validates the complete final IR.

## Inputs and limits

Inputs are a semantically valid DesignSpec and resolved MaterialProfile,
`initial_count`, `reserved_count`, `continuing_counts`,
`continuing_phases`, and `CompileProvenance`. The DesignSpec must allow
`MAGIC_RING`, `RESERVE`, `CLOSE`, and `SINGLE_CROCHET`; the supported domain is
single-color closed `AMIGURUMI_3D`. `continuing_counts` and phases are immutable
tuples of equal nonzero length. Each phase is an explicit cyclic base-index
rotation for the deterministic balanced transition.
The DesignSpec must explicitly admit the `FRONTIER` family. Its declared seed
and parameter profile are recorded, although this compiler performs no random
search and evaluates only one caller-provided schedule.

The caller may lower operational limits, but cannot raise `max_events` above
8,192, `max_attachment_locations` above 16,384, or
`max_frontier_location_references` above 262,144. The latter bounds repeated
location membership across immutable frontier snapshots, not just unique IDs.
These are operational memory/work ceilings, not numerical tolerances. Schedule
bounds and exact event/location/membership counts are checked before emission.
For initial count N, attachment count is `2*N + sum(continuing_counts)`:
both the ring insertion sites and initial SC tops are counted. Event count is
`N + 4 + sum(min(before, after))` for feasible binary transitions. Initial and
partition snapshots contribute `N*(N+2)` membership references; every actual
continued stitch contributes its resulting live-frontier length. Final output
counts are checked against those preflight totals. Invalid
inputs raise `INVALID_SOLVER_INPUT`, unsupported design scope raises
`NOT_APPLICABLE`, impossible balanced arity raises `NO_FEASIBLE_CONSTRUCTION`,
and budget overflow raises `SEARCH_BUDGET_EXHAUSTED`. No partial IR is returned.

All schedule values, limits, source snapshot, DesignSpec hash, and material
hash are included in the canonical solver parameter list. Provenance uses
`solver_family=FRONTIER`, `FRONTIER_SEARCH` derivations, and the separate
`EXPLICIT_RESERVE_SC_COMPILER_PARAMETERS_V1` hash domain. Inputs are copied
before validation or compilation; returned tables are newly owned values.
Caller provenance cannot overwrite compiler-owned parameter names. Material
identities are validated before registry lookup, including immutable REFERENCE
bindings; malformed/unhashable identities produce explicit rejection.

## Transport

The API/CLI/jobs operation is `compile_reserve_schedule`. Request fields are
`api_version`, `operation`, `design_spec`, `material_profile`, and `schedule`.
The exact schedule object contains `profile="EXPLICIT_RESERVE_SC_V1"`,
`initial_count`, `reserved_count`, array-valued `continuing_counts` and
`continuing_phases`, `max_events`, `max_attachment_locations`, and
`max_frontier_location_references`. There are no client-owned source/commit
overrides. A positive response reports `COMPILED_STRUCTURAL_PROPOSAL`, canonical
IR/hash, actual work, `NOT_VERIFIED` and `UNTESTED`. It explicitly reports
`visible_export_available=false` and `forward_simulation_available=false`.
This operation is not wired into the six-shape human-test UI.

## Structural meaning and limits

Every emitted stitch, operation, course, event, frontier snapshot, transition,
yarn event, branch/component terminal, and derivation is explicit. The active
and reserved frontiers remain obligations in the existing single branch and
component records; this compiler does not claim a branch DAG decomposition.
Both are closed directly after active continuation. This is a structural
construction proposal, not a two-leg garment solver, geometry/topology solver,
pattern instruction compiler, or physically verified crochet pattern.

The unchanged `SemanticValidator` is the acceptance check for emitted IR.
Its reserve ledger catches lost or duplicated reservation locations and
advancement from a reserved frontier. Structural validation does not establish
geometric fit, material feasibility, human usability, or physical acceptance.
