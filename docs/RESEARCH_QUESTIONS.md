# Research questions

## Triage rules

- **ENGINEERING DECISION:** A question is a blocker only for the named milestone. Unrelated future uncertainty does not block the canonical-IR milestone.
- **ENGINEERING DECISION:** An answer requires a proof, primary-source synthesis, controlled experiment, or explicit project decision with falsification criteria. Preference alone is not closure.
- **PROVEN / FORMAL:** No research result may weaken an exact canonical or fail-closed invariant.

Priority meanings:

- `P0`: blocks the named recommended next milestone; its scope is stated in the question/section.
- `P1`: blocks the first solver/forward-model/verification milestone.
- `P2`: blocks later topology, domain, or fidelity expansion.

## P0: canonical contracts and semantic validator

All P0 questions are answered. Their adopted decisions are normative for Milestone 0; later evidence may supersede them only through a new ADR/profile rather than an in-place weakening.

| ID | Status | Label | Adopted decision and closure evidence | Previously blocked |
| --- | --- | --- | --- | --- |
| `RQ-001` | `ANSWERED` | **ENGINEERING DECISION** | `CROCHET_CORE_1.0.0` executes six plain families, binary SC increase/decrease as derived shaping on typed stitch applications, and nine explicit construction/accounting operations. Positive-base stitches use `REPLACE_SPAN`; zero-base `CHAIN` uses explicit `INSERT_AT_GAP`. Non-SC/n-ary shaping fails closed. See [`DOMAIN_MODEL.md`](DOMAIN_MODEL.md), [`CROCHET_IR.md`](CROCHET_IR.md), and [ADR-0007](adr/0007-v1-executable-stitch-and-operation-semantics.md). | V2-V4 validator and initial fixtures |
| `RQ-002` | `ANSWERED` | **PROVEN / FORMAL** | Immutable ordered frontiers own explicit attachment-location IDs. Replay assigns every produced location to exactly one of active-live, reserved-live, retired, or declared-open-boundary, with explicit span/gap edits, disjoint split/reserve, and explicit join orientation. See [`TOPOLOGY_SEAMLESS.md`](TOPOLOGY_SEAMLESS.md), [`CROCHET_IR.md`](CROCHET_IR.md), and [ADR-0008](adr/0008-ordered-attachment-frontier-ledger.md). | V4 semantic validator |
| `RQ-003` | `ANSWERED` | **ENGINEERING DECISION** | `CROCHET_SEMANTIC_EQUIVALENCE_V1` projects construction semantics, labels entities from total execution/creation order, alpha-renames references, applies the collection registry, and compares JCS bytes. General graph isomorphism and partial-order equivalence are excluded from V1. See [`CROCHET_IR.md`](CROCHET_IR.md) and [ADR-0009](adr/0009-execution-normalized-semantic-equivalence.md). | V9 foundation and canonical validator APIs |
| `RQ-004` | `ANSWERED` | **ENGINEERING DECISION** | V0 uses project/geometry-specific profiles. Mesh profiles require exact component/boundary counts, orientable two-manifolds, no self-intersection/contact, explicit millimetre frames, declared numerical profiles, and no repair. See [`MESH_PREFLIGHT.md`](MESH_PREFLIGHT.md), [`DESIGN_SPEC.md`](DESIGN_SPEC.md), and [ADR-0010](adr/0010-domain-specific-v0-preflight-profiles.md). | DesignSpec semantics and V0 implementation |
| `RQ-005` | `ANSWERED` | **ENGINEERING DECISION** | Structured artifacts use their collection registry followed by RFC 8785 JCS over accepted I-JSON/binary64 values and domain-separated SHA-256. Inline MaterialProfiles recursively use the sole material canonical projection before parent DesignSpec hashing. Duplicate keys, unsafe integers, non-finite/overflow values, invalid Unicode, and locale syntax fail. Cross-runtime goldens are fixed. See [`CANONICALIZATION.md`](CANONICALIZATION.md) and [ADR-0011](adr/0011-jcs-ijson-domain-separated-hashes.md). | Stable DesignSpec/CrochetIR hashing |

## P0: V0 Mesh Preflight contracts

