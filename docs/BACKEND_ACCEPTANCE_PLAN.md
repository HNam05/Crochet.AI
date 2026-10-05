# Backend implementation and acceptance

Status: IN PROGRESS. This plan does not certify generated patterns.

The complete ordered implementation roadmap, dependencies, package acceptance
checks and physical-evidence prerequisites are maintained in
[BACKEND_IMPLEMENTATION_ROADMAP.md](BACKEND_IMPLEMENTATION_ROADMAP.md)
(2026-10-05). Its planned milestones do not change the implemented state below.

## Acceptance rule

Each promised capability needs an executable implementation, independent tests,
documented limits, and a stable versioned interface. Rejecting an unsupported
domain is safe behavior, not completion of that domain. Real calibration and
holdout measurements are required for physical claims. Canonical contracts and
approved goldens remain frozen. Production frontend work is outside backend
release acceptance. The user separately authorized a bounded local browser
prototype for human crochet testing on 2026-10-04, with a mobile app deferred;
see [LOCAL_PROTOTYPE_V1.md](LOCAL_PROTOTYPE_V1.md). This changes delivery sequencing,
not mandatory verification or physical acceptance.

## Packages in delivery order

| ID | Deliverable | Required acceptance evidence | Current state |
| --- | --- | --- | --- |
| B0 | Canonical runtime and semantic validator | Python and independent Node conformance | Implemented 1.0 and additive 1.1; recheck at release |
| B1 | Visible parser, binder, exporter, detached certification | Independent fixtures; order, anchors, colors, malformed text, semantic round trips, strict typing | M1A subset implemented; M1B and V9/V10 remain |
| B2 | Input/material resolution and geometry adapters | Immutable references, units, semantic negatives, robust predicates and boundary tests | Supported DesignSpec 1.1 mesh profiles have bounded V0 admission, exact adjacent and nonadjacent pair decisions, opening binding and normalized mesh evidence; flat, lace and non-mesh adapters remain open |
| B3 | Analytic solver and independent candidate checks | Reachability proof, bounded global count search, reproducible traces, adversarial fixtures | Narrow closed-pole SC proposal implemented; full V5 and domains remain |
| B4 | Target-independent F0 simulation | Dimensioned energies, target-leakage tests, convergence and collision evidence | Target-free experimental stretch, shear and bending terms with bounded combined descent and exact final-coordinate intersection/distance diagnostics; contact response, calibrated convergence and V6 missing |
| B5 | Geometry, robustness and V0-V10 orchestration | Independent synthetic metrics, bounded scenarios, fail-closed outcomes, provenance | Ordered V0-V10 checkpoint, supported mesh V0, core V1-V3 and single-yarn M1A V9 are integrated; full V4/V5-V8/V10 and calibrated forward/metric evidence remain open |
| B6 | Versioned API and CLI | Contract tests, structured errors, deterministic artifact retrieval | Local transport-independent API/CLI subset implemented; release contract open |
| B7 | Durable jobs and artifacts | Atomicity, idempotency, cancellation, resource limits, concurrency and recovery tests | Local SQLite jobs subset implemented; operational gates open |
| B8 | Security, packaging and operation | Untrusted input limits, path safety, isolation, diagnostics, install and end-to-end tests | Request limits and wheel subset implemented; service hardening open |
| B9 | Free-form, geodesic, topology and frontier solvers | Separate applicability contracts, branch/join fixtures, budgets, independent reconstruction | Missing; research required |
| B10 | Garment, flat and lace solvers | Separate domain contracts, semantics, fixtures and acceptance | Missing; research required |
| B11 | Empirical material and acceptance profiles | Real calibration samples, frozen thresholds, separate holdouts, human review | Frozen pilot campaigns, append-only measurements, baseline Type-A drafts and PDF measurement sheets implemented; full uncertainty, open-tube instructions, physical evidence and accepted profiles remain open |
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
that limitation was closed on 2026-09-30 by a clean venv installation and
byte-exact installed-package smoke; additional platform/version combinations
remain release checks. Next software package: specify and
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
slack rule, with whole-work budgets and explicit ambiguity. Full semantically
validated DesignSpec/material/source binding now requires a unique bijection
between retained openings and boundary loops. The additive API operation
`inspect_mesh_openings` exposes this under server-owned limits and persists
through the local queue; it explicitly reports preflight `INDETERMINATE`.
Certified filtered orientation is implemented separately with independent
homogeneous rational test oracles, not yet wired into V0 mesh admission.

