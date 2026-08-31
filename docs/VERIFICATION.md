# Verification contract

## Purpose and trust boundaries

- **PROVEN / FORMAL:** Exact structural validity is necessary for a verified pattern and cannot be inferred from geometric similarity.
- **ENGINEERING DECISION:** Verification is an ordered V0-V10 gate pipeline. Each gate emits structured evidence defined in [`FAILURE_POLICY.md`](FAILURE_POLICY.md).
- **ENGINEERING DECISION:** Generation, semantic validation, forward simulation, target comparison, and export round-trip validation are separate responsibilities and should use independent implementations where practical.
- **HYPOTHESIS:** Numerical geometry and robustness thresholds become evidence-backed only after the physical calibration program in [`PHYSICAL_VALIDATION.md`](PHYSICAL_VALIDATION.md).

The candidate generator may read target geometry. The independent forward simulator MUST NOT. Only the V7 comparator receives both target geometry and predicted geometry.

```text
DesignSpec + target + MaterialProfile
                |                         generation trust domain
                v
          solver candidate -> CrochetIR + solver trace
                                  |
              independent semantic validation (V2-V5)
                                  |
CrochetIR + MaterialProfile + simulator config
                                  |
              independent forward model (V6)
                                  |
                     predicted geometry ---------+
                                                  |
target geometry --------------------------------> comparator (V7)
```

## Evidence model

Every gate evidence record contains:

- `gate_id` and gate implementation version;
- `outcome`: `PASS`, `WARNING`, `FAIL`, `INDETERMINATE`, or `NOT_RUN`;
- content hashes of every input actually read;
- verification and threshold profile identifiers;
- deterministic parameters, work budget, and seed where applicable;
- exact assertions checked and their result counts;
- metric vector with units and per-metric thresholds where applicable;
- structured diagnostics;
- hashes of produced artifacts;
- runtime telemetry separated from canonical evidence.

Wall-clock duration, machine name, and timestamp may be recorded as telemetry but MUST NOT affect a canonical result hash. Evidence is append-only. Re-running a gate creates a new record rather than editing the old one.

## Gate sequence

| Gate | Input and responsibility | Required success condition | Representative critical failure |
| --- | --- | --- | --- |
| V0 Input/geometry preflight | Raw geometry and external assets | The canonical representation in [`GEOMETRY_MODEL.md`](GEOMETRY_MODEL.md), exact domain profile in [`MESH_PREFLIGHT.md`](MESH_PREFLIGHT.md), and resolved numerical policy in [`NUMERICAL_GEOMETRY.md`](NUMERICAL_GEOMETRY.md) pass; normalization is lossless, deterministic, separately hashed, and fully recorded | `E_INPUT`, `E_UNSUPPORTED_FEATURE` |
| V1 DesignSpec | DesignSpec plus referenced asset hashes | Schema and semantic constraints pass; dimensions, coordinate frame, requested topology, construction limits, material reference, and verification profile are explicit | `E_SCHEMA`, `E_REFERENCE` |
| V2 CrochetIR structure | Candidate CrochetIR only | Schema version supported; IDs unique; references typed; canonicalization deterministic; all operations and stitch semantics supported | `E_SCHEMA`, `E_REFERENCE`, `E_DETERMINISM` |
| V3 Stitch/reference accounting | CrochetIR plus canonical stitch library | Independently recomputed base/top arity, course membership, attachment multiplicity, yarn continuity, colors, and counts exactly match | `E_REFERENCE`, `E_COUNT` |
| V4 Frontier/topology | CrochetIR plus DesignSpec topology requirements | Every frontier transition is legal and total; branches resolve; only declared openings remain; components, orientation, split/join, cuts, and reattachments satisfy policy | `E_FRONTIER`, `E_TOPOLOGY` |
| V5 Candidate/solver claims | V2-V4-passing IR, DesignSpec, solver trace | Claimed invariants, reachability constraints, budgets, deterministic tie breaks, and seam/cut/reattachment counts are independently confirmed | `E_GEOMETRY_UNREACHABLE`, `E_SEARCH_BUDGET`, `E_DETERMINISM` |
| V6 Independent forward simulation | Target-free physical-semantic projection, MaterialProfile, declared loads/boundaries, SimulatorConfig | Simulator returns `CONVERGED`; predicted geometry is finite and has no forbidden unresolved collision | `E_FORWARD_DIVERGED`, `E_COLLISION` |
| V7 Geometry comparison | Predicted geometry and target geometry | Every hard member of the metric vector passes its own threshold after only the declared alignment | `E_SHAPE_THRESHOLD`, `E_TOPOLOGY` |
| V8 Material/gauge robustness | V6 model plus bounded MaterialProfile uncertainty set | All required scenarios complete; every critical structural/contact condition and profile-required geometry condition passes | `E_MATERIAL_UNCERTAINTY`, `E_COLLISION`, `E_SHAPE_THRESHOLD` |
| V9 Human export round trip | CrochetIR, locale exporter, independent parser | Each required locale parses to a semantically equivalent canonical construction | `E_EXPORT_ROUNDTRIP`, `E_DETERMINISM` |
| V10 Provenance/physical status | Complete V0-V9 evidence and physical records if claimed | Required hashes and versions form a closed chain; physical status is supported by linked records and the profile's evidence requirement | `E_PROVENANCE`, `E_PHYSICAL_VALIDATION` |

