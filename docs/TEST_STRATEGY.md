# Test strategy

## Test objective

- **PROVEN / FORMAL:** Tests for exact representation invariants use exact oracles; numerical tolerances are not substitutes for graph, count, reference, or state-machine equality.
- **ENGINEERING DECISION:** Tests are designed to falsify implementations. Valid examples alone are insufficient.
- **ENGINEERING DECISION:** Python property and stateful tests use Hypothesis unless a documented technical constraint prevents it.
- **ENGINEERING DECISION:** A solver and its independent verifier do not normally change in the same implementation task.

The test suite protects the contracts in `docs/`, especially [`CROCHET_IR.md`](CROCHET_IR.md), [`VERIFICATION.md`](VERIFICATION.md), and [`FAILURE_POLICY.md`](FAILURE_POLICY.md). A failed test is evidence to investigate, not permission to weaken an invariant, tolerance, example count, or expected output.

## Directory responsibilities

| Directory | Defect class and oracle |
| --- | --- |
| `tests/unit/` | Pure local behavior, canonical stitch tables, exact arithmetic/accounting helpers, parsers, and schema utilities |
| `tests/property/` | Hypothesis-generated valid and invalid DesignSpecs, CrochetIR artifacts, MaterialProfiles, graphs, and meshes |
| `tests/stateful/` | Rule-based frontier, yarn, branch, course, reservation, split, join, and closure machines |
| `tests/metamorphic/` | Input transformations with invariant or covariant outcomes where no single expected pattern is unique |
| `tests/integration/` | Schema-to-semantic-validator, solver-to-IR, IR-to-forward-model, comparator, and export/parser boundaries |
| `tests/golden/` | Human-approved canonical bytes, expected diagnostics, gate vectors, and metric envelopes |
| `tests/physical/` | Immutable specimen records and measured comparison results; never routine unit-test data |
| `tests/fixtures/` | Reusable generated geometry, DesignSpecs, MaterialProfiles, malformed artifacts, and fixture manifests |

Tests MUST not import helper logic from the exact production function they claim to verify when that would reproduce the same bug. Shared schema types are acceptable; shared accounting, state-transition, geometry-comparison, or canonicalization implementations require a stated common-mode justification.

## Test profiles

| Profile | Trigger | Contents | Budget rule |
| --- | --- | --- | --- |
| `quick` | Local completion/stop hook | schema validation, deterministic canonicalization, focused unit tests, smoke round trip, bounded property examples | Must be fast and deterministic; no geometry Monte Carlo |
| `pr` | Proposed integration | full unit/property/stateful suites, integration fixtures, approved goldens, small deterministic geometry set | Fixed work budgets; failures preserve replay seeds |
| `nightly` | Scheduled | adversarial meshes, high-example property tests, solver cross-checks, collision cases, robustness samples, retessellations | Budget and machine class recorded |
| `release` | Version candidate | all computational gates, approved benchmark suite, provenance audit, frozen threshold profile | No automatic golden or threshold changes |
| `physical` | Controlled campaign | specimen protocols, measurements, holdouts, photos/scans, physical metric comparison | Human-run; never required as an external CI oracle |

Reducing Hypothesis examples, search depth, mesh resolution, or numerical precision solely to make a failure disappear is forbidden. A legitimate budget change documents coverage impact and receives review.

## Unit and contract tests

At minimum, unit tests cover:

- `CROCHET_CORE_1.0.0` lookup: plain six-family stitches, binary SC shaping, and explicit rejection of non-SC/n-ary shaping;
- base/top arity and attachment-location accounting;
- `REPLACE_SPAN` and `INSERT_AT_GAP` legality for linear beginning/end/internal/empty gaps, cyclic adjacent/wrap/singleton gaps, and every non-adjacent/null/implicit-anchor rejection;
- unique IDs and typed reference resolution;
- finite-number and unit validation;
- canonical serialization, I-JSON/binary64 acceptance, safe-integer rejection, negative-zero normalization, collection ordering, profile-domain separation, idempotence, RFC 8785 vectors, and stable project hashes from [`CANONICALIZATION.md`](CANONICALIZATION.md);
- every legal and illegal frontier transition in the specification table;
- exact course, branch, yarn-cut, reattachment, seam, and opening counts;
- every failure code's minimum diagnostic fields and deterministic ordering;
- every independent-forward outcome mapping, where only `CONVERGED` can pass V6;
- per-metric threshold comparison, including exact equality at open and closed boundaries;
- overall-state precedence from gate outcomes;
- German, US English, and UK English terminology mappings at export boundaries.

Boundary tests include zero, one, maximum supported count, non-finite values, duplicate IDs, wrong-kind references, empty frontiers, cyclic wraparound, and budget exactly exhausted.

## Hypothesis property tests

### Generator rules

Generators are versioned test assets and MUST be independent of production construction routines. They produce:

1. valid minimal artifacts;
2. valid recursively composed artifacts within an explicit size budget;
3. artifacts containing exactly one labelled defect;
4. adversarial artifacts containing multiple defects with a deterministic expected primary-code policy.