The user's adjacent-zone decision is implemented as a separate experimental
exact kernel. Its caller-explicit rational barycentric zone excludes only
point pairs with both points inside their respective open zones; mixed pairs
are checked. Full original-face overlap/contact is checked before exclusion.
No default lambda, physical calibration, retessellation invariance, frozen
profile mutation or V0 pass is introduced. See
[`ADJACENT_RESIDUAL_EXPERIMENT.md`](ADJACENT_RESIDUAL_EXPERIMENT.md).
The experimental mesh-wide residual wrapper now recomputes source, topology
and ordering and prechecks aggregate pair work before distance evaluation,
retaining exact distances and complete provenance. Versioned admission policy
and independent backend gates remain open; no acceptance threshold is chosen.
Integration checkpoint passed 649 Python tests, Ruff, strict mypy on 52 source
files, all five independent Node canonical vectors and `git diff --check`.
The following integration passed 692 Python tests, Ruff including the new
installed smoke tool, strict mypy on 53 source files, all five Node vectors and
diff checks. A freshly built wheel passed `pip check` and installed smoke in a
clean Python 3.11.9 venv with no system-site packages, outside the checkout.

The user-approved additive DesignSpec 1.1 and numerical profile 2 now require
an explicit reduced rational barycentric exclusion size. Legacy records,
schemas and goldens remain unchanged. See `DESIGN_SPEC_1_1.md` and
`NUMERICAL_GEOMETRY_2.md`. Version-specific end-to-end V0 integration remains
open; legacy-only operations reject the new profile rather than downgrade it.
The source-bound winding proposal checks complete pair and volume-component
evidence and proposes only whole closed-component reversals. Mixed open and
closed meshes remain explicitly unsupported. It is not an outward-orientation
or complete mesh-acceptance proof. Integration passed 746 Python tests, strict
mypy on 55 source modules, Ruff, all five independent Node vectors and diff
checks. The rebuilt wheel passed dependency checks and isolated installed smoke
outside the checkout in the clean Python 3.11.9 venv, including byte parity for
all eight schemas and both numerical records. This is a local installation
check, not a cross-platform or production deployment acceptance.

The current local checkpoint adds `inspect_v0_mesh_v2`, a mesh V0 admission path
for closed/open amigurumi and garment surfaces under DesignSpec 1.1 and
numerical profile 2. The closed-only compatibility operation remains. The
source-bound adjacent residual now receives an exact profile threshold decision
for every adjacent pair; the enclosing V0 check also requires complete original
face-pair coverage, numerical degeneracy and nonadjacent clearance checks,
stable closed-component volume signs, unique retained-opening assignment where
applicable, and a hashed normalized mesh with index maps. The runtime keeps
full-pattern verification `NOT_VERIFIED` and physical status `UNTESTED`. Flat,
lace and non-mesh V0 profiles remain outside this operation; they cannot
inherit its `PASS`.
The integration suite passed 766 Python tests, Ruff, strict mypy on 57 source
modules, all five independent Node conformance vectors and `git diff --check`.
The rebuilt wheel passed dependency checks and installed smoke in a clean Python
3.11.9 venv outside the checkout. These are local software checks only.

The next target-free F0 checkpoint adds an exact self-intersection diagnostic
for final stretch-prototype coordinates. It checks complete face-pair coverage
and optimizer provenance, and reports the exact minimum nonadjacent squared
distance. It has no contact force or calibrated clearance policy. V6 remains
open; this diagnostic cannot promote an experimental force balance to
`CONVERGED`.
The follow-up integration passed 770 Python tests, Ruff and strict mypy on 58
source modules. This checkpoint does not add a V6 acceptance claim.

The next B4 software increment adds versioned, target-free shear and bending
energies for the supported plain quad strip, plus bounded combined descent over
stretch, shear and bending. Shear stiffness/rest cosine and bending stiffness/
rest dihedral are explicit `HYPOTHESIS` inputs with provenance; none is inferred
from the heuristic initialization. The combined final coordinates feed the exact
self-contact diagnostic with all three term identities and provenance checked.
All outputs remain experimental. Contact response, calibrated convergence and
the V6 admission gate remain open.
This integration passed 786 Python tests, Ruff, strict mypy on 60 source
modules, all five independent Node conformance vectors, and `git diff --check`.
The rebuilt wheel passed dependency and installed smoke checks outside the
checkout in a clean Python 3.11.9 venv; the new B4 modules import from that
wheel. These checks establish software integrity for this experimental slice,
not complete B4 or backend acceptance.

