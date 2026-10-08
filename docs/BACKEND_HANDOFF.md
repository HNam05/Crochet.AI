# Backend handoff

Latest checkpoint: 2026-10-08. Read this file before continuing backend work.
This is a working implementation checkpoint, not full backend acceptance.

## Repository and product

- Primary checkout: `C:\Users\hanne\OneDrive\Dokumente\Crochet\Crochet.AI`.
- Repository: `https://github.com/HNam05/Crochet.AI`, branch `main`.
- User authorized continuing backend implementation and committing/pushing the
  code and status notes in the current request. Never force-push.
- Local browser testing comes first; a separate mobile app is still required
  later. Current prototype layout is sufficient; prioritize backend completion.
- CrochetIR is canonical. Preserve solver/verifier separation, deterministic
  bounded generation, fail-closed gates, frozen schemas and human-approved goldens.

## Implemented so far

- Canonical schemas/hash profiles and exact semantic/reference/frontier checks.
- Bounded analytic closed-pole single-yarn SC proposals, global count DP followed
  by phase DP, explicit compilation to complete CrochetIR.
- Local six-shape pilot, live instruction/stitch progress and schematic object
  preview, saved projects/sessions, optimistic revision conflicts, feedback.
- English printable PDF: Round/R1 notation, MR/SC increases/decreases, parenthetic
  total stitches at the end of each round, no newly-created-stitch totals.
- Versioned API/CLI, durable SQLite jobs, bounded transport/process isolation,
  wheel packaging and isolated installation checks.
- Calibration campaign/store, printable measurement packet and draft material
  derivation. Physical measurements are not invented or accepted as calibrated
  merely because their software records validate.
- V0 mesh admission, ideal sphere/ellipsoid targets and additive DesignSpec 1.2
  simple explicit-coordinate revolution targets. Arbitrary axes/open coordinate
  targets and native cylinder/cone interfaces remain partial. The closed-coordinate
  producer now samples authoritative knots and emits unverified SC proposals.
- Target-free shaped-cell construction, independent surface manifold/Euler/Betti
  audit and independent raw-IR-to-cell conformance. V4 can PASS only in the
  documented closed single-component/branch/yarn SC subset.
- Independent V5 candidate-claims subset: counts, binary transitions, balanced
  shaping, phases, construction maxima, parameter/hash/material/run conditions.
  Contradictions FAIL; absent complete search/physical evidence stays incomplete.
- Experimental target-free stretch/shear/bending and contact diagnostics are
  computational slices, not complete physical F0/V6 acceptance.
- Closed shaped SC rest preparation and distinct ring/course initialization
  with initial elastic forces are available through API/CLI/isolated jobs;
  a new separate profile adds tension-only ring/CLOSE, declared pressure and
  bounded experimental optimization. Calibrated closure/cap material, shaped
  shear/bending, contact response, multistart and independent V6 remain missing.

## Previous producer checkpoint

Producer-only `ANALYTIC_SEARCH_TRACE_V1`: input/config/target/source bindings;
ascending hypothesis prefix; exact circumference/window inputs; per-pass/layer
count and phase work/state accounting; interruption and terminal causes;
proposal IR hashes. Immutable JCS trace/hash is outside canonical IR and exposed
by generation API/CLI/jobs. New prototype projects persist a separate hashed
proposal-to-final link for FIXED_ZERO_CONTINUOUS_V1 recompilation. Legacy projects
are not rewritten or given invented traces. Trace reservation is bounded at
8,192 attempted course slots per invocation.

The independent V5 checker is deliberately unchanged in this producer task.
Trace integrity/availability does not establish independently verified search.
Full verification remains NOT_VERIFIED and physical status UNTESTED.

## Independent replay checkpoint

`ANALYTIC_TRACE_AUDIT_V1` now independently replays the complete staged bounded
sphere/equal-axis-ellipsoid search. It recomputes input/config/material/target
bindings, samples, integer windows, both count-DP passes, phase-DP objectives and
exact ties, all layer work/interruptions, ascending hypothesis prefix, remaining
global budgets, terminal cause and original proposal hash order. Every supplied
raw proposal is independently checked for actual count/phase schedule, bounds,
declared source/config consistency and work claims. Proof work is capped at
6,000,000 units. Neither replay kernel imports producer generation code.

API/CLI/jobs expose `inspect_analytic_search_trace`. Optional `search_evidence`
on `verify_candidate` binds the audit into V5 evidence. False trace claims FAIL;
missing original proposals, proof exhaustion or unsupported samplers remain
INDETERMINATE. Native candidate membership is checked before confirming trace
checks. V5 still awaits physical feasible-selection evidence. Audit PASS does
not authenticate source execution or pass V6-V8/V10; the report explicitly says
source_authentication=NOT_VERIFIED and physical_status=UNTESTED.