Generated invalid cases assert both rejection and the expected failure category. At least the primary code, gate, artifact pointer/entity reference, and observed/expected context are checked. Shrinking MUST preserve the labelled defect; otherwise the test rejects that shrink and continues.

### Required properties

- Schema-valid canonical artifacts survive parse, canonicalize, serialize, and reparse without semantic change.
- Canonicalization is idempotent and independent of object-key insertion order and unordered collection order.
- Inline MaterialProfile permutation is normalized by the independent material projection before DesignSpec hashing, including distinct repeated readings from one specimen; meaningful arrays remain order-sensitive.
- Alpha-renaming explicit IDs preserves semantic equivalence after canonical ID normalization.
- Independently recomputed counts and arities equal declarations for every generated valid IR.
- Replacing one reference with a dangling or wrong-kind ID always fails V2/V3 with `E_REFERENCE`.
- Mutating one course count or stitch arity always fails V3 with `E_COUNT`.
- Removing a required frontier transition, reservation resolution, or opening declaration always fails V4 with `E_FRONTIER` or `E_TOPOLOGY`.
- Repeating identical inputs, versions, parameters, budget, and seed produces byte-identical canonical IR and evidence except excluded telemetry.
- Export and parse preserve semantic graph equivalence for every supported locale and generated supported construction.
- Failure aggregation is monotone: adding a failing mandatory gate cannot improve overall state.

Every new property reports in its test docstring or metadata: invariant, generated domain, independent oracle, expected failure code for negative cases, and replay/minimized-counterexample procedure.

## Stateful frontier testing

Use a Hypothesis `RuleBasedStateMachine` with a small specification-only reference model, not the production frontier class. Model pools include active linear/cyclic frontiers, reserved segments, closed frontiers, branch tokens, active yarns, and declared openings.

Rules cover:

- create linear or cyclic frontier;
- advance by a valid supported stitch operation;
- insert a zero-base chain only at a generated legal explicit gap and attempt missing, non-adjacent, reversed, and wrong-frontier anchors;
- split and create accounted branch states;
- reserve a contiguous ordered segment;
- cut, attach, and reattach yarn explicitly;
- join compatible frontiers;
- close a frontier;
- declare an intentional opening;
- attempt each operation with incompatible state, orientation, ownership, arity, or yarn.

After every valid step, assert unique ownership, deterministic order, reference closure, yarn continuity, and conservation of all frontier locations among active-live, reserved-live, retired, or declared-open-boundary states. `CLOSED` is tested as a frontier lifecycle state with no owned locations. At terminal state, assert zero unaccounted branches and zero unintended open boundaries. Negative rules assert that state is unchanged and the precise error category is returned.

The location oracle uses the exact four-state ledger: active-live, reserved-live, retired, or declared-open-boundary. `CLOSED` is checked as a frontier terminal whose input locations became retired. Generated cases include sphere, continuous spiral, flat row, Y branch, two legs, sleeve opening, reserved armhole, branch reattachment, frontier merge, intentional opening, and capability-gated lace chain space. No test helper may replace IDs with numeric ranges.

Persist every minimized state-machine counterexample as a normal regression fixture after review.

## Metamorphic tests

Metamorphic tests compare invariants and independently reconstructed outcomes, not raw solver stitch counts when multiple correct patterns exist.

| Transformation | Required relation |
| --- | --- |
| Translation | Translating target and declared coordinate-bound landmarks preserves semantic construction choice and dimensionless metric vector; predicted geometry translates by the same vector. |
| Rigid rotation | Rotating target and coordinate-bound inputs preserves graph semantics and metrics; predicted geometry rotates accordingly. No world-axis heuristic may change topology. |
| Uniform scale covariance | Scaling target dimensions, material pitches, loads/boundaries, and tolerances by factor `s > 0` preserves canonical construction semantics and dimensionless metrics; predicted lengths scale by `s`. |
| Mirror symmetry | Mirroring a mirror-permitted DesignSpec yields an orientation-adjusted graph isomorph, mirrored predicted geometry, and equal scalar distance metrics; chirality-sensitive constraints are toggled explicitly. |
| Mesh retessellation | Deterministic equivalent tessellations of the same surface preserve V0 topology and remain within the retessellation robustness envelope. CrochetIR may differ, so comparison uses V6/V7 outcomes and declared invariants. |
| Winding normalization | A consistently reversed closed orientable mesh normalizes to the same canonical orientation event and equivalent downstream evidence. Mixed or ambiguous winding fails rather than being guessed. |
| Export/parse | Formatting, line wrapping, and supported localized terminology changes parse to semantically equivalent canonical IR. |
| Reasonable gauge monotonicity | On monotone analytic cylinder/cone fixtures with all other constraints fixed, increasing effective stitch pitch cannot increase the direct circumference count target. End-to-end integer optimization is checked against a documented monotone envelope, not an unjustified per-course equality. |

Numerical metamorphic comparisons use versioned, unit-bearing tolerances. A transformation test MUST record whether the expected relation is exact, invariant within tolerance, or covariant.