## Software checkpoint: 2026-10-04

The additive `run_forward_prototype` operation connects physical projection,
material graph, initialization, stretch/shear/bending optimization and exhaustive
final-coordinate contact diagnostics through the local API, generic CLI and
durable queue. The closed recipe enforces server-owned work limits and explicit
hypothesis parameters. See [FORWARD_PIPELINE_V1.md](FORWARD_PIPELINE_V1.md).

The supported surface is a plain aligned cyclic quad strip with open boundaries.
A separately identified coordinate restriction connects the optimizer's full
node domain to the contact diagnostic's surface-only domain. Failed or exhausted
runs expose no geometry; forbidden final intersections also suppress nested
optimizer coordinates. All results remain `NOT_VERIFIED`, `UNTESTED` and
`v6_outcome:NOT_RUN`. Contact response, calibrated convergence, V6/V7/V8,
broader construction and backend release remain open.

The user-approved live object and crochet-step inspiration is recorded in
[PRODUCT.md](PRODUCT.md), with source evidence in the Yarnify3D research record.
This checkpoint provides a bounded backend integration foundation; it does not
implement either user interface or a live making-session contract.

Integration passed 814 Python tests, Ruff across source/tests/tools, strict mypy
on 61 source modules, all five independent Node canonical vectors and
`git diff --check`. The freshly built wheel passed dependency and installation
smoke checks in the clean Python 3.11.9 venv outside the checkout. A real installed
CLI forward request returned exactly the same response as source execution,
including 18 surface vertices, 24 triangles and both six-location boundaries.
These are software checks for the experimental slice, not physical or release
acceptance. Agent token/cost measurements were unavailable and remain null in
the ignored checkpoint record.

## Local browser prototype checkpoint: 2026-10-05

The user selected local browser testing now and a separate mobile app later.
The additive prototype supports sphere/ellipsoid requests and user-entered
cyclic SC gauge, producing canonical CrochetIR, controlled Pattern V1 and
German instructions. The analytic search proposes course counts; the existing
compiler fixes continuous work order with zero course phases. Independent
semantic validation and export round trip remain mandatory. Existing solver,
verifier, schemas and goldens were not changed for this prototype.

The browser connects real generation, schematic stitch selection/orbit,
incremental construction, current instruction/count, durable revision-checked
progress, source-bound human feedback and artifact downloads. The preview
uses construction counts and material pitch; it is not a calibrated forward
prediction. Full verification remains `NOT_VERIFIED`, physical status `UNTESTED`.
See [LOCAL_PROTOTYPE_V1.md](LOCAL_PROTOTYPE_V1.md) for the bounded contract and
[PROTOTYP_TESTEN.md](PROTOTYP_TESTEN.md) for the actual crochet test protocol.

Integration passed 823 Python tests, Ruff across source/tests/tools, strict mypy
on 66 modules, nine frontend state tests, all five independent Node canonical
vectors and `git diff --check`. The final wheel passed dependency and installed
smoke checks outside the checkout, including all seven browser assets and the
prototype console entry point. Actual source and installed HTTP generation
produced identical IR and Pattern V1. The default software fixture has 18 courses
and 339 instructions; changing gauge and size changes the construction.

Live browser checks covered sphere/ellipsoid generation, compound increases,
forward/back and course navigation, orbit/keyboard/zoom/object selection,
incremental display, reload/restore, real downloads and feedback persistence.
The narrow mobile browser layout was checked at 390 px; this does not deliver
the separately requested mobile app. Test feedback is explicitly a software
test, not a crocheted specimen. The user server is loopback-only; physical
calibration, broader construction and full backend release remain open.
Worker usage/cost measurements were unavailable and are recorded as null in
`artifacts/agent-costs/local-prototype-20261005.json`.

## Shapes and printable test checkpoint: 2026-10-05

The local prototype now offers closed cylinders, cones, capsules and an organic
pear alongside sphere/ellipsoid. The new forms reuse the existing hashed
surface-of-revolution contract, analytic count search, canonical IR compiler
and independent semantic/round-trip checks. Capsule dimensions are constrained;
unsupported shapes and exhausted construction budgets fail explicitly. No
solver, independent verifier, schema or golden was changed for this expansion.