The prototype verification route replays stored traces diagnostically. Historical
hash-only projects remain incomplete; do not regenerate missing proposals or
silently rewrite existing projects. Complete new snapshots are described below.

Independent small exhaustive/hand oracles caught and repaired a DEC-center
arity error in the new verifier before integration acceptance. Count/phase
producer implementations, authoritative schemas and goldens are unchanged.

## Complete proposal persistence checkpoint

New projects retain the complete original raw CrochetIR proposals in
`PROTOTYPE_PROPOSAL_BUNDLE_V1`, with a separate domain hash binding input hashes,
trace, original order, final project identity and the existing phase-policy link.
Existing SQLite project/session transactions and storage ceilings include these
snapshots; no tables, canonical schema or database migration are added. Session,
feedback and restart/download behavior preserve the bundle. Same-ID historical
records return unchanged without backfill. Partial or corrupted bundles fail
explicitly, including deletion of the trace while retaining the bundle marker.

The local verify route admits the bundle and sends its original proposals to the
unchanged independent auditor. Complete new spheres can pass the scoped trace
audit. The existing zero-phase link is still producer provenance, not independent
proof of the final relation or physical feasible selection. Prototype V5 remains
INDETERMINATE; overall NOT_VERIFIED and physical status UNTESTED remain. Wider
samplers and full V6-V8/V10 acceptance are still open. API 2 MB/100,000-node limits
are unchanged; oversized verification fails explicitly rather than truncating.
Solver/compiler, independent auditor and verification-pipeline source are
unchanged in this producer/persistence package.

## Independent final-relation checkpoint

`PROTOTYPE_FINAL_RELATION_AUDIT_V1` independently binds a retained native analytic
proposal to the fixed-zero-phase prototype IR. It checks exact source parameters
and provenance, each parameter digest, actual round counts and phases, balanced
shaping, both raw ordered stitch/frontier chains and every required anchor update.
Only after these checks may phase-dependent connections be omitted from the
canonical semantic comparison. Solver/compiler, proposal persistence, schemas
and goldens are unchanged.

API/CLI/durable jobs expose `inspect_prototype_final_relation`. V5 invokes it only
after independent search audit PASS and a unique provenance match from the same
audited raw proposal batch. Relation PASS removes exactly
final_candidate_to_original_proposal_relation. Native proposal verification keeps
its existing behavior; missing or ambiguous originals cannot establish proof.
Physical feasible selection and physical_verification remain open; V5 stays
INDETERMINATE, overall NOT_VERIFIED and physical UNTESTED.

Hand-authored adversarial fixtures demonstrate why schema acceptance, correct
counts and a phase-stripped comparison alone are insufficient: a valid hidden
intermediate frontier rotation must fail raw replay. Canonical schedule strings
reject padded numbers such as "06". Additional boundary tests require complexity
limits before hashing and reject client reports or budget overrides.

## Explicit coordinate target checkpoint

DesignSpec 1.2 adds ordered radius_mm/axial_mm meridian knots under
SURFACE_OF_REVOLUTION_COORDINATE_PROFILE_CANONICAL_JSON_V1. Its AXIAL_LENGTH is
exactly the finite binary64 full axial extent, not endpoint displacement.
Old schemas, profiles, goldens and saved projects are not upgraded or backfilled.
See [ANALYTIC_COORDINATE_TARGET_V1.md](ANALYTIC_COORDINATE_TARGET_V1.md) and
[ADR 0017](adr/0017-explicit-analytic-meridian-coordinates.md).

The immutable ANALYTIC_COORDINATE_TARGET_V1 adapter supports simple CLOSED,
pole-ended AMIGURUMI_3D meridians and signed cardinal axes matching frame up.
Exact dyadic-rational predicates reject all segment crossings/touches/overlaps;
adjacent straight continuation remains valid. A fixed 129-knot/8,128-pair ceiling
bounds work. Explicit caps and simple nonmonotone axial movement are supported.
Finite distinct pole/cardinal witnesses guard representability at those points;
no universal binary64 sampling certificate is claimed. Ideal topology is genus
zero, distinct from candidate/mesh topology or physical stitchability.

API/CLI/isolated durable jobs expose existing inspect_analytic_target. V0 has a
separate coordinate scope, version, budgets and linked target hash: valid ideal
targets PASS, proved coordinate contradictions FAIL/E_INPUT, unsupported scopes
stay INDETERMINATE. New coordinates do not enter the independent forward model.
At this admission checkpoint, the only generator-side change was an explicit
NOT_APPLICABLE admission guard;
count/phase search, compilation, independent candidate replay and CrochetIR are
unchanged. Coordinate generation was still open at that checkpoint; the producer
extension below now implements it. Independent sampling/V7 and physical acceptance
remain open, overall NOT_VERIFIED and physical UNTESTED.