Gates run in order. After a mandatory failure, later gates default to `NOT_RUN`. They may run in a diagnostic-only mode, but their results cannot change the overall rejected state.

V0 additionally records the immutable source hash, `IndexedTriangleMeshV1` representation version, parser adapter/version, source-to-canonical index maps, domain-profile ID, numerical-profile ID/version/record hash, characteristic scale, threshold/operator set, robust-predicate backend/version, and every normalization event. An uncertified required predicate, unresolved profile, or threshold interval straddling a decision boundary yields `INDETERMINATE`; it never becomes a guessed `PASS` or repair.

## Exact semantic checks

V2-V4 MUST use exact logic rather than tolerances wherever the representation is discrete.

### Identity and canonicalization

- Every explicit ID is unique in its declared namespace.
- Every reference exists and targets the required entity kind.
- The `design_spec_ref` ID and SHA-256 digest match the validated DesignSpec.
- Canonical serialization follows [`CANONICALIZATION.md`](CANONICALIZATION.md): duplicate-free I-JSON, finite binary64 values, safe integers, artifact-specific collection ordering, RFC 8785 JCS UTF-8, profile-domain separation, and SHA-256.
- Repeated canonicalization is idempotent and byte-identical.

### Stitch, course, and yarn accounting

- Each stitch's declared `base_arity`, `top_arity`, and derived shaping classification equal `CROCHET_CORE_1.0.0`; V1 accepts plain six-family stitches and only binary SC shaping.
- Every stitch has exactly one yarn-independent frontier edit paired with its `ADVANCE`: positive-base stitches use a valid consecutive `REPLACE_SPAN`; zero-base `CHAIN` uses a legal explicit `INSERT_AT_GAP`; target frontiers, neighbors, retired bases, and created tops agree exactly.
- Resulting top attachment locations are neither missing nor duplicated.
- Each stitch belongs to exactly one ordered course or round; course order and cyclic/linear mode agree with traversal.
- Yarn-path events form continuous ordered paths. Changes of active yarn require explicit cut, attach, reattach, or color-change semantics as appropriate.
- Declared per-course and total counts equal independent recomputation; derived counts are not trusted inputs.

### Frontier and topology accounting

- Frontier creation, advancement, split, reservation, reattachment, join, closure, and opening declaration replay through the exact attachment-location ledger. Every produced location is exclusively active-live, reserved-live, retired, or declared-open-boundary.
- Every reserved frontier is later consumed, deliberately retained as an opening, or explicitly closed.
- Every branch reaches a terminal accounted state; split and join arities and orientation are compatible.
- Every remaining boundary corresponds one-to-one with a declared intentional opening.
- Requested connected-component, boundary-component, and branch relationships match the DesignSpec. Every target boundary has a unique `REMAIN_OPEN` opening match. Where a closed orientable surface is required, the selected topology profile also checks Euler characteristic and/or Betti numbers with an implementation-independent algorithm.

## V5 candidate verification and selection

V5 verifies a candidate; it does not trust the solver's success flag. Solver traces MUST record solver name/version, input hashes, parameters, invariant set, deterministic budget, explored-state count, seed if any, and terminal reason.

