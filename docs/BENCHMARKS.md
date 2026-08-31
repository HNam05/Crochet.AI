# Benchmark and golden-fixture contract

## Purpose

- **ENGINEERING DECISION:** Benchmarks exercise distinct failure modes and evidence gates; they do not collapse quality into one leaderboard score.
- **PROVEN / FORMAL:** Invalid fixtures with exact expected rejection are as important as valid fixtures.
- **HYPOTHESIS:** Geometry envelopes are provisional until physical calibration supports a versioned threshold profile.

This document specifies fixture intent and governance. Actual mesh, DesignSpec, MaterialProfile, CrochetIR, and evidence artifacts live under `tests/fixtures/`, `tests/golden/`, and `tests/physical/`.

## Fixture manifest

Every fixture directory contains a machine-readable manifest with:

- stable `fixture_id`, title, domain, version, and lifecycle status;
- classification: `valid`, `invalid`, `metamorphic_family`, or `physical`;
- exact parametric generation recipe or immutable source-asset hash;
- millimetre coordinate system, orientation convention, and characteristic-length rule;
- DesignSpec, MaterialProfile, target geometry, and optional approved CrochetIR hashes;
- permitted solver families and required feature milestone;
- expected gate outcome for V0-V10, including the exact primary error for a negative fixture;
- exact structural/topological invariants;
- metric implementation and threshold-profile IDs, with per-metric envelopes;
- deterministic parameters, budgets, and seeds;
- provenance and human approval record for golden expectations.

Generated fixtures are preferred when a compact exact recipe exists. Their generator version and output hash are both pinned. External meshes require origin and license review before inclusion.

## Required computational fixtures

| ID | Fixture | Contract focus | Expected result when its milestone is enabled |
| --- | --- | --- | --- |
| `GEO-SPHERE-01` | Sphere | Closed genus-0 surface, rotational symmetry, smooth increase/decrease schedule, analytic-vs-geodesic redundancy | V0-V9 pass; topology exact; all canonical views and cross-sections inside frozen envelope |
| `GEO-CYLINDER-01` | Cylinder | Constant circumference, separate stitch/course pitch, opening/cap declaration, translation/rotation/scale relations | No unintended count drift; declared boundaries only; dimensionless metrics covariant |
| `GEO-CONE-01` | Cone or truncated cone | Monotone circumference transitions, apex handling, course reachability | Reachable transitions and non-stacked shaping policy pass; apex/open end exactly accounted |
| `GEO-ELLIPSOID-01` | Ellipsoid | Anisotropic global shape, silhouettes and cross-sections beyond average distance | V0-V9 pass; principal-axis landmarks and section errors each pass |
| `GEO-HOURGLASS-01` | Hourglass | Consecutive decreases/increases, narrow waist, local curvature and anti-stacking | V0-V9 pass with waist sections and robust Hausdorff independently gated |
| `NEG-THIN-NECK-01` | Thin-neck invalid case | Feature below the supported material/operation reachability bound under fixed seamless constraints | V5 `FAIL`, primary `E_GEOMETRY_UNREACHABLE`; proof preconditions and limiting course recorded |
| `TOP-TWO-LOBE-01` | Two-lobe shape | Geodesic critical point, level-set topology change, branch decomposition | Topology engine accounts for split/merge; otherwise milestone-specific `E_UNSUPPORTED_FEATURE`, never a guessed single frontier |
| `TOP-Y-BRANCH-01` | Y-branch | One trunk to two branches, frontier split/reservation/reattachment, branch terminal accounting | V4 passes with zero unaccounted branches and only declared openings; seam/cut tuple exact |
| `TOP-TWO-LEG-01` | Two-leg split | Body frontier split into two ordered legs, reserved frontier resumed later | V4 passes; each child frontier has one owner and terminal state; yarn events exact |
| `TOP-TORUS-01` | Torus/handle | Genus-1 target, merge/join strategy, unavoidable construction decision | Exact target topology and construction join pass when supported; earlier milestones expect explicit `E_UNSUPPORTED_FEATURE` |
| `NEG-NONMANIFOLD-01` | Non-manifold mesh | Edge with invalid face incidence and/or non-manifold vertex fan | V0 `FAIL`, primary `E_INPUT`; no automatic repair |
| `NEG-SELF-INTERSECT-01` | Self-intersecting mesh | Geometrically intersecting triangles without a declared valid contact interpretation | V0 `FAIL`, primary `E_INPUT`, offending primitive IDs reported |
| `NEG-COURSE-JUMP-01` | Unreachable course transition | Symbolic count transition outside the enabled stitch library's arity/reachability constraints | V5 `FAIL`, primary `E_GEOMETRY_UNREACHABLE`, not `E_SEARCH_BUDGET` |
| `SEM-COLOR-01` | Color transition | Active yarn, explicit `COLOR_CHANGE`, yarn path, course ordering, localized export | V2-V4 and V9 pass; color/yarn semantics survive every required locale round trip |
| `SEM-ROUNDTRIP-01` | Human-pattern round trip | Canonical IR to German, US English, and UK English and back | V9 pass by `CROCHET_SEMANTIC_EQUIVALENCE_V1`; text and raw-ID equality are not required |