These questions are answered and unblock implementation of V0 Mesh Preflight. Bootstrap numerical thresholds remain explicitly uncalibrated, so a computational pass is at most `EXPERIMENTAL`; calibration is not a blocker for implementing the deterministic gate.

| ID | Status | Label | Adopted decision and closure evidence | Previously blocked |
| --- | --- | --- | --- | --- |
| `RQ-006` | `ANSWERED` | **PROVEN / FORMAL + ENGINEERING DECISION** | V0 consumes immutable `IndexedTriangleMeshV1`: finite binary64 coordinates in a declared right-handed millimetre frame, zero-based safe-integer indices, array-position identity, integer incidence, explicit adapter provenance, and no topology repair. Coordinate coincidence never merges identities. See [`GEOMETRY_MODEL.md`](GEOMETRY_MODEL.md) and [ADR-0012](adr/0012-canonical-indexed-triangle-mesh.md). | Canonical V0 parser/mesh boundary |
| `RQ-007` | `ANSWERED` | **ENGINEERING DECISION** | DesignSpec V1 resolves `v0_num_mesh_binary64_v1` to immutable version `1.0.0`. Exact topology has no tolerance; certified robust signs and scale-normalized threshold classifications fail closed. The characteristic scale is the certified mesh vertex diameter and thresholds have explicit inclusive/exclusive boundaries. See [`NUMERICAL_GEOMETRY.md`](NUMERICAL_GEOMETRY.md), [`../profiles/v0-mesh-numeric-profile-1.json`](../profiles/v0-mesh-numeric-profile-1.json), and [ADR-0013](adr/0013-versioned-v0-numerical-geometry.md). | Reproducible V0 numerical predicates |

## P1: first deterministic solver and verifier

| ID | Label | Question and decision needed | Closure evidence | Blocks |
| --- | --- | --- | --- | --- |
| `RQ-101` | **HYPOTHESIS** | Which global integer optimization state and transition cost produce reachable sphere/cylinder/cone/ellipsoid/hourglass courses without local rounding drift or stacked shaping? | Formal reachability constraints, deterministic DP budget, counterexamples to greedy rounding, and analytic golden proposals | Analytic solver V1 |
| `RQ-102` | **HYPOTHESIS** | What minimal F0 graph/spring energies and initialization predict useful geometry without reading target geometry? | Dimensioned energy specification, independent input API audit, convergence tests, sensitivity analysis, and tube/sphere comparison | V6 F0 |
| `RQ-103` | **HYPOTHESIS** | Are per-response `effective_gauge.effective_stitch_pitch_mm` and `effective_gauge.effective_course_pitch_mm` identifiable and repeatable enough for an initial same-crocheter MaterialProfile when canonical stitch type, course mode, tension profile, and fabric state are frozen? | At least three tube specimens per required calibration-response key, instrument uncertainty, residual analysis, and repeatability estimate under frozen conditions | Calibrated material profile |
| `RQ-104` | **HYPOTHESIS** | Which normalized Chamfer, robust Hausdorff percentile, silhouettes, sections, volume, landmarks, normals, and topology thresholds correspond to visibly/physically acceptable results? | Thresholds frozen before independent sphere/hourglass/Y-branch holdouts; full metric vector and false-pass/false-reject analysis | Overall `VERIFIED` state |
| `RQ-105` | **HYPOTHESIS** | Which bounded material scenarios are sufficient for V8 without implying statistical confidence unsupported by the sample design? | Parameter bounds with provenance, deterministic scenario design, sensitivity/coverage study, and adversarial missed-corner analysis | Material robustness gate |
| `RQ-106` | **ENGINEERING DECISION** | Which collision/contact conditions are exact V6 failures at F0, and which require a thickness/tolerance model? | Unit-bearing collision policy, independent synthetic cases, convergence-resolution study, and owner/calibration path | V6 collision evidence |
| `RQ-107` | **PROVEN / FORMAL** | Under which enabled stitch semantics is a course-count transition provably reachable or unreachable? | Necessary/sufficient integer conditions or exhaustive bounded state proof, with `E_GEOMETRY_UNREACHABLE` distinct from budget exhaustion | V5 candidate verifier |
| `RQ-108` | **ENGINEERING DECISION** | What parser-visible anchors make human exports unambiguous without requiring textual identity across German, US English, and UK English? | Grammar subset, ambiguity rejection corpus, semantic round-trip properties, and accessible human examples | V9 exporter/parser |
| `RQ-109` | **HYPOTHESIS** | Are the bootstrap V0 normalized area, coincidence, contact, volume, and landmark bands conservative enough across supported mesh sources without excessive false rejection? | Frozen adversarial corpus, scale/retessellation sweep, certified-margin distributions, and reviewed successor-profile proposal | Calibrated V0 profile and claims above `EXPERIMENTAL`; not V0 implementation |