One bounded Luna/medium worker implemented the input/target/admission package.
A read-only Luna mathematical reviewer checked the ideal embedding proof and
exact predicate implementation; no concrete bug was found in that limited scope.
Primary independently reviewed schemas, API/V0 evidence, hashes and counterexamples.
This review does not cover baseline physical-model or full release correctness.

## Explicit coordinate producer checkpoint

EXPLICIT_COORDINATE_MERIDIAN_V1 derives segment lengths from admitted authoritative
radius/axial knots. Exact rational squared-distance checks certify bounded hypot
enclosures, and rational cumulative lengths preserve short segments. Total length
error and every returned s/radius/axial conversion must meet the caller's numerical
policy. Failed enclosures, overflow and excess rounding fail explicitly; segment
work obeys max_arc_panels. Length tolerance is not physical or V7 acceptance.
See [ANALYTIC_COORDINATE_GENERATION_V1.md](ANALYTIC_COORDINATE_GENERATION_V1.md)
and [ADR 0018](adr/0018-bounded-coordinate-meridian-generation.md).

Generation reuses unchanged count/phase DP and the complete CrochetIR compiler.
Coordinate-only solver provenance records sampler version, target hash and work;
the existing trace also retains signed axial samples. Old input paths do not gain
these fields or parameters. API/CLI/jobs use existing generation dispatch.
New cylinder/cone/capsule/pear pilot requests author DesignSpec 1.2 coordinates,
with AXIAL_LENGTH binding full extent. Legacy authoring and saved projects remain
unchanged. Sphere/ellipsoid authorship is unchanged.

The independent sphere auditor, candidate/final-relation checkers, V0 pipeline,
forward model, schemas and goldens are unchanged in this producer package.
Coordinate traces remain INDETERMINATE with unsupported_target_sampler; extra
coordinate provenance also remains explicitly unsupported by the narrower claims
checker. No producer analysis is promoted to independent evidence. Overall
NOT_VERIFIED and physical UNTESTED remain; coordinate replay/V7 and physics are open.

One bounded Luna/medium worker owns implementation with targeted tests; primary
owns numerical policy, independent adversarial tests, integration and publication.
A Luna/low mathematical reviewer checked the enclosure/2E displacement proof
and implementation. Token and cost measurements are unavailable, not estimates.

## Independent coordinate replay checkpoint

COORDINATE_MERIDIAN_REPLAY_V1 now independently reconstructs the admitted explicit
coordinate sampler and extends ANALYTIC_TRACE_AUDIT_V1's staged search scope.
It uses exact squared input distances, bit-enumerated binary64 neighbor enclosures,
exact accumulated lengths, independent linear segment lookup, strict conversion
checks and signed axial trace samples. Coordinate numerical work shares the
6,000,000-unit trace proof budget; exhausted proof is INDETERMINATE. No new
tolerance is introduced. Native sphere evidence bytes are preserved.
See [ANALYTIC_COORDINATE_REPLAY_V1.md](ANALYTIC_COORDINATE_REPLAY_V1.md) and
[ADR 0019](adr/0019-independent-coordinate-search-replay.md).

Raw candidate claims recognize the three coordinate-only solver parameters only
after independent numerical/input binding checks. Partial/false metadata fails;
unknown parameter semantics remains incomplete even after refreshed hashes.
The existing final-relation and V5 adapters can consume the extended search proof
without changing their raw construction predicates. Generation, canonical
schemas/goldens, count/phase replay kernels, final-relation/pipeline/API/storage
and the target-free forward model are unchanged in this verifier package.

Coordinate search/final-relation PASS removes only the scoped computational
missing checks. Physical feasible selection and physical_verification remain;
overall NOT_VERIFIED and physical UNTESTED remain. Thin-neck/unsupported scopes
are explicitly incomplete. Truthful reached sample-conversion/circumference
failure traces retain a named incomplete numerical-failure scope; forged success
or inconsistent reached-stage records fail. Preprocessing failures occur before
trace creation and return no producer trace. Full numerical-failure acceptance,
V7 coverage and physical calibration are separate remaining work.

One Luna/medium worker implemented the bounded verifier package with its tests.
Primary owns the contract, independent exact/property/adversarial and delivery
tests, numerical review, integration and publication. A read-only Luna/low
verifier reviewer checked the scoped numerical/trust boundaries. Its initial
preprocessing failure concern was withdrawn after actual producer runs confirmed
both cases return null trace; this was not a code defect or a weakened test.
The review did not establish full physical or release correctness. Usage/cost
measurements are unavailable and recorded as null in ignored agent-cost evidence.

## Closed shaped elastic checkpoint