PDF export is local and source-bound. It rebuilds instructions from persisted
validated IR, checks material/design/request identity and groups only identical
contiguous instructions without losing their work order or stitch totals.
Round headers and instructions remain together on printable A4 pages.
Each PDF includes material values, source identity, status and a worksheet for
measurements, stuffing state, problem rounds and required changes. Unsupported
font characters fail explicitly. ReportLab and dependency notices are reviewed
in [the PDF decision record](research/PROTOTYPE_PDF_REVIEW_2026-10-05.md).

Final integration: 837 Python tests passed, including all four new shape
candidates and PDF metadata/content/routing/ordering/pagination checks. Ruff,
strict mypy on 68 modules, ten frontend state tests and five Node canonical
vectors passed. The rebuilt wheel passed dependency checks and installed smoke
outside the checkout. Source HTTP and installed rendering produce identical
PDF bytes for the actual pear project; an earlier saved sphere also exports.
All five pear PDF pages were rendered and visually reviewed.

Live UI checks covered pear/capsule generation, preserved gauge examples,
invalid capsule dimensions, persistent step resume and narrow layout without
horizontal overflow. The PDF button fetched valid content and started a browser
download; the in-app automation download event was unavailable, so a separate
PDF from the same endpoint is retained for review. No filesystem completion is
claimed from the button's status alone. The existing visual design is retained.
[The human test protocol](PROTOTYP_TESTEN.md) defines sphere/capsule/pear trials
using the actual tester's measured material. Physical status remains UNTESTED;
full verification, broader organic/multipart generation and the separate mobile
app remain open. Two bounded Luna/medium workers were used; runtime token/cost
measurements are unavailable and recorded as null in
`artifacts/agent-costs/extended-prototype-20261005.json`.

## Gate and calibration implementation checkpoint: 2026-10-05

The first executed roadmap section adds a versioned capability inventory,
ordered V0-V10 evidence, strict profile/input/source identity, predecessor-bound
resume and fail-closed status aggregation. Supported mesh V0, input/semantic
checks and real single-yarn DE/US/UK M1A round trips execute through the local
API, CLI and durable jobs. Job completion does not imply pattern verification.
The configured verification profile remains uncalibrated.

Frozen calibration campaigns and append-only SQLite measurements preserve
specimen roles, raw readings and correction history. Draft material derivation
uses one protocol-fixed raw baseline per independent specimen; repeated readings
remain visible for review. SQL identity/link columns are checked against record
content. Drafts cannot promote themselves to a calibrated profile. A four-page
PDF measurement protocol is available in the browser; it is not the still-missing
open-tube crochet construction. See [CALIBRATION_CAMPAIGNS.md](CALIBRATION_CAMPAIGNS.md).

The P03/P04 follow-on adds explicit sphere/ellipsoid ideal target admission and
bounded target-side sampling, plus a separate closed combinatorial cellulation
for Plain/INC/DEC, ring anchors and final caps. Independent tests check edge
incidence/orientation, vertex links and Euler characteristic. Source projection
hashes are recomputed; target/source metadata cannot enter the cell builder.
The API exposes both inspections without claiming candidate topology or physical
verification. V4 is still INDETERMINATE, V5-V8/V10 are NOT_RUN.

Integration passed 957 Python tests, strict mypy on 76 modules, Ruff, ten frontend
state tests and five independent canonical Node vectors. Packaging dependency
checks and isolated installed smoke checks passed, including the new operation
inventory, analytic/cell modules and deterministic measurement PDF. Source and
isolated installed API checks construct cells from actual saved sphere/pear IR;
the installed PDF is identical to the reviewed HTTP/download artifact. The live
sphere passes ideal-target V0, the generic pear remains INDETERMINATE, and both
remain NOT_VERIFIED/UNTESTED. Five saved projects survive the server restart.
The PDF was rendered and visually reviewed. Reopening calibration databases
also verifies column order/types, primary/unique identities, correction-index
predicate and foreign-key bindings before changing journal mode.
These checks establish software behavior, not calibration or physical
pattern validity. Complete topology, candidate verification, physical simulation,
geometry comparison, robustness, physical provenance, further solver domains and
release operations remain open. No solver, existing validator, schema or golden
was changed. Six bounded Luna/low agents performed implementation and read-only
reviews; unavailable cost/token measurements are recorded as null in
`artifacts/agent-costs/backend-implementation-20261005.json`.
Follow-on implementation is recorded in
[BACKEND_IMPLEMENTATION_ROADMAP.md](BACKEND_IMPLEMENTATION_ROADMAP.md).

