# Seamless Topology and Construction Graph

## Status and scope

**FUTURE:** the Seamless Topology Engine is planned, not implemented. This document defines its abstractions and fail-closed obligations.

Its job is to propose how target regions can be traversed and connected with as few sewn seams, yarn cuts, and reattachments as possible. It does not generate final instructions, prove physical feasibility, or bypass the hard geometry gate.

## Three distinct representations

**ENGINEERING DECISION:** the following boundaries are mandatory.

1. Target topology describes the input surface and may include geodesic fields, level sets, critical regions, landmarks, and mesh connectivity.
2. A solver-private `ConstructionGraph` describes a possible construction plan, including regions, frontier obligations, splits, joins, reservations, reattachments, openings, and proposed seams.
3. Canonical `CrochetIR` records the complete executable stitch and construction sequence with explicit frontier transitions.

The Construction Graph is neither CrochetIR nor a pattern. It may contain target-region references and alternatives that are illegal in canonical IR. Shared validation, forward simulation, hashing, and export never treat it as authoritative construction data.

## Construction Graph model

Conceptually, a Construction Graph is a directed, attributed multigraph:

```text
G_C = (R, P, E)
```

- `R` is a finite set of construction regions or episodes.
- `P` is a finite set of typed entry/exit frontier ports owned by regions.
- `E` connects ports and states how a frontier obligation continues: continuous advance, split, reservation, reattachment, join, closure, declared opening, or sewn seam.

Each region records an applicability domain, proposed traversal direction, frontier topology, and target-region reference. Each edge records yarn-continuity intent and an exact obligation. No edge directly asserts stitch IDs or counts.

A graph is compilation-ready only when all ports are paired with a legal edge or terminal policy and there is a deterministic topological execution order. Compilation can still fail when no exact CrochetIR operation sequence realizes the plan.

## Frontier state model

A frontier is the ordered collection of currently available attachment locations for continued construction. Topology and lifecycle are separate:

```text
topology:   LINEAR | CYCLIC
lifecycle:  ACTIVE | RESERVED | CLOSED | DECLARED_OPEN
```

`CLOSED` and `DECLARED_OPEN` are terminal. `DECLARED_OPEN` requires the same non-null `opening_requirement_id` in the `DECLARE_OPENING` operation and the resulting CrochetIR opening. That ID must resolve to `DesignSpec.construction_constraints.intentional_openings`; purpose and closure expectation must agree. It is not an unverified leftover.

### Chosen reference model

V1 uses ordered attachment/loop IDs inside explicit immutable frontier objects with component and branch ownership. It does not use producer stitch IDs, numeric ranges, implicit cursors, or a second persistent-segment entity. A reserved frontier itself is the persistent branch-local segment. See [ADR-0008](adr/0008-ordered-attachment-frontier-ledger.md).

The reference validator maintains a location ledger with exactly four states: active-live, reserved-live, retired, and declared-open-boundary. `CLOSED` is a frontier state whose former locations are retired. No location may be live in two frontiers. Solvers may use ranges or compressed contours privately, but compilation expands them to explicit ordered IDs.

Each stitch carries a yarn-independent frontier edit. `REPLACE_SPAN` names its target frontier and reuses the stitch's exact non-empty base/top lists. `INSERT_AT_GAP` names the target frontier plus nullable left/right neighboring location IDs and reuses the stitch's top list; it is the only edit legal when base arity is zero. No gap index or implicit working cursor enters CrochetIR.

The canonical lifecycle operations are:

| Operation | Preconditions | Result and obligations |
| --- | --- | --- |
| `CREATE` | Valid anchor or produced locations; no reused frontier ID | 0 inputs, 1 `ACTIVE` output, at least one created location |
| `ADVANCE` | One `ACTIVE` frontier; exact supported stitch arities and legal explicit span/gap edit | 1 input/1 `ACTIVE` output; referenced bases retire and new tops are explicit |
| `SPLIT` | One `ACTIVE` frontier and an explicit ordered partition/branch rule | 1 input, at least 2 `ACTIVE` child obligations; no location silently duplicated or lost |
| `RESERVE` | `ACTIVE` frontier not required by the current yarn path | 1 input, at least 2 outputs: exactly one continuing `ACTIVE`, at least one `RESERVED`; reserved locations explicit |
| `REATTACH` | `RESERVED` frontier plus permitted explicit `ATTACH` and yarn transition | 1 `RESERVED` input/1 `ACTIVE` output, no attachment delta; reattachment is counted |
| `JOIN` | Compatible active/reserved frontiers with explicit orientation and location mapping | at least 2 inputs/1 output; all consumed locations and orientations are explicit |
| `CLOSE` | `ACTIVE` frontier with a legal closure realization | 1 input/1 `CLOSED` output; every available input location retires |
| `DECLARE_OPENING` | `ACTIVE` or `RESERVED` frontier and matching DesignSpec opening requirement | 1 input/1 `DECLARED_OPEN` output; boundary order is retained and linked to its opening record |