FORWARD_SHAPED_ELASTIC_DIAGNOSTIC_V1 adds the missing closed-shaping elastic
preparation alongside the unchanged plain-strip optimizer. It admits an explicit
target-free hypothesis recipe, validates the closed cells before graph/coordinate
allocation, retains every PLAIN/INC/DEC incidence and assigns separately declared
ring rest lengths/stiffness. Gauge-based shape factors are explicit hypothesis
inputs, not empirically accepted material coefficients. Rest terms are prepared
before initialization, without deriving their values from initial geometry.

The new deterministic ring/course polygons cover every closed-cell vertex; the
existing spring kernel evaluates initial energy and nodal forces. The bundle
binds projection/material/recipe/cells, all terms/coordinates and missing checks.
Its shared spring kernel and closed-cell convention are documented dependencies,
not an independent physical verifier. Source IR identity stays outside the
physical bundle; excluded solver/target/color metadata cannot perturb it.
API/CLI/isolated jobs expose inspect_shaped_forward_model. No generator,
verification gate, old numeric algorithm, canonical schema/golden or storage
migration changes. Limits: 1 initialization, 2,048 vertices, 4,096 faces,
8,192 spring terms; malformed or failed numerical execution returns no bundle.
See [FORWARD_SHAPED_ELASTIC_V1.md](FORWARD_SHAPED_ELASTIC_V1.md) and
[ADR 0020](adr/0020-closed-shaped-elastic-diagnostic.md).

This closes one P04 preparation slice only. Closure mechanics/open fixtures,
shaped shear/bending, loading/contact response, optimization and calibration
remain missing. Geometry is comparison-ineligible, V6 NOT_RUN, overall
NOT_VERIFIED and physical UNTESTED. Initial force balance cannot establish
convergence or physical accuracy. No hypothetical coefficients were applied to
persisted projects or their human instructions.

One Luna/medium worker owns the new kernel and targeted tests; primary owns
the contract, API integration, independent force-gradient/incidence/metadata and
delivery checks, final review and publication. Primary review removed an unsafe
unsupported-topology assumption and repeated nested scans by reusing closed-cell
preflight and indexed ownership. A focused read-only Luna/low geometry reviewer
found no additional concrete issue in the reviewed scope; it did not run tests
or establish physical/release acceptance. Worker usage/cost measurements remain
null in ignored `artifacts/agent-costs/2026-10-08-shaped-forward.json`.

## Closed closure, pressure and optimization checkpoint

FORWARD_CLOSED_MECHANICS_PROTOTYPE_V1 adds an explicit outer recipe around
the shaped elastic preparation. Ring and final CLOSE cycles use tension-only
purse strings with independent rest perimeters/stiffness; pressure adds -pV
and the closed oriented surface volume gradient. Signed volume must exceed the
owned orientation epsilon and stay below an independently declared operational
volume limit even when pressure is zero. Positive constant pressure can make
this quadratic spring model unbounded: the volume guard is a divergence limit,
not an equilibrium target or calibrated threshold. No target geometry enters
mechanical execution.

The existing Armijo core is unchanged. Limits: 1 initialization, 2,048 vertices,
4,096 faces, 8,192 springs, 128 iterations, 512 complete objective callbacks,
32 trials per iteration. Preparation's one elastic energy evaluation is separately
recorded. Initial/final complete mechanics use counted callbacks only; the cache
holds one state. Invalid trial volume/closure edges backtrack; invalid initial
state, nonfinite sums or squared-force overflow yield NUMERICAL_FAILURE.
Failure/budget/line-search results publish no geometry or nested initial points.
Only EXPERIMENTAL_FORCE_BALANCED exposes comparison-ineligible debug geometry,
still NOT_VERIFIED, UNTESTED, V6 NOT_RUN. This does not accept contact, shaped
shear/bending, closure yarn/cap accuracy, multistart or calibration.

API/CLI/jobs: run_closed_forward_prototype. Local HTTP:
CSRF-protected POST /api/forward/closed with exact project_id and forward_run.
It executes stored source artifacts and checks retained proposal integrity,
without changing any project/session, instructions or previews. Limits apply to
the assembled request. Legacy evidence is never invented. See
[FORWARD_CLOSED_MECHANICS_V1.md](FORWARD_CLOSED_MECHANICS_V1.md) and
[ADR 0021](adr/0021-closed-closure-pressure-optimization.md).

One Luna/medium worker implemented the coherent kernel/test package; primary
owns contract, API/HTTP delivery, independent objective and publication checks.
A focused Luna/low geometry reviewer independently checked pressure derivatives
and exposed shared Armijo force-square overflow. Primary/worker review also
corrected force-map coordinates, hidden initial evaluation, oversized caching
and extreme finite closure arithmetic before integration. No old optimizer,
generator, verification algorithm, canonical schema/golden or storage migration
changes. Unknown worker token/cost measurements stay null in
`artifacts/agent-costs/2026-10-08-closed-mechanics.json`.

## Validation and runtime

