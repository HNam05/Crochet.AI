# Backend implementation and acceptance

Status: IN PROGRESS. This plan does not certify generated patterns.

## Acceptance rule

Each promised capability needs an executable implementation, independent tests,
documented limits, and a stable versioned interface. Rejecting an unsupported
domain is safe behavior, not completion of that domain. Real calibration and
holdout measurements are required for physical claims. Canonical contracts and
approved goldens remain frozen. Frontend work is out of scope.

## Packages in delivery order

| ID | Deliverable | Required acceptance evidence | Current state |
| --- | --- | --- | --- |
| B0 | Canonical runtime and semantic validator | Python and independent Node conformance | Implemented 1.0 and additive 1.1; recheck at release |
| B1 | Visible parser, binder, exporter, detached certification | Independent fixtures; order, anchors, colors, malformed text, semantic round trips, strict typing | M1A subset implemented; M1B and V9/V10 remain |
| B2 | Input/material resolution and geometry adapters | Immutable references, units, semantic negatives, robust predicates and boundary tests | Partial input/material validation, meridional samplers, indexed-mesh decode/topology/exact-geometry/diameter diagnostics, hash-locked profile, exact relative area/coordinate-distance and algebraic six-volume, bounded exact face-pair intersections and nonadjacent near-contact plus non-certifying vertex/face ordering diagnostics; adjacent residual contact, boundary matching and V0 certification missing |
| B3 | Analytic solver and independent candidate checks | Reachability proof, bounded global count search, reproducible traces, adversarial fixtures | Narrow closed-pole SC proposal implemented; full V5 and domains remain |
| B4 | Target-independent F0 simulation | Dimensioned energies, target-leakage tests, convergence and collision evidence | Target-free stretch-only prototype, initial surface/intersection/distance diagnostics; shear, bend, contact response, calibrated convergence and V6 missing |
| B5 | Geometry, robustness and V0-V10 orchestration | Independent synthetic metrics, bounded scenarios, fail-closed outcomes, provenance | Initial open-surface arithmetic, exact intersection and squared-distance diagnostics only; robust V0-V10 gates missing |
| B6 | Versioned API and CLI | Contract tests, structured errors, deterministic artifact retrieval | Local transport-independent API/CLI subset implemented; release contract open |
| B7 | Durable jobs and artifacts | Atomicity, idempotency, cancellation, resource limits, concurrency and recovery tests | Local SQLite jobs subset implemented; operational gates open |
| B8 | Security, packaging and operation | Untrusted input limits, path safety, isolation, diagnostics, install and end-to-end tests | Request limits and wheel subset implemented; service hardening open |
| B9 | Free-form, geodesic, topology and frontier solvers | Separate applicability contracts, branch/join fixtures, budgets, independent reconstruction | Missing; research required |
| B10 | Garment, flat and lace solvers | Separate domain contracts, semantics, fixtures and acceptance | Missing; research required |
| B11 | Empirical material and acceptance profiles | Real calibration samples, frozen thresholds, separate holdouts, human review | External physical evidence needed |
| B12 | Backend release | Every promised package accepted; compatibility and operational evidence documented | Not ready |

## First checkpoint (historical)

Preserve the uncommitted sibling M1 worktree. Reconcile and validate its grammar,
parser, binder and exporter before integrating into the main workspace. Check
instruction order, cyclic anchor identity, attachments, color boundaries,
terminal state, unsupported exports and malformed text. Keep CrochetIR,
PatternParseContext and CertificationManifest contracts intact. Do not change
the independent semantic validator to accommodate binder/exporter defects.
Run focused regressions, full tests, Ruff, mypy and Node conformance.

## Implementation checkpoint: 2026-09-22

- Main workspace contains the reconciled M1A text implementation; the sibling
  uncommitted worktree remains untouched. Parsing, binding, yarn segments, live
  anchors, explicit span export, strict grammar limits and round trips have tests.
- User approval allowed only an additive core 1.1 multi-site ring extension.
  Its separate schema, verifier rule, hand-built fixtures and text tests are in
  place. Core 1.0 schema and existing goldens are unchanged.
- B3 has an exact two-pass count-search kernel with exhaustive tiny-domain
  oracle tests and a separate mathematical review. It is not a complete solver:
  profile decoding, course placement, angular history, compilation and physical
  verification are still absent. See `ANALYTIC_COUNT_SEARCH.md`.
- B1 still needs advanced M1B operations and production provenance handling;
  detached text hashes do not establish full V10 acceptance.
- Later-course increase/decrease and wraparound explicit-span round trips now
  have executable coverage. Schema-valid split-ring course mutations are rejected.
- Next executable step: implement analytic target/course hypotheses and balanced shaping
  placement under explicit budgets before adding a direct CrochetIR compiler.
- B2 and B4-B12 remain open as listed above. No physical tests, new golden
  approvals, commits, pushes or deployment are claimed.

Checkpoint validation: `python -B -m pytest -q` passed 167 tests; Ruff and strict
mypy (12 source files) passed; the independent Node reference passed all five
unchanged conformance vectors; `git diff --check` passed. These results establish
software checks for the implemented subset, not full backend or physical acceptance.

## Current handoff: 2026-09-28

The 2026-09-22 checkpoint above is historical, not the current implementation
state. The primary checkout now has a narrow end-to-end analytic proposal path,
versioned local API/CLI, bounded JSON admission, local durable jobs, wheel
packaging, and a target-free physical-semantic projection. See
`BACKEND_RUNTIME.md` for exact admitted behavior and limitations. The separate
uncommitted `Crochet.AI-milestone-1` checkout remains untouched.