## Independent surface topology checkpoint: 2026-10-05

`SURFACE_TOPOLOGY_AUDIT_V1` independently checks the generated closed triangle
complex, without importing the cell builder. It detects duplicated faces,
unused vertices, invalid edge incidence/orientation, disconnected components
and non-cyclic vertex links. Rational Betti dimensions are derived only after
the closed oriented manifold prerequisites pass. Hand-authored tetrahedron,
torus, disconnected and pinched fixtures establish separate positive/negative
oracles; a bounded-identifier regression guards early input rejection.

The additive `inspect_closed_surface_topology` API/CLI/job operation derives
all cells from validated server-side source artifacts. V4 records exact surface
metrics, budgets and linked projection/cell/audit hashes. Defective surfaces fail
V4. A successful surface audit retains INDETERMINATE because the independent
source-stitch-to-cell incidence conformance proof is not yet implemented.
A wrong-but-spherical replacement fixture specifically verifies this boundary.
No generator, existing semantic validator, schema, golden or physics rule was
modified for this checkpoint. It introduces no numerical tolerances.

Live saved sphere and pear projects pass the surface audit while remaining
NOT_VERIFIED/UNTESTED; all eight saved projects survive the restart. HTTP V4,
source CLI and isolated installed-wheel inspection produce identical audit
evidence. The independent read-only review found no topology/Betti defect;
its label-length admission suggestion is implemented and tested. Remaining
P03-P13 and broader domain/release requirements retain their previous status.
See [SURFACE_TOPOLOGY_AUDIT_V1.md](SURFACE_TOPOLOGY_AUDIT_V1.md). Unavailable
worker usage/cost measurements remain null in
`artifacts/agent-costs/surface-topology-20261005.json`.

Integration validation passed 999 Python tests, Ruff, strict mypy on 77 modules,
five independent canonical vectors and ten frontend state tests. The rebuilt
wheel passes dependency checks and isolated out-of-checkout installation smoke;
its actual saved-pear surface audit matches both CLI and HTTP evidence exactly.
These are software checks, not full backend or physical acceptance.

## Closed-cell source conformance checkpoint (2026-10-05)

`CLOSED_CELL_CONFORMANCE_V1` validates and hashes raw CrochetIR independently
of the cell builder and projection extraction. Exact face-slot predicates bind
each triangle to source stitch bases/tops, ordered anchored cycles, event coverage
and initial/terminal caps. Cell envelope/content digests and source identifiers
are checked; source tables and reference lists are bounded before hashing.
There are no numerical tolerances or changes to the generator, schemas, goldens,
existing semantic validator or physical model.

V4 now passes in the supported closed single-component, single-branch, single-yarn
SC amigurumi scope only when surface manifold/Euler/Betti and source-cell proofs
both pass and DesignSpec component/boundary requirements match. Unsupported scope
or exhausted proof budgets remain INDETERMINATE. Mismatched generated mappings
fail, including topology-preserving altered diagonals and unrelated spheres with
refreshed hashes. Wider V4 construction coverage and V5-V8/V10 remain open;
overall NOT_VERIFIED and physical UNTESTED remain unchanged.

The additive `inspect_closed_cell_conformance` API/CLI/job operation exposes both
separate immutable proofs and hashes. Live saved sphere and pear projects reach
V4 PASS; all eight saved projects remain intact. Source CLI, isolated installed
CLI and HTTP V4 proof payloads/hashes agree exactly. The rebuilt wheel passes
dependency and isolated installation checks. The independent review's pre-hash
table-bound finding is repaired and regression-tested. Worker usage measurements
are unavailable and remain null in `artifacts/agent-costs/cell-conformance-20261005.json`.
Integration validation passed 1,017 Python tests, Ruff, strict mypy on 78 modules,
five independent canonical vectors and ten frontend state tests. These checks
do not establish full backend or physical acceptance.
See [CLOSED_CELL_CONFORMANCE_V1.md](CLOSED_CELL_CONFORMANCE_V1.md).

## Independent analytic candidate-claims checkpoint (2026-10-05)

`ANALYTIC_CANDIDATE_CLAIMS_V1` independently reconstructs course counts,
binary SC transitions, balanced shaping, cyclic phases and construction quantities
from validated raw CrochetIR. It checks recorded run bounds, parameter hashes,
profile/material conditions and prototype final-count/phase metadata without
calling the solver, compiler, placement optimizer or cell builder. Indexed source
table permutations preserve identical proof hashes. This introduces no numerical
tolerances or changes to generation, schemas, goldens or semantic validation.