Closed mechanics checkpoint: all 1,327 Python tests passed in 546.87 s.
The 24 new focused tests passed in 7.60 s: 13 worker kernel tests and 11 primary
independent objective/source-mutation/API/job/HTTP regressions. Full Ruff,
strict mypy on 91 source modules, five Node canonical vectors and ten frontend
tests passed. Bundled-runtime wheel build, clean no-index/no-dependency reinstall,
pip check and isolated external-directory installation smoke passed; nine
bundled schemas retain exact bytes. No dependency or global configuration changed.

Nine complete source/installed CLI envelopes agree: immediate initial balance,
nontrivial deformed SC 3/4/3, energy-budget exhaustion, invalid initial volume,
extreme finite pressure, extreme finite closure stiffness, prohibited target
override, and existing saved pear/sphere. Temporary loopback HTTP execution for
the saved pear and sphere agrees with both runtimes. The deformed synthetic case
uses 62 objective callbacks, 21 iterations and 41 trials; energy falls from
20.4499748137 to 7.6693981689 N mm and maximum force is 0.0431934055 N under
its explicitly synthetic 0.05 N criterion. Saved pear/sphere checks use a loose
synthetic criterion and establish delivery only, not nontrivial convergence.
All 12 listing/project snapshots were compared unchanged before/after execution.
The saved pear's English PDF remains 5,508 bytes / 3 pages; R1 MR/sc and final
parenthetic total notation were checked. No projects or measurements were created
or backfilled. Evidence: `artifacts/backend-closed-mechanics/`.

The first full run was stopped after an additional extreme finite closure test
exposed an uncaught -inf/+inf compensated sum. The guarded correction, regression
and complete rerun above passed. Preserve the distinct interrupted/final logs.
Publication restarts the owned port-8765 launcher/child pair against the final
checkout revision; verify listener ownership and advertised operation before
reusing runtime state in the next chat. Historical saved provenance is unchanged.

Shaped elastic checkpoint: all 1,303 Python tests passed in 521.22 s.
70 targeted shaped/API/job and existing strip-pipeline
tests passed in 23.53 s, including the worker's 13 kernel tests and primary's
10 independent derivative/incidence/metadata/delivery tests. Full Ruff, strict
mypy on 90 source modules, five Node canonical vectors and ten frontend tests
passed. Wheel build through bundled Python, clean no-index/no-dependency reinstall,
pip check and isolated out-of-checkout smoke passed; all nine schemas retain
their exact bundled bytes. The source venv lacks bdist_wheel; its distinct failed
build log is retained, and no dependency or global configuration was changed.

Seven complete source/installed CLI envelopes agree: plain/shaped minimal cases,
existing pear/sphere, missing material response, prohibited coordinate override
and overflowing force evaluation. Success is an initial diagnostic only;
errors return no geometry bundle. The unchanged stored pear produces 385 vertices,
766 faces and 786 springs; sphere 368/732/751. These are physical graph/cell counts,
not crochet round totals. All 12 live project snapshots/listing were compared
before and after the diagnostic delivery checks and remain identical; no project
was created or backfilled. Evidence: `artifacts/backend-shaped-forward/`.

Independent coordinate replay checkpoint: all 1,280 Python tests passed
in 540.28 s. The worker's 59 focused replay tests and 14 claims/delivery tests
passed; the full suite includes the primary's exact, high-precision, property,
adversarial, API/job and prototype integration checks. Full Ruff, strict mypy on
89 source modules, five independent Node canonical vectors and ten frontend
tests passed. Wheel build, clean isolated installation, dependency check and
out-of-checkout smoke passed; all nine schemas are bundled byte-for-byte.
Four complete source/installed CLI audit envelopes match: capped and nonmonotone
coordinate targets PASS, tampering FAIL, absent originals INDETERMINATE. The
complete native sphere audit retains its pre-edit canonical bytes and SHA-256
`5dd73d5d57bdeaabdaf57947e2ce64ba328f4f32e568bf645e44ae2b82cdc440`.

Live verification of the existing coordinate pear and complete-bundle sphere
now gives search/final-relation PASS, with exactly physical feasible selection
and physical_verification still missing from V5. Overall NOT_VERIFIED and
physical UNTESTED remain. The pear's 20 rounds/354 stitches and stored raw IR
are unchanged; its English PDF download passed (5,508 bytes). The hash-only
legacy sphere remains incomplete because original proposals are absent.
All 12 project snapshots and their listing were compared before and after live
verification/PDF export and remain exactly unchanged. No project was created or
backfilled. Evidence is under `artifacts/backend-coordinate-replay/`; worker
usage/cost remain null in `artifacts/agent-costs/2026-10-08-coordinate-replay.json`.