Domain-preflight negatives additionally cover a missing sphere face, locally reversed face, non-manifold edge, repeated-index triangle, self-intersection, touching components, unmatched garment boundary, garment-panel overlap, flat work supplied as `MESH_3D`, and lace holes incorrectly sent through a closed-surface profile. Repairs are never applied inside a passing test.

## V0 geometry-contract tests

The V0 suite independently constructs `IndexedTriangleMeshV1` fixtures and must not use the production parser or adjacency builder as its oracle. Exact cases cover zero/negative/out-of-range/fractional indices after adapter resolution, repeated indices, duplicate and reversed-duplicate faces, coordinate-equal distinct vertices, isolated faces, non-manifold edges, bow-tie vertices, boundary chains/branches, non-orientable components, locally inconsistent winding, and source-renumber/order invariance.

Numerical cases resolve `v0_num_mesh_binary64_v1` from its machine-readable record and cover proper intersection, intended shared-edge/shared-vertex adjacency, extra overlap across an intended entity, vertex-face touch, edge-edge touch, coplanar overlap, coincident triangles, same-component near contact, inter-component touch/near contact, unreliable signed volume, and ambiguous landmark assignment. Every threshold is tested at the representable value immediately below, exactly at, and immediately above its boundary. Tests scale and translate every suitable case by at least `1e-6` and `1e6`, with corresponding unit/tolerance conversion, and require the same classification and canonical diagnostic relation.

Property generators search for invalid incidence ledgers, disconnected vertex links, boundary degree other than two, permutation-sensitive results, hidden fixed-unit epsilons, and predicate results that change with traversal order. If a robust backend cannot certify a required sign or interval side, the asserted result is `INDETERMINATE`; a fallback approximate sign is never accepted. Golden files remain read-only.

## Semantic-equivalence adversarial matrix

| Mutation after export/parse | V1 relation |
| --- | --- |
| Alpha-renamed IDs and reordered entity tables | Equivalent |
| German/US/UK wording that maps to the same canonical families | Equivalent |
| Different display labels or solver derivations | Equivalent; V10 retains lineage separately |
| Reordered course or independent-component execution | Not equivalent |
| Two plain SC nodes replacing one SC increase | Not equivalent |
| Reversed join mapping or work direction | Not equivalent |
| Different material-profile hash or color transition | Not equivalent |
| Cyclic boundary rotated away from its anchor | Invalid before equivalence |

The oracle constructs the execution-normalized projection independently of the production exporter/parser. It compares JCS bytes, not a generic graph-isomorphism library.

## Solver/verifier separation tests

- A solver test may inspect its own trace, but acceptance requires the independent semantic verifier and forward model.
- Verifier fixtures include adversarial candidates that satisfy solver bookkeeping while violating the canonical contract.
- Forward-model tests include target-like solver embeddings and assert the V6 interface rejects them.
- Comparator tests use synthetic predicted surfaces generated without solver code.
- Diverse solver comparison evaluates independently simulated geometry and invariants, never majority votes over counts.

An exceptional change spanning solver and independent verifier requires separate commits or clearly separated diffs, independent review, a common-mode-risk note, and at least one adversarial test that would fail if both implementations shared the same mistaken assumption.

## Numerical testing

Every tolerance record includes value, unit, comparison operator, rationale, owning subsystem, calibration path, and profile version. Tests cover values immediately below, exactly at, and immediately above each threshold using representable numbers appropriate to the implementation.

Numerical solvers are tested for convergence status, residual history, finite outputs, deterministic work budget, sensitivity to mesh resolution, and explicit `DIVERGED`, `BUDGET_EXHAUSTED`, `NUMERICAL_FAILURE`, and `UNRESOLVED_COLLISION` paths. A convergence flag alone is not an oracle; residuals and independent invariants are checked.

## Golden controls

Golden fixtures are defined in [`BENCHMARKS.md`](BENCHMARKS.md). Every approved golden contains:

- fixture and schema version;
- input hashes and canonical generation recipe;
- expected canonical artifact hash or expected rejection code;
- expected V0-V10 outcome vector;
- metric envelope and threshold-profile ID where numerical;
- solver, verifier, forward-model, parser/exporter, and metric versions;
- approval record with reviewer identity, date, rationale, and issue/change reference.

Ordinary test execution is read-only. No test or helper has an `--update`, snapshot-rewrite, or auto-accept path. A proposed replacement is emitted outside `tests/golden/`, diffed semantically and bytewise, then copied only after explicit human approval. CI rejects an unapproved expected-output change.

Goldens are not universal truth. They pin reviewed behavior for a versioned contract. A schema or algorithm improvement may legitimately propose a new golden, but it cannot silently rewrite history.

## Regression and failure handling

Every confirmed defect receives the smallest reproducing test at the lowest adequate layer. Preserve the original seed and minimized counterexample, but prefer a stable explicit fixture for long-term regression. Flaky tests are treated as determinism or isolation defects; they are not retried until green without retaining failed evidence.

Test reports record command/profile, software commit, dependency lock hash when present, seed, deterministic work budgets, selected threshold profile, passed/failed/skipped counts, and artifact locations. A skipped mandatory test makes the verification run incomplete.