`TOP-TORUS-01` and `TOP-TWO-LOBE-01` have milestone-dependent approved outcomes. Changing an expected `E_UNSUPPORTED_FEATURE` to a verified construction is a feature transition and requires a new fixture version plus human-approved golden, not an in-place rewrite.

## Exact fixture construction requirements

### Analytic shapes

Sphere, cylinder, cone, ellipsoid, and hourglass targets MUST be generated from explicit equations and dimensions in millimetres. The manifest records domain bounds, closure/cap rules, meshing parameters, orientation, and exact landmark/cross-section definitions. Decimal dimensions are stored canonically; informal labels such as “unit sphere” are insufficient.

Each analytic shape has at least:

- a reference tessellation;
- a consistently reversed-winding variant;
- two topology-equivalent retessellations with materially different triangle layout;
- translated, rigidly rotated, uniformly scaled, and mirrored variants where permitted.

These variants support metamorphic tests without assuming byte-identical CrochetIR.

### Invalid geometry

Negative meshes are constructed by a small deterministic edit to a valid base mesh. The manifest identifies the edited vertices/faces and the intended unique defect. V0 diagnostics must point to that defect. If a fixture accidentally contains another earlier-priority defect, it is corrected rather than relaxing the expected code.

### Construction semantics

Y-branch, two-leg, color, and round-trip fixtures include a small human-auditable reference transition trace independent of production code. It enumerates frontier ownership, branch tokens, active yarn, explicit cuts/attachments, intentional openings, and exact terminal states.

## Benchmark result vector

A run reports, without hiding individual failures:

1. V0-V10 outcome vector and diagnostics;
2. exact structural counts and topology invariants;
3. V7 metric vector: symmetric Chamfer, robust Hausdorff percentile, every canonical-view silhouette IoU, cross-section errors, volume error where defined, landmark deviations, normal error, curvature diagnostics, and topology;
4. V8 worst-case/scenario metrics and incomplete scenarios;
5. construction tuple: sewn seams, yarn cuts, reattachments, then declared complexity measures;
6. deterministic work counts such as states expanded, iterations, linear solves, and peak resident memory where available;
7. canonical hashes and full implementation/profile provenance.

Wall-clock time is diagnostic and includes machine metadata. Deterministic work counts are the primary regression signal. A performance regression limit may be added only with a versioned workload and rationale; performance never overrides correctness.

## Solver redundancy benchmark

When two diverse solvers support a fixture, each produces its own CrochetIR. Both run through the same independently governed semantic verifier but separate V6 simulations. Comparison uses invariant vectors, predicted geometry, robustness, and construction tuple. Different stitch counts are permitted. Majority voting and “closest counts” are not acceptance rules.

A benchmark report states shared libraries and likely common-mode risks. An algorithm port or three parameterizations of the same method do not count as independent solver diversity.

## Physical benchmark mapping

| Physical ID | Computational precursor | Primary purpose |
| --- | --- | --- |
| `PHY-TUBE-01` | `GEO-CYLINDER-01` | Estimate separate effective stitch and course pitch under recorded conditions |
| `PHY-SPHERE-01` | `GEO-SPHERE-01` | Validate closed-round shaping and stuffing response |
| `PHY-HOURGLASS-01` | `GEO-HOURGLASS-01` | Validate local count transitions and waist cross-sections |
| `PHY-Y-BRANCH-01` | `TOP-Y-BRANCH-01` | Validate branching construction, openings, seams/cuts, and branch geometry |

Physical data follows [`PHYSICAL_VALIDATION.md`](PHYSICAL_VALIDATION.md). Calibration specimens and holdout validation specimens are distinct records.

## Golden approval and immutability

An expected artifact becomes golden only after a human reviewer approves:

- the fixture recipe and licenses;
- structural and topology expectations;
- semantic diff from any predecessor;
- numerical profile and rationale;
- provenance completeness;
- whether the expected outcome is success or explicit rejection.

Approval is recorded in a sidecar manifest with reviewer, UTC date, rationale, issue/change reference, and approved hashes. Tests never update goldens. Proposed outputs go to a separate review directory and MUST NOT be copied into `tests/golden/` by CI, a solver, or an automated snapshot command.

## Initial acceptance status

**ENGINEERING DECISION:** During bootstrap, this document defines the suite but does not claim approved numerical outputs or physical thresholds. Until fixtures and profiles receive explicit approval, their status is `PLANNED`, their metrics are research data, and successful runs are at most `EXPERIMENTAL`.