Previous accepted V5 claims checkpoint: 1,050 Python tests, Ruff, strict mypy on
79 source modules, five independent Node canonical vectors, ten frontend tests;
wheel dependency/isolated smoke and CLI/HTTP proof equality passed.
Producer trace checkpoint: 1,062 Python tests passed in 412 seconds; 48 targeted
analytic tests and four API/job/prototype/legacy tests also passed. Ruff, strict
mypy on 80 source modules, five Node canonical vectors and ten frontend tests
passed. Wheel dependency and isolated installed smoke checks passed. HTTP,
source CLI and installed CLI producer traces/proposal hashes agree exactly.
The pre-instrumentation solver comparison preserves both proposal hashes.
Code and this handoff are versioned together on `main`. For exact publication
revision, compare `git rev-parse HEAD` with `git ls-remote origin refs/heads/main`;
never treat an old note as confirmation of current GitHub or runtime state.

Independent replay checkpoint: 1,114 full-suite tests passed in 550.37 seconds.
After the final direct-call evidence-size guard, 90 count/phase/audit/API/pipeline
tests passed in 17.09 seconds. Ruff and strict mypy (84 source modules), five Node
canonical vectors and ten frontend tests passed. Final wheel build/install,
dependency check and isolated smoke passed. Source and installed CLI return
identical PASS reports for the historical native sphere proposal (44,289 proof
units); source CLI and live HTTP return identical INDETERMINATE stored-project
reports with only original_proposal_artifacts missing. Nine projects were retained
at that checkpoint.
The focused independent review found no additional fail-open computational claim.

Proposal snapshot checkpoint: 1,125 full-suite tests passed in 493.76 s;
15 targeted persistence/delivery tests passed in 48.53 s. Full Ruff and strict
mypy (85 source modules), five Node canonical
vectors and ten frontend tests passed. Wheel build/install, dependency check and
isolated installed smoke passed. Installed bundle admission returns the exact
original proposal. Source CLI, installed CLI and live HTTP return identical PASS
search-audit reports (44,289 proof units). A separate temporary-store HTTP check
confirmed nine explicit 422 E_PROVENANCE rejections across project/PDF/verify for
deleted trace, missing design identity and malformed original IR. Quota rollback
and the assembled verification request's 2 MB limit are covered by targeted tests.

Proposal snapshot checkpoint's live 40 mm sphere:
`057803daeb6335dad900570d00693ad08bdd4f44c59b5a4208b9868596e3dc45`.
GET restored the complete bundle; PDF export passed. At that checkpoint V5 had
these missing checks:
deterministic_candidate_selection_and_tie_break,
final_candidate_to_original_proposal_relation and physical_verification.
V5 INDETERMINATE, overall NOT_VERIFIED and UNTESTED are intentional. The nine
historical projects are preserved without backfill. This test project was created
from the final source snapshot before publication; its recorded historical commit
and snapshot are retained, not silently rewritten after publication.

Local browser: `http://127.0.0.1:8765/`.
Final-relation checkpoint: 1,162 full-suite tests passed in 482.70 s;
37 new targeted tests passed in 18.45 s. Full Ruff,
strict mypy on 86 source modules, five independent Node canonical vectors and
ten frontend tests passed. Wheel build/install, dependency check and isolated
out-of-checkout smoke passed. Source CLI, installed CLI and live HTTP return
identical whole verification envelopes and relation reports for the saved sphere;
all 12 relation assertions PASS, with digest
`38696d19aa220e844372305e2892c13ab5027bb8ffc0efcf060d0a01c333096a`.
Its V5 now has exactly deterministic_candidate_selection_and_tie_break and
physical_verification missing. Ten projects and sessions remain intact; English
PDF download passed. A Windows-1252-decoded prior HTTP capture was corrected
only for the read-only comparison; database and live UTF-8 steps were unchanged.
The historical hash-only sphere still returns search audit INDETERMINATE with
original_proposal_artifacts missing, no relation report and unchanged project.
Focused independent review found no concrete issue in the new auditor/API/V5
scope; it did not audit the baseline physical model or full release acceptance.
Logs and delivery comparisons are under `artifacts/backend-final-relation/`.
The first full-suite run was interrupted by new user input; its partial log is
retained separately. Only the complete rerun establishes the full-suite result.
No controlled speedup is claimed. Worker token/cost measurements remain null
in `artifacts/agent-costs/2026-10-06-final-relation.json`.

Explicit-coordinate checkpoint: all 1,217 full-suite tests passed in 534.76 s.
The first full run was stopped after an obsolete dispatch test treated the newly
supported 1.2 version as unknown; that ordinary registry test now asserts 1.2
acceptance and unknown 1.3 rejection. Frozen schemas/goldens remain unchanged.
Only the complete rerun establishes the full-suite result.
55 new focused tests and the adjacent-contract
regressions passed together (81 tests, 8.77 s). Full Ruff and strict mypy on
87 source modules passed. Five frozen Node canonical vectors, six additional
Python/Node coordinate/design hash comparisons and ten frontend tests passed.
Wheel build, clean isolated installation, dependency check and out-of-checkout
smoke passed; all nine registered schemas are bundled byte-for-byte. Six source
and installed CLI envelopes match exactly, including valid capped/nonmonotone
targets, crossing rejection, V0 evidence and structured generation NOT_APPLICABLE.
The old sphere target metadata and digest are unchanged.