The additive `inspect_analytic_candidate_claims` API/CLI/job operation returns
immutable source-bound evidence. V5 requires V1-V4 to pass, rejects false claims,
and remains INDETERMINATE while actual input-bound search traces, count-window
admission, work/completion and deterministic selection evidence are unavailable.
Resource exhaustion emits no partial proof. Declared work-counter bounds do not
establish actual search work or the validity of a proposal score after prototype
phase-zero recompilation. V6-V8/V10 and physical acceptance remain open.

All eight saved projects survive the server restart. Live sphere and pear pass
every reconstructed assertion, retain V4 PASS and V5 INDETERMINATE, and remain
NOT_VERIFIED/UNTESTED. Source CLI, isolated installed-wheel CLI and live HTTP V5
payloads and hashes agree exactly for the saved pear. The rebuilt wheel passes
dependency and isolated out-of-checkout installation smoke checks. The focused
implementation/review findings are repaired and regression-tested. Unavailable
worker token/cost measurements remain null in
`artifacts/agent-costs/analytic-claims-20261005.json`.
See [ANALYTIC_CANDIDATE_CLAIMS_V1.md](ANALYTIC_CANDIDATE_CLAIMS_V1.md).

Integration validation passed 1,050 Python tests, including 81 targeted claim/API/
checkpoint/pipeline tests, Ruff, strict mypy on 79 modules, five independent Node
canonical vectors and ten frontend state tests. These checks establish software
behavior, not complete V5, full backend acceptance or physical pattern validity.

## Analytic search-trace producer checkpoint (2026-10-05)

The separate producer `ANALYTIC_SEARCH_TRACE_V1` binds canonical design/material,
target/config digests, algorithm versions and compiler source identity outside
CrochetIR. It records ascending hypothesis attempts, exact rational sampling and
circumferences, decimal-integer window bounds, per-pass/layer retained states and
work, partial interruptions, objectives, terminal causes and ordered proposal
hashes. Trace storage is limited to 8,192 reserved course slots; exhaustion remains
a bounded-search outcome, not an impossibility claim. Early unadmitted runs carry
no trace. No numerical tolerance, schema, golden or independent gate was changed.

The generation API/CLI/job response includes immutable trace bytes/hash. New
prototype projects persist a separate hashed `PROTOTYPE_GENERATION_LINK_V1` that
binds the optimized proposal to the actual fixed-zero-phase final IR. Proposal
scores are not final-IR quality evidence. Legacy saved records remain untouched.
V5 still does not admit or independently replay this producer evidence, so
NOT_VERIFIED/UNTESTED and all open physical/domain/release requirements remain.

Hand-counted count/phase work oracles cover complete and interrupted passes;
initial state exhaustion, sample failures, circumference overflow and extreme
empty-window bounds are regression-tested. An isolated comparison against the
pre-instrumentation Git HEAD preserved both proposal hashes exactly. Forty-eight
targeted analytic tests and four API/job/prototype/legacy delivery tests passed.
Ruff, strict mypy on 80 modules, five independent canonical Node vectors and ten
frontend state tests passed. Wheel dependency and isolated out-of-checkout smoke
checks passed. Live HTTP trace/proposal payloads and hashes match source and
isolated installed-wheel CLI generation exactly. Eight existing project sessions
are preserved; nine projects are now saved, including the new traced checkpoint.
Full integration passed 1,062 Python tests. Validation and publication context are recorded in the current
[BACKEND_HANDOFF.md](BACKEND_HANDOFF.md). Worker usage measurements are unavailable
and remain null in `artifacts/agent-costs/analytic-search-trace-20261005.json`.
See [ANALYTIC_SEARCH_TRACE_V1.md](ANALYTIC_SEARCH_TRACE_V1.md).

## External dependencies and operational authority

Physical specimens and new golden approvals require human input. Numerical
policies need units, rationale, owner and calibration evidence. Multi-user
authentication depends on deployment scope; local-only operation must not be
presented as a multi-user service. No commits, pushes, publication or paid
services are authorized by this plan. The user subsequently authorized GitHub
checkpoint commits and pushes on 2026-09-30; deployment and paid services still
require separate authority. Record exact remaining work at an interrupted checkpoint.