`JOIN`, `SPLIT`, and `ATTACH` are construction operations, not ordinary stitches. A crocheted join does not automatically count as a sewn seam. Sewn seams, yarn cuts, and reattachments are separately counted construction properties.

## Formal lifecycle invariants

**PROVEN / FORMAL:** a compiled candidate is structurally invalid if any of these predicates is false.

- Every frontier ID has exactly one creation transition.
- Every nonterminal transition consumes the current state exactly once and produces explicitly named successor state(s).
- Frontier order and orientation are explicit; cyclic order is fixed by `anchor_attachment_location_id`, never by an implicit modulo rotation.
- A `REPLACE_SPAN` target is one exact consecutive ordered span of its active input frontier. An `INSERT_AT_GAP` target is one exact adjacent-neighbor pair, or a legal linear end/empty gap. Its target frontier is the transition input; yarn state and work direction cannot select the location.
- A reserved frontier cannot advance. It may be reactivated only by the specified yarn/attach preconditions, or may be consumed directly by a final `JOIN` whose explicit mapping discharges that obligation without new yarn work.
- A closed or declared-open frontier has no outgoing transition.
- Split outputs are disjoint ordered partitions of the input boundary; silent loss, duplication, and shared live junction locations are forbidden in V1.
- Join inputs are distinct obligations and their orientation mapping is explicit.
- Every created or split branch eventually reaches `CLOSED` or `DECLARED_OPEN`.
- Every declared opening has an exact, non-null `DesignSpec` opening-requirement reference shared by the operation and opening record.
- Every yarn discontinuity and sewn seam is represented and counted.
- No target-mesh reference is needed to execute or validate CrochetIR frontier semantics.

The semantic validator, not the solver, independently checks these invariants.

## Required scenario realizations

These examples define reference-model obligations, not solver availability:

| Scenario | Frontier realization |
| --- | --- |
| Sphere with joined rounds | `CREATE` one cyclic frontier; ordered `ADVANCE` rewrites per round; terminal `CLOSE` |
| Continuous spiral | One anchored cyclic frontier; course/event order advances it without an implicit round join |
| Flat row | Linear frontier; `TURN` changes course work direction while the stored boundary order stays explicit |
| Y branch | One active frontier `SPLIT` into disjoint branch-local child frontiers; no shared live location |
| Two legs | Independent created components/frontiers or one explicit split, followed by an oriented `JOIN` when the body begins |
| Sleeve opening | Boundary becomes `DECLARED_OPEN` only when it remains open in the target/design; otherwise it is a reserved construction obligation |
| Reserved armhole | `RESERVE` partitions one active sequence into one continuing active and one reserved frontier |
| Branch reattachment | `ATTACH` plus `REATTACH` changes the exact reserved sequence back to active and counts a reattachment |
| Frontier merge | Oriented `JOIN` retires declared join sites and concatenates the remaining sequences; empty remainder produces `CLOSED` |
| Intentional opening | `DECLARE_OPENING` retains the exact ordered boundary and matching DesignSpec requirement |
| Lace chain space | A capability-gated `CHAIN_SPACE` attachment location participates in the same ledger; V1 core rejects the capability rather than inventing semantics |

A scenario that cannot be represented with these rewrites is unsupported under V1. The validator must not approximate it through stitch IDs or range arithmetic.

## Topology-planning pipeline

For suitable target geometry, a future engine may:

1. compute one or more deterministic geodesic or other scalar fields;
2. extract regular level-set components;
3. isolate stable critical intervals;
4. construct a Reeb-style summary of component births, deaths, splits, joins, and cycles;
5. decompose it into candidate construction regions;
6. enumerate bounded Construction Graph alternatives;
7. attach frontier/yarn obligations and proposed seam alternatives;
8. ask a domain solver to realize each plan as complete CrochetIR;
9. send candidates through independent validation, simulation, and geometry verification.

