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
| B2 | Input/material resolution and geometry adapters | Immutable references, units, semantic negatives, robust predicates and boundary tests | Partial input/material validation and meridional samplers; certified mesh path missing |
| B3 | Analytic solver and independent candidate checks | Reachability proof, bounded global count search, reproducible traces, adversarial fixtures | Narrow closed-pole SC proposal implemented; full V5 and domains remain |
| B4 | Target-independent F0 simulation | Dimensioned energies, target-leakage tests, convergence and collision evidence | Projection and topology-only graph/material resolution implemented; no F0 simulation or V6 pass |
| B5 | Geometry, robustness and V0-V10 orchestration | Independent synthetic metrics, bounded scenarios, fail-closed outcomes, provenance | Missing |
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
geometry gate. Next: establish robust geometric predicates and
implement and test contact and
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

## External dependencies and operational authority

Physical specimens and new golden approvals require human input. Numerical
policies need units, rationale, owner and calibration evidence. Multi-user
authentication depends on deployment scope; local-only operation must not be
presented as a multi-user service. No commits, pushes, publication or paid
services are authorized. Record exact remaining work at an interrupted checkpoint.