After loading the new code locally, all ten saved projects and sessions matched
their pre-task captures exactly. The saved sphere retains V0 PASS, independent
search/final-relation PASS, V5 INDETERMINATE with exactly the same two missing
physical/selection checks, overall NOT_VERIFIED and physical UNTESTED. The legacy
hash-only sphere remains incomplete; PDF download passed. Comparisons use UTF-8
captures directly and do not edit storage. Evidence is under
`artifacts/backend-coordinate-target/`. Worker token/cost measurements remain
null in `artifacts/agent-costs/2026-10-06-coordinate-target.json`; no measured
speedup or physical acceptance is claimed.

Coordinate producer checkpoint: all 1,248 Python tests passed in 563.41 s.
The worker's 70 focused tests and the primary's 27 independent adversarial/property
tests passed. Full Ruff, strict mypy on 88 modules, five unchanged independent Node
canonical vectors and ten frontend tests passed. Wheel build, clean isolated
installation, dependency check and out-of-checkout smoke passed; all nine schemas
are bundled byte-for-byte. Three complete source/installed CLI generation envelopes
match: capped and nonmonotone targets emit proposals, while a crossing is rejected
without candidates or trace. Entire native-sphere and historical capped-cylinder
proposal/trace payloads match their pre-edit captures under fixed provenance.
These checks establish the documented producer subset, not independent coordinate
replay, V7 or physical pattern validity. Evidence is under
`artifacts/backend-coordinate-generation/`; worker usage measurements remain null
in `artifacts/agent-costs/2026-10-06-coordinate-generation.json`.

The restarted live source server preserved all ten original project snapshots
exactly. The complete-bundle sphere retains V0 PASS, search/final-relation PASS,
and V5 INDETERMINATE with the same two physical/selection checks missing. Its
PDF download passed; the historical hash-only sphere stays incomplete.
New explicit-coordinate pear (40 x 55 mm, hypothetical 25 stitches/28 rounds per
100 mm) generated 20 rounds and 354 stitches, with semantic validation and text
round trip PASS, ideal-target V0 PASS, coordinate search audit/V5 INDETERMINATE,
overall NOT_VERIFIED and physical UNTESTED. Its complete bundle was retrieved
unchanged, and the English PDF downloaded successfully (5,508 bytes):
`6e098e81d5559506896b3ed2f38399f0248c8ee43478a87ca922d3d23061e200`.
This project records the source snapshot before checkpoint publication; do not
rewrite its historical commit/dirty-source provenance after committing.

The first live attempt reached an old Windows background process and its schema
assertion failed. After stopping the verified owned process pairs and checking
listener ownership, the complete live checks passed against new source. The
extra legacy pear created during that diagnostic is retained unchanged, alongside
the ten original projects and new coordinate pear (12 saved projects total).
Failure diagnostics and both PDFs remain in the ignored evidence folder.

Start from repository root: `.venv/Scripts/python.exe -u tools/run_prototype.py --port 8765`.
On Windows, stopping the terminal session alone may leave its Python child alive.
Before restart, identify only this checkout's prototype launcher/child process
pair, stop that owned pair and confirm port 8765 has no listener. After restart,
 confirm exactly one listener belongs to the new process. A printed listening
 message alone does not prove that browser requests reach the new source.
At the current checkpoint, a server started inside the restricted execution
environment printed its listening message but timed out on loopback requests.
After stopping its verified owned launcher/child pair and confirming the port
was free, starting the same command outside that restriction restored access.
No firewall or global security configuration was changed. Retain the distinct
failed-start diagnostics; do not count the listening message as successful QA.
Persistent private projects/feedback: `artifacts/local-prototype/` (ignored).
Nine historical projects existed before the complete snapshot task; their sessions
are preserved (eight untraced projects and one hash-only traced sphere).
Ten projects were saved after the complete-bundle sphere checkpoint; the current
coordinate producer checkpoint has 12, as described above.
Generated PDFs under `output/pdf/` are local exports, not authoritative fixtures.
Do not infer installed runtime or remote branch state from this note; check live.

## Next work in order

1. Extend the closed-shaped model with explicitly declared shaped shear/bending,
   calibrated closure yarn/cap and open-fixture mechanics, contact response and
   optimization path safety. Ring/CLOSE tension, pressure and bounded Armijo now
   have an experimental producer; retain target-free execution and calibrate its
   hypotheses independently. No complete physical F0 or V6 acceptance yet.