- **ESTABLISHED:** Morse/Reeb-style summaries are useful for reasoning about level-set connectivity under appropriate regularity conditions.
- **ENGINEERING DECISION:** they are topology-planning aids only.
- **HYPOTHESIS:** the resulting branch decompositions correlate with practical seamless crochet strategies.

A topologically coherent plan can still be unreachable by supported stitch arities, collide physically, require excessive distortion, or fail the geometry threshold.

## Seamless optimization

For every independently verified candidate, construction quality reports at least:

```text
sewn_seam_count
yarn_cut_count
yarn_reattachment_count
```

Seamlessness is optimized only among candidates that pass structural/topology gates, independent forward simulation, and every hard geometry threshold. The global ordering is defined in `SOLVER_ARCHITECTURE.md`.

The topology engine may use lower bounds, such as a minimum number of unavoidable graph discontinuities, to prune a plan. Unless the bound is formally proven for the declared operation set, it is a heuristic and cannot justify `NO_FEASIBLE_CONSTRUCTION`.

## Bounded exploration

Every run declares positive integer budgets:

| Parameter | Unit | Bound |
| --- | --- | --- |
| `max_scalar_field_hypotheses` | fields | Traversal orientations/seeds |
| `max_critical_regions` | regions | Stable topology events admitted |
| `max_construction_graphs` | graphs | Complete plans generated |
| `max_graph_states` | partial plans | Branch-and-bound states expanded |
| `max_backtracks` | alternatives | Revisited split/join/seam choices |
| `max_compile_attempts` | plans | Plans sent to a CrochetIR compiler |

Exhausting a counter before complete enumeration returns `SEARCH_BUDGET_EXHAUSTED`, never a proof that no seamless or feasible construction exists. The report includes the limiting counter and best lower bounds found.

## Numerical tolerances

All values come from a versioned profile; none is implicit.

| Tolerance | Unit | Purpose | Owner / validation path |
| --- | --- | --- | --- |
| `critical_value_separation_mm` | mm | Isolates distinct scalar-field events | Topology engine / two-lobe, Y-branch, torus fixtures |
| `level_component_merge_mm` | mm | Decides whether contour fragments form one component | Contour extractor / remeshing and noise tests |
| `junction_orientation_tolerance_rad` | rad | Detects ambiguous join orientation | Topology compiler / mirrored and twisted-join fixtures |
| `topology_persistence_floor_mm` | mm | Filters short-lived numerical features, when explicitly enabled | Topology engine / convergence study; **HYPOTHESIS** until calibrated |

Filtering a feature changes the declared planning domain and must be recorded. It is not silent mesh repair.

## Counterexamples and degenerate cases

- A split that places one attachment location in two child frontiers duplicates a branch resource and is invalid.
- A split that leaves one location in no child frontier creates an unaccounted boundary and is invalid unless that boundary is explicitly closed/opened.
- Joining two cyclic frontiers with opposite or ambiguous orientation can create a twist or crossing even when counts match.
- Reserving a sleeve/limb frontier and never resuming or declaring it open leaves a hard `E_FRONTIER` failure.
- A torus/handle introduces a level-set split and later merge; treating all contours as one simple course sequence loses topology.
- Equal or near-equal saddle values can make branch order mesh-dependent. The safe result is topology instability or bounded alternative enumeration.
- A Reeb-style graph can be topologically correct while every supported crochet realization exceeds geometric or material limits.
- A cyclic boundary array rotated while retaining the old anchor is invalid; silently accepting it makes shaping positions and join orientation parser-dependent.
- A join that consumes a site but also carries it into the output leaves one location both retired and live and is invalid.
- Reattaching a reserved armhole by numeric index after earlier insertions can select different locations across implementations; explicit IDs avoid the ambiguity.
- A chain whose output happens to appear between two locations but whose edit omits those neighbors is invalid; output-array differencing cannot reconstruct the missing intent.
- A cyclic insertion that names two existing but non-adjacent neighbors is invalid even if inserting there would produce the declared output array after reordering.

## Unsupported bootstrap claims

The bootstrap does not claim complete Morse theory on arbitrary meshes, globally optimal seamless decomposition, physical feasibility of branches, automatic seam necessity proofs, or support for all garment/lace constructions.