The target-free physical projection now lowers to a topology-only graph with
exact MaterialProfile response-key matching. It handles basic shaping incidence,
the admitted ring creation and frontier closure, including exact attachment
sets and event/transition identity, without assigning coordinates or
interpreting graph incidence as a spring. Other operation and branch/opening
semantics remain outside the projection's admitted scope. A separate strict
`F0_STRETCH_PROTOTYPE` input admission now requires explicitly unloaded loading,
provenance-bound hypothetical course/wale coefficients, budgets and tolerances;
it does not establish complete F0 calibration or V6. Experimental stretch terms
now cover course edges and only plain top-to-top wale incidence; ring-start wales
and shaping remain unresolved rather than receiving invented rest lengths. A
synthetic-only energy helper tests the units/formula, not a simulation result.
An experimental target-independent initializer now places supported plain
cyclic courses with exact input-dependent chord/axial spacing and an explicit
vertex budget; its coordinates are not a physical prediction. A separate
diagnostic computes stretch energy and forces with finite/undefined-case
rejection but cannot mark V6 converged. Bounded Armijo stretch steps now feed
a deterministic multi-step driver with global iteration/evaluation limits,
per-step trial limits and the exact initialization hash in its evidence. Only
experimental stretch-force balance is reported, never V6 convergence. Next:
the target-free open quad strip and its deterministic triangulation now cover
only exact plain 1:1 adjacent cyclic courses with explicit lower/upper
boundaries and combinatorial manifold checks; they do not invent ring/closure
caps or establish geometric embedding/contact. A target-free initial-coordinate
triangle diagnostic reports represented area and shape quality, with exact-zero
and arithmetic-indeterminate rejection; it is not a calibrated or robust
geometry gate. A bounded, target-free AABB pass now lists all inclusive
triangle-box overlap candidates at initial coordinates with stable global face
ordinals and exact artifact provenance. The contact-pair budget limits *all*
unordered comparisons, including non-overlaps; exhaustion returns no partial
result. Adjacent faces remain candidates. This is not triangle intersection,
penetration, a collision-free result or V6 evidence. An exact binary-rational
candidate narrowphase now detects intersections beyond intended shared
vertices/edges at the initial coordinates, including coplanar folded faces.
It is intersection-only: near-disjoint pairs, physical thickness, penetration,
contact response and V0/V6 clearance are not established. An exact all-pair
minimum squared-distance diagnostic now also covers disjoint AABBs without
rounding the rational mm² result. It has no acceptance threshold and excludes
shared-ID adjacent faces, so it still establishes no physical clearance or
contact response. Next: define and implement a versioned F0 contact policy and
calibrated model, then
V6 outcomes; then implement V7/V8 and V0-V10 orchestration with independent
negative tests. None of those stages may infer a physical pass from a valid IR,
an analytic proposal, or a converged numerical result alone. Free-form,
branching, garment, flat and lace work remain separate B9/B10 packages.
The admitted plain multi-course subpath has a compiler-to-initial-geometry
integration regression; it remains an experimental diagnostic, not a release
or physical-verification gate.

For B12, run the complete software suite, independent conformance, packaged
out-of-checkout smoke tests, compatibility/security/operational gates, and
versioned golden review. Physical specimens, calibrated material/model profiles
and independent holdouts are external B11 requirements; until they exist the
honest physical status is `UNTESTED`. Release remains **not ready**.

## Software checkpoint: 2026-09-29

The current source tree has exact, budgeted, source-bound V0 diagnostics through
nonadjacent face-pair intersection and near-contact, plus source-index-preserving
vertex/face ordering without a canonical mesh identity. Shared-index adjacent
residual contact is explicitly unresolved; no normalized mesh or V0 pass is
issued. The B7 isolated-worker IPC boundary now records malformed or deeply
nested child replies as immediate generic internal failures. Integration checks
passed: 534 Python tests, Ruff, strict mypy on 47 source files, all five
independent Node canonical vectors, and `git diff --check`.

The profile-bearing source distribution and wheel built successfully. On
2026-09-30 the wheel was installed into a separate venv and its CLI, bundled
schemas and immutable profile passed checks outside the source checkout.
This venv inherited existing runtime dependencies via system-site-packages;
fully isolated dependency installation remains a release check. Next software package: specify and
test the missing adjacent residual-contact policy without treating incidental
shared-simplex contact as physical clearance, then complete V0 canonical
normalization, boundary assignment and fail-closed admission. The open B1/B3-B10
packages remain required independently of this V0 work.

## Software checkpoint: 2026-09-30

Directed boundary cycles now preserve source-face winding, have canonical
starting vertices, and retain source-to-ordered index maps. Component keys and
loops are ordered deterministically. The stage revalidates the full source and
prior ordering evidence and refuses invalid topology. It does not assign
openings or certify a semantic mesh identity. Exact landmark-to-loop eligibility
now records per-loop rational distances and all candidates under the immutable
slack rule, with whole-work budgets and explicit ambiguity. It does not yet bind
complete DesignSpec openings. Integration passed 558 tests, Ruff, strict mypy on
49 source files, all five independent Node canonical vectors, and diff checks.
Certified filtered orientation is the next bounded stage; further V0 admission
and independent backend gates remain open.

## External dependencies and operational authority

Physical specimens and new golden approvals require human input. Numerical
policies need units, rationale, owner and calibration evidence. Multi-user
authentication depends on deployment scope; local-only operation must not be
presented as a multi-user service. No commits, pushes, publication or paid
services are authorized by this plan. The user subsequently authorized GitHub
checkpoint commits and pushes on 2026-09-30; deployment and paid services still
require separate authority. Record exact remaining work at an interrupted checkpoint.