Solver `SEARCH_BUDGET_EXHAUSTED` maps to `E_SEARCH_BUDGET`, not a fabricated pattern and not a proof of impossibility. `E_GEOMETRY_UNREACHABLE` requires either an exact reachability argument or exhaustive search over the explicitly bounded supported state space. The orchestration outcome `NO_VERIFIED_SOLUTION_WITHIN_BUDGET` retains the complete cause set: generation exhaustion maps to `E_SEARCH_BUDGET`, while emitted candidates rejected by later gates retain those gates' actual failures.

Candidate selection is lexicographic after V0-V8 feasibility:

1. reject every structurally invalid candidate;
2. reject every candidate outside any hard geometry or robustness threshold;
3. minimize sewn seams;
4. minimize yarn cuts and reattachments using the profile's declared tuple order;
5. compare remaining geometry metrics using the profile's explicit partial order;
6. minimize declared construction-complexity measures;
7. apply a deterministic canonical-hash tie break.

A seamless candidate outside the geometry acceptance region is ineligible.

## V6 independent forward model

The V6 simulator accepts only the target-free `FORWARD_PHYSICAL_SEMANTICS_V1` projection described in [`FORWARD_MODEL.md`](FORWARD_MODEL.md), plus:

- MaterialProfile;
- independently declared loading and boundary conditions;
- SimulatorConfig, including numerical budget and deterministic seed if needed.

It MUST reject target meshes, target landmarks, target distance fields, solver embeddings, closest-point projections to the target, and solver repair hints. The orchestrator enforces this by type/interface separation and records the exact V6 input hash set.

The allowed forward outcomes are `CONVERGED`, `INVALID_MODEL_INPUT`, `DIVERGED`, `UNRESOLVED_COLLISION`, `BUDGET_EXHAUSTED`, and `NUMERICAL_FAILURE`. Only `CONVERGED` may carry predicted geometry and pass V6. Numerical tolerances have units, rationale, owner/calibration path, and version. Convergence at a coarse tolerance is not evidence that a finer threshold would pass.

Shared libraries between solver and simulator require a documented common-mode review. Solver-specific target fitting and target-constrained initial states are forbidden even when convenient.

## V7 geometry metric stack

### Sampling and alignment

The V7 comparison profile defines its own positive characteristic target length `L` in millimetres, normally the target bounding-box diagonal. This is not the V0 numerical-profile scale, which is the certified mesh vertex diameter. Surface samples are deterministic, area-weighted, and recorded by algorithm version, density, and seed. Degenerate targets fail V0.

The DesignSpec coordinate frame is authoritative. A profile may permit a deterministic rigid registration to remove placement only; scale fitting or non-rigid registration is forbidden for absolute-size claims. The applied transform is evidence.

### Required metric vector

| Metric | Definition and normalization | Gate use |
| --- | --- | --- |
| Symmetric Chamfer | Mean nearest-surface distance in both directions, averaged symmetrically and divided by `L` | Global average fidelity |
| Robust Hausdorff | Maximum of the declared bidirectional distance percentile, for example P95 or P99, divided by `L`; percentile is profile data | Local worst-region fidelity without one-sample domination |
| Multi-view silhouette IoU | IoU for each canonical view and the declared minimum/mean summary; cameras and raster resolution are fixed | Perceptual outline fidelity |
| Cross-section error | Per-section radial or contour distance and area difference at DesignSpec-defined planes, normalized by local section size or `L` | Thin necks, tapers, limbs, and waist fidelity |
| Volume error | Absolute predicted-minus-target volume divided by target volume, when both surfaces are closed and oriented | Global inflation/deflation |
| Landmark deviation | Euclidean distance for each named landmark divided by `L`; no averaging may hide a hard landmark failure | Recognizable feature placement |
| Surface-normal error | Deterministic correspondence-based angular distribution in degrees | Orientation and faceting diagnostic or gate |
| Curvature diagnostics | Versioned, scale-aware comparison of selected curvature summaries | Diagnostic until calibrated |
| Topology | Exact component, boundary, genus/Betti, and declared branch/opening checks | Hard gate, never averaged with geometry |

**ENGINEERING DECISION:** The full metric vector is reported. Each hard metric has its own operator and threshold. A weighted scalar may be shown for exploration only and cannot determine pass/fail.