## P2: topology and domain expansion

| ID | Label | Question and decision needed | Closure evidence | Blocks |
| --- | --- | --- | --- | --- |
| `RQ-201` | **HYPOTHESIS** | Which geodesic discretization and boundary conditions remain stable under low-quality meshes and retessellation? | Primary-source comparison, convergence study, retessellation metamorphic suite, and failure policy | Geodesic solver |
| `RQ-202` | **HYPOTHESIS** | How reliably do level-set critical points and Reeb-style summaries propose construction branches without conflating target topology with feasible crochet topology? | Synthetic topology suite, perturbation stability analysis, and independent Construction Graph feasibility checks | Seamless Topology Engine |
| `RQ-203` | **HYPOTHESIS** | Which bounded advancing-front state, heuristic, collision guard, and rollback policy provide useful coverage with reproducible budget exhaustion? | State invariants, deterministic beam/backtracking budget, adversarial stalls, and explicit no-solution results | Frontier solver |
| `RQ-204` | **FUTURE** | Which fixtures can separately identify stretch, stuffing expansion, compression, friction, bending, and drape without severe confounding? | Sensitivity/Fisher-information style analysis and pre-registered physical experiments | F1/F2 material models |
| `RQ-205` | **FUTURE** | Which garment constructions, ease models, and cloth measurements belong in the first garment solver without borrowing amigurumi assumptions? | Garment-specific DesignSpec contract, graded fixtures, and cloth validation plan | Garment solver |
| `RQ-206` | **FUTURE** | What exact combinatorial guarantees are possible for rows, grids, repeats, motifs, colour regions, C2C, tapestry, mosaic, and filet? | Separate flat-domain IR mapping and exhaustive finite fixtures | Flat-crochet solver |
| `RQ-207` | **FUTURE** | Which typed semantics are needed for chain spaces, picots, post stitches, clusters, puffs, bobbles, fans/shells, and motif attachment points? | Domain-reviewed semantic library and round-trip/stateful tests | Lace solver |

## Ongoing licensing questions

| ID | Label | Question | Current disposition |
| --- | --- | --- | --- |
| `RQ-LIC-01` | **ENGINEERING DECISION** | Does the exact GeoStitch revision expose a compatible license for any desired asset or code? | Unresolved. No reuse. Concepts must be derived from primary geodesic literature. |
| `RQ-LIC-02` | **ENGINEERING DECISION** | Is there a compatible explicit license for the research code associated with the surfaces-of-revolution paper? | Unresolved. No code reuse; independently derive published mathematics. |
| `RQ-LIC-03` | **ENGINEERING DECISION** | Are any Digital Crochet implementation artifacts needed, and what exact licenses cover them? | Unresolved and not needed for milestone 1. No reuse. |
| `RQ-LIC-04` | **FUTURE** | Should any GPL or non-commercial crochet project ever be integrated rather than used only as conceptual prior art? | Requires an explicit product/distribution licensing decision. Current answer is no integration. |

## Question record template

When work begins, add or link a research record containing:

```yaml
question_id: RQ-101
status: OPEN               # OPEN | IN_PROGRESS | ANSWERED | DEFERRED
owner: subsystem-or-role
milestone: analytic-solver-v1
claim_label: HYPOTHESIS
decision_required: concise statement
primary_sources: []
license_checks: []
method: proof, experiment, or source synthesis
falsification_criteria: []
artifacts_and_hashes: []
result: null
limitations: []
affected_contracts: []
reviewer: null
```

An `ANSWERED` question records the adopted decision and why competing approaches were rejected. New evidence creates a superseding record rather than deleting prior uncertainty.