2. Implement independent V6 convergence, V7 geometry comparison, V8 material
   robustness and feasible-candidate selection, then V10 bound provenance.
   V7 sampling must bind its own coverage/error policy; coordinate search proof
   does not establish physical geometry accuracy.
3. Complete numerical-failure trace acceptance beyond the explicitly incomplete
   reached-stage scope, uncertainty/calibration provenance, broader topology/solver domains,
   M1B/full export acceptance, recovery/security/release acceptance. See the full
   roadmap; this list does not waive any package acceptance requirement.
   Older r(s) profiles remain ambiguous and saved projects must not be rewritten.
4. Collect real crochet feedback/specimen measurements. Human physical trials and
   new golden approvals are separate gates. Develop the separate mobile app later.

## Reading and commands

Contracts: `BACKEND_IMPLEMENTATION_ROADMAP.md`, `BACKEND_ACCEPTANCE_PLAN.md`,
`FORWARD_CLOSED_MECHANICS_V1.md`, `FORWARD_SHAPED_ELASTIC_V1.md`,
`FORWARD_MODEL.md`, `MATERIAL_MODEL.md`,
`ANALYTIC_COORDINATE_TARGET_V1.md`, `DESIGN_SPEC.md`,
`ANALYTIC_COORDINATE_GENERATION_V1.md`,
`ANALYTIC_COORDINATE_REPLAY_V1.md`,
`ANALYTIC_SEARCH_TRACE_V1.md`, `ANALYTIC_CANDIDATE_CLAIMS_V1.md`,
`PROTOTYPE_PROPOSAL_BUNDLE_V1.md`, `PROTOTYPE_FINAL_RELATION_AUDIT_V1.md`,
`VERIFICATION_PIPELINE.md`, then the affected
subsystem contract/skill.

Quality: `.venv/Scripts/python.exe -m pytest -q`,
`.venv/Scripts/python.exe -m ruff check src tests tools`,
`.venv/Scripts/python.exe -m mypy src`, `git diff --check`.
Node: `tools/canonical_reference.mjs tests/conformance/canonical-vectors.json`
and `tools/prototype_frontend_tests.mjs`.
CLI: `python -m crochet_ai.cli --json request --request-file <request.json>`.
Generation requests additionally need the global `--software-commit` argument
set to the actual checkout revision, and run limits within DesignSpec limits.
Unsupported generation returns structured NOT_APPLICABLE with CLI exit code 3;
target inspection errors use exit code 2. Do not weaken admission to test delivery.
Build/install evidence and cost notes live under ignored `artifacts/`; missing
worker token/cost measurements remain null. Never report software tests as
physical proof or call the complete backend finished from this checkpoint.

## Faster continuation without reducing acceptance

Prioritize R1 end-to-end completion; R2/R3 remain promised later scopes. Bundle
one coherent acceptance package per checkpoint, including API/persistence/status
integration, rather than serial small producer-only changes. Independent count
and phase replay implementations were developed concurrently; primary owned
the envelope, API integration and critical review. Use at most the documented
bounded worker count and keep generation/independent verification separate.

Run each worker's targeted oracle tests, then one complete suite at integration.
Run Ruff/mypy/Node independently in parallel; installed-wheel checks verify the
delivered package. Full-suite `--durations=15` evidence is retained under ignored
`artifacts/backend-trace-audit/pytest-full.log`. Optimize measured hotspots next;
do not add test parallelism or cross-module shared mutable fixtures without
evidence. Physical measurement work can proceed alongside software completion,
but must use real specimens and cannot be inferred from software checks.

Measured suite hotspots include prototype trace/legacy persistence (37.87 s),
V5 proof-budget routing (26.70-27.45 s) and shape generation (up to 26.30 s).
These remain required checks. Investigate repeated generation/validation before
sharing fixtures or adding parallel pytest execution. The initial local pip
installer continued consuming CPU after its successful-install message; that
owned helper was stopped after installed-package verification. A local-only
wheel invocation with --no-index/--no-deps and --disable-pip-version-check plus
dependency check finished in 4.04 s. This is a per-command release-check choice,
not a global pip, cache, credential or security configuration change. The full
suite timing is not a controlled before/after speed comparison. Worker token and
cost measurements were unavailable and remain null in ignored agent-cost notes.

Read-only cProfile evidence for one saved 40 mm sphere verification is retained
under `artifacts/backend-proposal-persistence/`. It recorded 171.6 million calls
and 66.06 s with profiler overhead: schema validation 57.54 s cumulative,
21 IR validations 54.87 s, V9 42.42 s, three semantic round trips 34.57 s.
Cumulative timings overlap and are not additive, nor a production benchmark.
Repeated schema/IR validation is a measured next optimization target. Use a
separate task with immutable, request-owned validated contexts and preserve
independent input admission; never share mutable user inputs across boundaries.
No verifier optimization or measured speedup is claimed in this checkpoint.