**HYPOTHESIS:** Initial numerical thresholds and landmark weights are engineering hypotheses. They are versioned and frozen before a benchmark run, then calibrated using physical specimens rather than tuned to make a candidate pass.

## V8 material robustness

Robustness operates over explicitly bounded uncertainty in effective stitch pitch, effective course pitch, and only those additional parameters supported by identifiable calibration. It does not turn yarn category and hook diameter into false certainty.

The profile declares either an exhaustive finite scenario set or a deterministic bounded sampling design, with seed, sample count, parameter bounds, and work budget. Sampled coverage is reported as empirical coverage, not as an opaque confidence percentage.

- `PASS`: every required scenario completed and passed all critical conditions and required metric thresholds.
- `WARNING`: permitted only when every critical structural/contact condition passes but a named advisory margin is narrow; it prevents overall `VERIFIED`.
- `FAIL`: any required scenario violates a hard condition.
- `INDETERMINATE`: bounds or required coverage are missing, or the robustness budget ends early.

Worst case, declared percentiles, and the full failure set are retained. A nominal V7 pass cannot override a V8 fail.

## V9 semantic export round trip

For each required locale, including German, US English, and UK English when enabled:

1. export canonical CrochetIR to human instructions;
2. parse with an independently maintained parser;
3. validate both IRs under the same executable semantics profile;
4. construct `CROCHET_SEMANTIC_EQUIVALENCE_V1` projections using execution/creation-order alpha-renaming;
5. compare their JCS bytes exactly under [`CANONICALIZATION.md`](CANONICALIZATION.md).

The projection preserves construction order, family/shaping/arity/incidence, operations, frontier ledger, yarn/color/material bindings, branches/components, joins, and openings. It excludes solver derivations and provenance that V10 retains separately. Localized spelling, abbreviations, whitespace, table order, display labels, and regenerated IDs are not equality oracles. Ambiguous text is an `E_EXPORT_ROUNDTRIP` failure; the parser MUST NOT guess. Exported instructions may carry explicit machine-readable anchors where needed for an unambiguous round trip.

Reordered independent components, changed join orientation, a cyclic rotation inconsistent with its anchor, or two plain stitches substituted for one shaping node fail V1 equivalence. General graph-isomorphism and partial-order search are not V9 fallbacks.

## V10 provenance and physical evidence

Every verified output records at least:

- DesignSpec, MaterialProfile, input geometry, and CrochetIR hashes;
- solver name/version, parameters, terminal reason, and seed;
- forward-model and metric implementation versions;
- verification and threshold profile identifiers;
- exporter/parser versions and required locales;
- software commit and evidence-bundle hash;
- physical-record IDs and content hashes when physical claims are made.

Physical status is separately reported as `UNTESTED`, `CALIBRATED`, or `PHYSICALLY_VERIFIED`, following [`PHYSICAL_VALIDATION.md`](PHYSICAL_VALIDATION.md). A failed physical trial is expressed as V10 `FAIL` with `E_PHYSICAL_VALIDATION`; the positive status field is not abused as a failure code.

## User-facing evidence summary

The user output exposes categories, not a confidence percentage:

| Display category | Required content |
| --- | --- |
| Structural Integrity | `PASS` or `FAIL` from exact V2-V3 evidence |
| Topology | `PASS` or `FAIL` from V4 and topology members of V7 |
| Geometry | Metric vector plus `PASS` or `FAIL`; no hidden scalar confidence |
| Material Robustness | `PASS`, `WARNING`, or `FAIL` from V8 |
| Construction | Sewn seams, yarn cuts, reattachments, and declared complexity values |
| Physical Validation | `UNTESTED`, `CALIBRATED`, or `PHYSICALLY_VERIFIED` plus linked V10 evidence |

```yaml
overall_state: EXPERIMENTAL
verification_profile_id: amigurumi-f0-research-v1
structural_integrity: PASS
topology: PASS
geometry:
  outcome: PASS
  metrics: {chamfer_normalized: ..., robust_hausdorff_p95_normalized: ...}
material_robustness: WARNING
construction: {sewn_seams: 0, yarn_cuts: 1, reattachments: 1}
physical_validation: UNTESTED
evidence_bundle_hash: sha256:...
```

All omitted required evidence is visible as `NOT_RUN` or `INDETERMINATE`; absence is never rendered as success.
