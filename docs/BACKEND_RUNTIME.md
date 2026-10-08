# Local backend runtime 1.0

Status: implemented research subset, not a complete backend release. No output
of this runtime is physically verified. The facade is transport-independent;
there is no HTTP listener, account system, remote service, or frontend dependency.

## Install and inspect

Use Python 3.11 or later and an isolated environment. From the repository:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\Activate.ps1
crochet-ai --help
crochet-ai --json doctor
crochet-ai --json capabilities
```

Do not recreate an environment that contains unrelated work. Installation needs
the declared build/runtime dependencies; offline builds require those packages
already available. Built wheels include the authoritative schemas and locate
them independently of the current working directory. No global PATH or Codex
model configuration is changed by this package.

## JSON contract

All commands emit a versioned JSON envelope. `--json` selects compact output.
Success is `{"api_version":"1.0.0","ok":true,"data":{...}}`; errors have
`ok:false` and `error:{code,reason}`, optionally structured diagnostics. Help
is ordinary CLI help, not a JSON response. `ok` means the operation was handled;
it does not imply feasibility, verification, or physical accuracy.

The raw request shape is closed and rejects unknown fields. Limits are 2 MB,
100,000 JSON nodes and depth 64. Duplicate keys, unsafe integers, non-finite
numbers and invalid Unicode fail. No request may supply server provenance,
filesystem paths to follow, executable code or URLs to retrieve.

| Operation | Required payload in addition to api_version/operation |
| --- | --- |
| capabilities | none |
| generate_analytic | design_spec, material_profile, run_config |
| validate_ir | design_spec, material_profile, crochet_ir |
| export_ir | design_spec, material_profile, crochet_ir, terminology |
| run_forward_prototype | design_spec, material_profile, crochet_ir, forward_run |
| inspect_mesh_openings | design_spec, material_profile, mesh_json |
| inspect_analytic_target | design_spec, material_profile |
| inspect_closed_surface_topology | design_spec, material_profile, crochet_ir |
| inspect_closed_cell_conformance | design_spec, material_profile, crochet_ir |
| inspect_analytic_candidate_claims | design_spec, material_profile, crochet_ir |
| inspect_analytic_search_trace | design_spec, material_profile, run_config, search_trace, candidate_proposals |
| inspect_prototype_final_relation | design_spec, material_profile, original_proposal, crochet_ir |

`inspect_analytic_target` also accepts DesignSpec 1.2 explicit radius/axial
profiles through [ANALYTIC_COORDINATE_TARGET_V1](ANALYTIC_COORDINATE_TARGET_V1.md).
It returns source-bound immutable ideal-surface metadata after bounded exact
meridian admission. Existing sphere/ellipsoid metadata is unchanged; ambiguous
older radial profiles remain unsupported. Closed explicit caps and simple
nonmonotone meridians are supported with cardinal axes; unsupported frames and
boundaries return structured errors. Generation from this representation follows
[EXPLICIT_COORDINATE_MERIDIAN_V1](ANALYTIC_COORDINATE_GENERATION_V1.md);
the separate [coordinate replay](ANALYTIC_COORDINATE_REPLAY_V1.md) supports the
documented numerical/search subset. V7 target sampling/comparison remains open. Inspection alone
retains NOT_VERIFIED/UNTESTED. CLI request and isolated durable jobs use the same
operation; no client-supplied proof or work-budget override is accepted.

`inspect_closed_surface_topology` constructs the server-owned target-free closed
SC cells, then independently audits their combinatorial topology and checks the
source stitch-to-face mapping. `inspect_closed_cell_conformance` returns the same
two proofs under `surface_topology` and `cell_conformance`, each with its hash.
A proof `PASS` is a partial computational result; pattern status remains `NOT_VERIFIED`
and physical status `UNTESTED`. A defective surface or mapping gives `REJECTED`. Faces,
budgets, hashes and claimed evidence cannot be submitted by clients. See
[`SURFACE_TOPOLOGY_AUDIT_V1.md`](SURFACE_TOPOLOGY_AUDIT_V1.md) and
[`CLOSED_CELL_CONFORMANCE_V1.md`](CLOSED_CELL_CONFORMANCE_V1.md). The generic `request`
CLI and durable jobs expose the same operation.

`inspect_analytic_candidate_claims` returns an independent `candidate_claims`
payload and `candidate_claims_sha256`. It derives schedule/construction quantities
from validated raw IR and checks recorded parameter claims, not solver flags.
Missing complete search evidence retains `INDETERMINATE` and NOT_VERIFIED/UNTESTED;
known false claims yield FAIL and REJECTED. Clients cannot submit claimed proof,
external traces or budgets. See [ANALYTIC_CANDIDATE_CLAIMS_V1.md](ANALYTIC_CANDIDATE_CLAIMS_V1.md).
The generic CLI request and durable job paths expose the same operation.

`inspect_analytic_search_trace` independently replays the complete bounded staged
sphere/equal-axis-ellipsoid search, exact count windows, DP objectives/ties,
interrupted layers and global work/prefix accounting. Complete original proposal
IR artifacts bind the raw schedules and declared provenance. Its immutable
domain-hashed report is retained by V5 when supplied through optional
`search_evidence={run_config,search_trace,candidate_proposals}` on `verify_candidate`.
The standalone operation returns the report payload. No client proof-budget
override is accepted. Missing proposal artifacts or unsupported samplers retain
INDETERMINATE; contradictions FAIL. Source authentication, physical selection and
full backend acceptance remain open. See [ANALYTIC_TRACE_AUDIT_V1.md](ANALYTIC_TRACE_AUDIT_V1.md).

`generate_analytic` additionally returns `search_trace` and `search_trace_sha256`
under [ANALYTIC_SEARCH_TRACE_V1.md](ANALYTIC_SEARCH_TRACE_V1.md). They are null for
unadmitted runs and present for admitted terminal outcomes, including partial
batch exhaustion. The trace binds inputs and records actual producer execution;
it is not independent verification. New prototype projects persist this trace
and a hashed `PROTOTYPE_GENERATION_LINK_V1` proposal-to-final phase-policy link.
Legacy stored projects remain unchanged. V5 can now independently replay these
untrusted traces through the optional search_evidence extension above.

New local projects additionally retain complete original CrochetIR proposals
in [PROTOTYPE_PROPOSAL_BUNDLE_V1](PROTOTYPE_PROPOSAL_BUNDLE_V1.md). The existing
project transaction and storage limits include the bundle. The prototype verify
route admits its hashes/bindings and sends original proposals to the unchanged
auditor, without regenerating historical evidence. Missing legacy artifacts stay
incomplete; partially present or corrupted bundles fail explicitly. Complete new
sphere traces can pass the scoped audit. The separate
[final-relation auditor](PROTOTYPE_FINAL_RELATION_AUDIT_V1.md) compares complete
native and final IRs, including actual ordered connections and anchor updates.
Its standalone operation accepts the four artifacts above and returns an
immutable, input-bound report. V5 invokes it only after search audit PASS and a
unique native provenance match. Relation PASS removes only that missing check;
physical selection and full V5 acceptance remain open. Legacy hash-only projects
stay incomplete. API transport limits remain unchanged.

`inspect_mesh_openings` is an additive diagnostic capability within the 1.0
envelope, not generation or mesh acceptance. `mesh_json` contains the exact UTF-8
source text; its bytes must match the DesignSpec digest, media type and frame.
The supplied material must match the inline or referenced binding. No asset URI
is followed. Server-owned inspection limits are 262,144 mesh bytes, 128 vertices,
256 faces, 16 openings, 64 retained-opening landmark references, 32 referenced
landmarks, 8,128 vertex pairs and 16,384 landmark-edge tests. Clients cannot
override these limits. A handled ambiguous/unmatched mapping can have `ok:true`;
inspect `diagnostic.classification`. Every result still reports
`mesh_preflight_state:INDETERMINATE`, `verification_state:NOT_VERIFIED` and
`physical_status:UNTESTED`. The existing local queue can execute and persist this
operation without new storage formats.

`terminology` is `US_EN`, `UK_EN` or `DE_DE`. The complete strict run configuration is
defined by `AnalyticRunConfig` in `src/crochet_ai/analytic_solver.py`, with nested
`numerics`, `count_budget`, `placement_budget` objects. The shaping separation
is a rational string such as `1/12`. All fields are required; there are no
implicit production tolerances. `tests/test_backend_api.py` constructs executable
generation/validation/export requests from independent synthetic fixtures.

```powershell
crochet-ai --json request --request-file capabilities-request.json
crochet-ai --json --software-commit <actual-git-sha> generate --request-file generate-request.json
crochet-ai --json validate --request-file validate-request.json
crochet-ai --json export --request-file export-request.json
```

The capabilities request file contains exactly:
`{"api_version":"1.0.0","operation":"capabilities"}`.
Each other file contains the complete request from the table, not just an IR.
Exit codes: 0 handled successfully, 2 invalid request/storage error, 3 handled
generation outcome other than `CANDIDATES_EMITTED`. Inspect the status even if
the response includes candidates: exhausted batches retain complete candidates.

The supplied commit is a caller assertion, not independently authenticated Git
provenance. The CLI separately hashes its installed Python sources and schemas
and records runtime versions. It marks checkout status `UNCONFIRMED`. Missing
commit identity prevents generation before search. This is not V10 certification.

## Experimental forward execution

`run_forward_prototype` connects existing target-free forward components under
`FORWARD_STRETCH_SHEAR_BENDING_PIPELINE_V1`. The closed request, explicit
hypothesis parameters, operational work limits and result rules are specified
in [FORWARD_PIPELINE_V1.md](FORWARD_PIPELINE_V1.md). It is available through the
generic `request --request-file` command and the existing durable local queue.

The supported construction is narrower than the analytic generator: only the
admitted plain aligned cyclic quad strip can enter this experimental surface
path. Unsupported shaping, phases or construction are rejected. The wrapper
does not synthesize ring/closure caps, seams, pressure or contact forces.

Only a balanced combined optimizer result with no forbidden final triangle
intersections may expose coordinates, with role `EXPERIMENTAL_DEBUG_ONLY`.
Failure or exhaustion exposes no geometry. The full result remains
`verification_state:NOT_VERIFIED`, `physical_status:UNTESTED`, and
`v6_outcome:NOT_RUN`. Handling a request or returning illustrative coordinates
does not establish converged F0, V6, calibrated shape accuracy or release.

## Analytic proposal policy

`analytic-closed-sc/1` supports a single yarn/color, non-branching closed-pole
cyclic SC construction starting in a magic ring and ending in CLOSE. Sphere,
ellipsoid and eligible radial profiles, including admitted DesignSpec 1.2
radius/axial meridians, are decoded. Cylinder/cone
meridional samplers exist, but their open/interface construction is not emitted.
Mesh fitting, branching, garments, flat work and lace remain separate packages.

For every explicitly bounded integer course count, jointly place all course
centres at `(2i+1)/(2M)` along the meridian. Record `L/M - course_pitch` in mm.
Find the globally optimal count schedule under the exact two-pass count
objective. For that fixed schedule, search all permitted balanced cyclic
rotations using a one-previous-course history. Minimize exact stacked shaping
pairs, then total shortfall from the configured separation in turns, then phase
sequence. Separation is a soft proposal objective, not a passed hard gate.

This staged count-then-phase policy is **not** a jointly global count/placement
optimum and is not the final V5-V8 candidate-selection policy. Counts, course
hypotheses, transitions, angle pairs, emitted candidates and stitch applications
have explicit caps. Count and placement work is shared across hypotheses.
Exhaustion is distinct from bounded infeasibility. No partial IR is published.

Elliptic arc integration uses monotone endpoint rectangle bounds in exact
arithmetic and an explicit caller-owned binary64 roundoff allowance. It is not
certified interval arithmetic. Arc tolerance and allowance are in mm; the
radius-zero tolerance is also in mm. Their owner is the selected numerical
profile, requiring convergence/scale studies before a production claim. Radial
profiles with `abs(dr) > ds`, nonzero closed poles, or interior zero-radius poles
fail instead of being repaired. `r(s)` does not determine the sign of axial
motion; this runtime does not invent an axial embedding from it.

Explicit coordinate generation uses exact rational cumulative approximate lengths
and normalized interpolation. Each segment has a bounded square-root enclosure
checked against the exact squared input distance; total length and per-output
roundoff must meet the caller's numerical policy. max_arc_panels counts segments
for this algorithm. Finite overflow, failed enclosures or excessive rounding yield
NUMERICAL_FAILURE, while insufficient segment budget yields SEARCH_BUDGET_EXHAUSTED.
Sampler version and diagnostics are recorded in coordinate-only proposal
provenance and bound by retained source/target/trace hashes. These producer
calculations are checked by the separate coordinate replay; they do not complete
V7, physical selection, calibration or full backend acceptance.

## Durable local jobs

### Closed shaped elastic preparation

`inspect_shaped_forward_model` adds a target-free initial elastic diagnostic for
closed SC bodies with binary shaping and MAGIC_RING/CLOSE. Supply the exact
versioned [recipe](FORWARD_SHAPED_ELASTIC_V1.md); the backend does not invent
mechanical constants from the viewer or MaterialProfile gauge. The existing
API/CLI request and isolated-job paths return the same deterministic bundle.
Limits: one initialization, 2,048 vertices, 4,096 faces, 8,192 spring terms;
lower declared vertex budgets are enforced before coordinate output. Unknown
fields/versions and target/coordinate overrides fail closed. Numeric force
failure returns E_FORWARD_DIVERGED with no geometry bundle.

The bundle is EXPERIMENTAL_INITIAL_ELASTIC_DIAGNOSTIC, comparison_eligible=false,
NOT_VERIFIED / UNTESTED with V6 NOT_RUN. This is preparation and initial-force
evaluation only; closure mechanics, shaped shear/bending, loading/contact
response, optimization and calibration remain incomplete. The older plain-strip
run_forward_prototype contract and verification-gate adapters are unchanged.

```powershell
crochet-ai --json jobs submit --db jobs.sqlite --request-file generate-request.json --idempotency-key request-001 --dry-run
crochet-ai --json jobs submit --db jobs.sqlite --request-file generate-request.json --idempotency-key request-001
crochet-ai --json --software-commit <actual-git-sha> jobs run-next --db jobs.sqlite --watchdog-seconds 60
crochet-ai --json jobs list --db jobs.sqlite --limit 20 --offset 0
crochet-ai --json jobs get --db jobs.sqlite <job-id>
crochet-ai --json jobs cancel --db jobs.sqlite <job-id>
```

Dry-run validates bounded JSON and reports its digest; it does not run the
operation or claim semantic validity. Submission atomically stores canonical
request bytes. A repeated key with the same canonical request returns the same
job; different content conflicts. Workers claim jobs transactionally and publish
complete result bytes, digest and terminal state together. Result hashes detect
accidental modification, not an attacker who can rewrite the entire database.

QUEUED becomes RUNNING and then SUCCEEDED or FAILED. Cancellation turns queued
jobs directly into CANCELLED; running jobs pass through CANCEL_REQUESTED and
suppress publication. Expired running leases become FAILED, never silently
retried. A cancelled expired lease becomes CANCELLED. Workers recover expired
leases when executing the next queue step. SUCCEEDED means API execution
succeeded; inspect embedded generation and verification status separately.

The CLI uses a spawned process and wall-clock watchdog. Timeout, process-start
failure and child termination produce explicit job failure. Malformed or
excessively nested child IPC responses also fail the job immediately with a
generic internal error; their bytes are not published. The watchdog is an
operational limit, not a deterministic solver proof. Defaults: 1,000 jobs,
256 MB aggregate request/result payload, 32 MB per result, 300-second lease.
SQLite page overhead is not covered by the payload quota. No disk-full guarantee,
OS memory sandbox, retention policy, multi-user authorization, encryption,
distributed scheduling or deployment hardening is claimed. Protect database
files using OS access control and do not expose this runtime to remote clients.

## Independent physical boundary

`PhysicalSemanticProjection` validates source IR/material admission and then
copies only explicitly allowlisted physical fields. Its immutable canonical
bytes/hash contain no DesignSpec reference, IR hash, solver derivations,
provenance, seed, target-role artifacts, colors or display labels. The admission
validator is not retained by the projection. Set tables are normalized; actual
event/course/frontier order is preserved. Stable source graph labels remain.

Currently only closed, single-yarn, non-branching cyclic SC with MAGIC_RING and
CLOSE is admitted. Unknown/unsupported construction and mismatched material
bindings fail. `lower_forward_graph` accepts only that projection and the
matching, semantically validated MaterialProfile. It requires an exact response
for every stitch's family, course form, requested tension profile and fabric
state; missing or ambiguous responses fail. The immutable topology-only result
contains attachment labels, course/wale incidence, shaping groups, declared
yarn-path stitch links, ordered MAGIC_RING/CLOSE operation records, their exact
creation/closure attachment sets, and separate stitch/course pitch values and
uncertainty. The closure set is checked against the retired input frontier;
multi-site ring anchors remain one ring operation, not multiple rings.
Incidence edges are not calibrated springs, and this is not geometric simulation,
convergence or proof of physical realizability. Graph support remains limited
to the projection's narrow admitted domain; the graph itself does not implement
physical closure mechanics, loading, energy, contact or optimization. Later
prototype stages below add only restricted stretch diagnostics. Further stages
must accept only this projection plus resolved material/loading/model inputs,
never the enclosing source IR. Shared semantic validation and JCS are
common-mode risks; adversarial fixtures are authored without solver helpers.

`admit_forward_inputs` is a separate, strict configuration-admission prototype.
It accepts only explicitly unloaded/unpressurized loading and a provenance-bound
`HYPOTHESIS` with separate positive course/wale stiffness coefficients in N/mm.
All five F0-contract work budgets and six versioned, unit-labelled tolerances
are mandatory; the prototype additionally requires `max_initialization_vertices`
and `max_line_search_trials` as separate positive work limits. Unknown fields
and target/embedding payloads fail. Its domain-separated hash
binds the admitted loading, model and config content, but no cache or V6 outcome
uses it yet. The model version is `F0_STRETCH_PROTOTYPE`, deliberately not a claim
of complete F0: the core profile remains stretch-only, while the separately
versioned shear and bending hypotheses below are experimental. Contact,
pressure and boundary mechanics remain unimplemented, and neither coefficients nor
thresholds are physically calibrated.

`prepare_stretch_terms` uses the admitted graph and hypothesis inputs to build
only experiment-labelled COURSE springs and unambiguous plain 1:1 TOP_LOOP-to-
TOP_LOOP WALE springs. It uses stitch pitch and course pitch separately and
records projection, material and input hashes. Ring-anchor wale incidences are
checked but omitted: interior course pitch is not silently transferred to the
ring. Shaping is rejected until a calibrated group rule exists. A private helper
checks the spring-energy formula on synthetic coordinates; the complete F0
optimizer, collision model and V6 geometry are not implemented.

`initialize_forward_graph` now provides the target-independent experimental
start state for plain cyclic SC courses with at least three tops per course.
All start sites of the one declared magic ring share an origin while retaining
their operation-declared order. Each course uses a regular polygon with chord
equal to its exactly selected stitch pitch; the first course starts at z=0,
later courses advance axially by their exactly selected course pitch. This
axial increment is not an assertion about 3D wale-edge length. Mixed/unknown
pitch, shaping, inconsistent adjacent work directions, any non-ordinal or
non-bijective previous-course base mapping, non-finite geometry and vertex-budget
exhaustion fail. A positive course pitch must also produce a finite, strictly
larger represented axial coordinate; sub-ULP stagnation and overflow fail.
This is a reproducible heuristic starting coordinate set,
not a predicted shape, energy minimum, or V6 pass.

`evaluate_initial_stretch_forces` now evaluates only those prepared terms at
that initial state. It verifies matching projection/material/input identities
and initialization content integrity, then reports deterministic experimental
spring energy (N mm), negative-gradient nodal forces (N), and the maximum force.
Undefined zero-distance directions, missing endpoints, invalid coefficients
and non-finite arithmetic fail. This is a diagnostic, not an optimizer,
collision check, converged forward geometry or V6 evidence.

`relax_one_stretch_step` attempts one bounded, deterministic stretch-only
gradient step from the target-free initializer. It uses a recorded initial
step in mm/N, fixed versioned Armijo decrease and half-step backtracking;
baseline and rejected trials consume explicit evaluation/trial budgets. It
returns distinct experimental acceptance, initial-stationarity, budget,
line-search and numerical-failure statuses with hashes and counters. A failed
step publishes no accepted coordinates. This is not a full optimization run,
contact/bending/shear simulation or V6 `CONVERGED` outcome. The line-search
control-flow test uses an injected finite rejection; it is not evidence that
such a rejection occurs naturally for the current spring fixtures.

`optimize_stretch_prototype` now repeats that step with global iteration and
energy-evaluation limits and a per-step line-search limit. Its deterministic
trace binds the exact initialization hash, projection, material and admitted
inputs. Only force balance of the admitted stretch terms can produce
`EXPERIMENTAL_FORCE_BALANCED`; exhausted, failed or numerically invalid runs
publish no final coordinates. This status does not check the full F0 energy,
topology geometry, collisions or physical accuracy and cannot pass V6.

`admit_shear_parameters` accepts an explicit `HYPOTHESIS` stiffness in N mm,
rest-angle cosine and provenance. `prepare_shear_terms` first rechecks the
complete supported plain 1:1 open-strip topology, then binds one term to each
canonical quad cell with hashes for the cells, parameters, material, projection
and run inputs. `evaluate_shear_terms` evaluates the cosine-angle energy and
analytic negative-gradient forces; singular edges and non-finite arithmetic
fail explicitly. The separate `optimize_stretch_shear_prototype` combines this
energy with the existing stretch terms under global iteration and evaluation
limits, records both term identities and the numerical step rule, and can only
return an experimental force-balance status. Its result can feed the exact
final-coordinate contact diagnostic, which still does not grant V6 or physical
clearance. Rest angle, shear stiffness and contact behavior need external
calibration before physical claims.

`admit_bending_parameters` requires an explicit `HYPOTHESIS` rest dihedral in
radians, bending stiffness in N mm and source provenance. The initializer does
not supply a physical rest angle. `prepare_bending_terms` binds these parameters
to canonical quad diagonals, topology, initialization, material and inputs.
`evaluate_bending_terms` evaluates a wrapped dihedral energy and its
negative-gradient nodal forces. Degenerate or excessively skinny faces and
ambiguous angle branches fail explicitly. The scale-aware quality limit and
arithmetic guards are versioned prototype numerical policy, not calibrated
crochet tolerances. `optimize_stretch_shear_bending_prototype` combines all
three terms with bounded Armijo descent, recording each term identity and
the numerical rule. A force-balanced result can feed the exact final-coordinate
contact diagnostic, but does not establish physical clearance or V6. Rest
dihedral, stiffness and contact response need external calibration.

`build_forward_surface_cells` derives a target-free, coordinate-free open quad
strip only between consecutive plain 1:1 cyclic SC courses. It checks exact
course/event order, graph node and edge coverage, previous-course base ownership,
bijective wale correspondence, a consistent course direction and exact ordinal
phase. Ambiguous rotations, reversals, shaping, missing/duplicate links and
courses with fewer than three loops fail. The result records both open boundary
loops and a projection/material-bound canonical hash. Neither MAGIC_RING nor
CLOSE supplies a geometric cap here; the cells are not a watertight mesh,
contact result, signed-volume model or V6 evidence.

`triangulate_forward_surface_cells` deterministically splits each admitted
quad along its declared first-to-third-vertex diagonal. It checks the exact
source artifact bytes/hash and fields, cell/course ordering, disjoint course
vertex sets, opposite directed incidence on interior edges, the two declared
boundary loops, connectivity and Euler characteristic zero. The result is an
open combinatorial triangulation, not an embedding: triangle area, normal
quality, self-intersection and physical contact have not been checked.

`diagnose_initial_triangle_geometry` now measures each ordered triangle at the
target-free experimental initializer coordinates. It rechecks the exact source
triangulation and initialization hashes/fields, matching projection/material,
coordinate uniqueness and finite arithmetic. The result reports represented
area in mm² and a scale-free triangle shape value; exact zero area, undefined
or unrepresentable arithmetic fail. It applies no uncalibrated near-degeneracy
threshold. Positive reported area is only an arithmetic diagnostic, not robust
embedding validity, contact clearance, outward orientation or V6 evidence.
An integration regression exercises a semantically validated, compiled
three-course plain-SC CrochetIR through projection, graph lowering, input
admission, initialization, open cells, triangulation and this diagnostic. A
valid phase-shifted construction is rejected by the narrow surface-cell
profile rather than silently rotated into it.

`diagnose_initial_aabb_candidates` now exhaustively compares the inclusive
axis-aligned bounds of every unordered pair of source-ordered triangles at the
same initial coordinates. Global face ordinals disambiguate the per-cell
triangle indices. The admitted `max_contact_pairs_evaluated` budget bounds the
*total* AABB comparisons, including non-overlaps; an insufficient budget fails
before a partial result is emitted. Candidates retain topologically adjacent
faces and their shared-location count. The diagnostic is bound to the exact
source triangulation, initialization and forward-input hashes. Its
`CANDIDATES_ONLY` status never establishes triangle intersection, penetration,
collision freedom, contact response, converged geometry or V6. It introduces
no contact tolerance and does not borrow V0 target-mesh thresholds.
The AABB and exact-intersection stages share provenance validation with the
area diagnostic but do not require its binary64 mm² metric to be representable;
finite coordinate scales with underflowing or overflowing area remain eligible
for the exact intersection-only calculation if the triangles are exactly
nondegenerate.

`diagnose_initial_exact_intersections` recomputes that candidate set and checks
each pair using exact rational arithmetic on the represented binary64 initial
coordinates. It rejects exact-zero-area triangles and records intersections
beyond an intended shared vertex or edge, including coplanar folded overlaps.
Its artifact is bound to the source, initialization, inputs and broadphase.
`EXACT_INTERSECTION_DIAGNOSTIC_ONLY` is the status even if no forbidden pair is
found. Disjoint AABBs may still be closer than a physical contact threshold;
the routine does not measure distance, thickness or penetration, provide
contact forces, prove collision freedom, or satisfy V0/V6. The V0
`NUMERICAL_GEOMETRY` near-contact tolerance is not applied to this F0
experimental prototype.

`diagnose_initial_exact_distances` separately examines every unordered
source-face pair, including pairs whose AABBs do not overlap. It excludes only
faces sharing an attachment-location ID, checks the admitted pair budget before
emitting a result, and reports the minimum nonadjacent squared distance in
mm² as reduced rational numerator/denominator strings. A face intersection
has exact squared distance zero. If there is no nonadjacent pair, the minimum
is explicitly null. The result and stable minimizing face pairs are bound to
the source, initialization and forward-input hashes. This is a
`DISTANCE_DIAGNOSTIC_ONLY` measurement of initial coordinates: it supplies no
calibrated contact threshold, fabric thickness, force, clearance certificate,
convergence or V6 outcome. The V0 near-contact profile is a separate contract.

`diagnose_final_exact_self_contact` repeats the exhaustive exact-intersection
classification on the coordinates of a provenance-bound
`EXPERIMENTAL_FORCE_BALANCED` optimizer artifact. It revalidates the source
triangulation, optimizer bytes and hash, coordinate domain, and the complete
unordered face-pair budget before testing contact beyond shared vertices or
edges. It also records the exact minimum squared distance in mm² among faces
without shared attachment locations, with every minimizing pair. Its result is
`FINAL_COORDINATE_SELF_CONTACT_DIAGNOSTIC_ONLY`, including when no forbidden
intersection is found. Without a calibrated thickness or contact policy, the
distance cannot establish near-contact clearance. The diagnostic does not
measure penetration, provide contact response, or establish F0/V6 convergence
or physical clearance.

## Target mesh decode-only boundary

`decode_indexed_triangle_mesh` accepts immutable raw bytes under the explicit
`application/vnd.crochet.indexed-triangle-mesh+json` media type, an expected
DesignSpec coordinate-frame ID, and positive byte/vertex/face budgets. The
registered `IndexedTriangleMeshV1` Draft 2020-12 schema and I-JSON parser
reject duplicate names, unsupported units/handedness, non-finite or unsafe
numbers and unknown fields. The adapter additionally checks in-range,
non-repeated zero-based face indices. It returns immutable ordered vertices
and faces, the raw-byte SHA-256, parser identity and identity source-index maps.
Its status is `DECODED_ONLY`: no geometry-valid normalized mesh hash or V0 pass
exists yet. `diagnose_indexed_triangle_mesh` re-decodes the raw source and
compares the complete immutable decoded record before inspecting exact index
topology. Its versioned, content-bound `EXACT_TOPOLOGY_DIAGNOSTIC_ONLY` report
records duplicate and isolated elements, edge incidence, face components,
boundary loops, winding, orientability and vertex-link failures. A nonmanifold
edge leaves orientability unknown rather than claiming a result. The loop
tuples identify undirected cycles in deterministic order, not
face-induced boundary winding. Indices and the diagnostic hash are source-order
dependent until a separately validated canonical normalization exists.
`diagnose_indexed_triangle_mesh_exact_geometry` likewise revalidates the raw
source and reports exact coordinate-equal vertex groups and exactly zero-area
faces using binary64 values interpreted as rationals. This diagnostic cannot
decide near-zero area or numerical coincidence.
`diagnose_indexed_triangle_mesh_diameter` computes the exact squared mesh
vertex diameter as a reduced mm² rational over every identity pair after
prechecking the entire pair budget. Its maximizing pairs and zero-diameter
case are diagnostic only; it does not certify a positive numerical-profile
scale or compute a floating square root. Contact, profile thresholds, boundary
matching and permitted normalization remain separate unimplemented V0 checks.
No OBJ, STL or other source-format inference is offered by this adapter.

`resolve_v0_numeric_profile` loads the single documented
`v0_num_mesh_binary64_v1` record from immutable bytes (or the bundled source
record), validates its closed schema and I-JSON form, and requires the frozen
domain-separated record hash before returning typed thresholds. The build
copies the authoritative root profile into the package, with an out-of-checkout
resolution smoke test. This establishes profile identity only: no numerical
predicate, mesh certification or V0 pass follows from loading it.

`diagnose_indexed_triangle_mesh_relative_thresholds` applies only the
profile's inclusive `2^-40` relative doubled-area and distinct-coordinate
distance boundaries. It computes the exact squared vertex diameter and
compares rational squares, so threshold equality and extreme representable
binary64 scales need no floating square root or guessed epsilon. It checks
the complete two-pass vertex-pair budget before quadratic work and records
the source/profile hashes, predicate backend and exact findings. Exact
coordinate-equal groups and exactly zero-area faces are reported separately;
the near-zero face set also contains exact-zero faces because they satisfy the
inclusive threshold. Zero scale fails closed. The report remains diagnostic
only: it does not implement contact, volume, robust orientation/coplanarity,
boundary assignment or V0 acceptance.

`diagnose_indexed_triangle_mesh_signed_six_volume` accepts only fully closed,
exactly manifold, consistently wound topology with no other topology issues;
the source, topology report and numerical profile are revalidated. It computes
translation-invariant algebraic signed six-volume for each face-connected
component using exact binary64 rationals, and compares the profile's strict
`2^-36` stability limit against the exact mesh diameter. Equality is
indeterminate, not a sign decision. The report records a stable algebraic sign
or indeterminacy but leaves self-intersection unresolved, performs no winding
reversal and makes no outward-orientation or V0-pass claim.
This pre-normalization report uses decoded source indices for its reference
vertex and face order, so its diagnostic hash is source-order dependent. Final
V0 evidence still requires the contract's canonical mesh ordering and maps.

An isolated `exact_triangle_relation` kernel now classifies two nondegenerate
triangles as disjoint, point, segment or coplanar-area intersection using exact
rational geometry and deterministic witness points. It carries no mesh index,
adjacency, component, budget or near-contact policy. It cannot establish
allowed contact or V0 pass; a separate target-mesh pair diagnostic must apply
those rules and independently test the intended shared simplex.
`diagnose_indexed_triangle_mesh_pair_relations` now does that exact
intersection-only pair check over a pre-admitted exhaustive face-pair budget.
It revalidates source and topology evidence, rejects zero-area triangles, and
records each relation with string-encoded rational witnesses. A shared indexed
vertex is allowed only as that point; a shared indexed edge only as exactly
that segment. Any extra intersection is marked forbidden. This is still a
source-order-dependent diagnostic, not a V0 outcome: component-specific error
classification, near-contact distance and certified final normalization remain
open.
An isolated `triangle_distance_squared` kernel now computes exact minimum
squared distance for nondegenerate triangles, returning zero for intersection
and checking vertex-face plus edge-edge features for disjoint surfaces. It has
no mesh identity, profile threshold or clearance semantics by itself.
`diagnose_indexed_triangle_mesh_near_contact` applies that kernel to all
nonadjacent indexed face pairs after source, topology, profile and complete
vertex/face pair-budget checks. It reports exact zero separately from positive
distance at or below the inclusive profile-relative `2^-40` threshold, using
exact squared mm² rationals and the exact squared vertex diameter. Face-pair
component relation and the minimum nonadjacent distance remain diagnostic;
pairs sharing an indexed vertex are counted but skipped with adjacent residual
contact explicitly `UNRESOLVED`. This does not certify clearance, permissible
adjacent contact, a normalized mesh or V0 acceptance.
`diagnose_indexed_triangle_mesh_canonical_order` separately revalidates the
source, issue-free orientable index topology and exact nondegeneracy, then
lexicographically orders binary64 vertices and cyclically rotated faces while
retaining both source-to-derived index maps. It is only an ordering diagnostic:
further V0 geometry checks, certified component/boundary normalization and permitted global
winding correction are missing, so it emits no canonical semantic mesh hash.
`diagnose_indexed_triangle_mesh_boundaries` recomputes this ordering and index
topology before deriving directed boundary cycles from face winding. It rotates
each cycle to its least ordered vertex and sorts loops and component keys,
retaining source maps. It refuses invalid topology and does not infer opening
assignments or outward orientation. These directed cycles remain diagnostic
evidence until the remaining V0 gates and normalization records are complete.
`diagnose_boundary_landmark_eligibility` revalidates source, ordering, directed
cycles and the immutable profile, then computes exact point-to-segment squared
distances per landmark and loop. It compares against the declared tolerance
plus `2^-40` times the mesh diameter algebraically, without a rounded square
root. Landmark, vertex-pair and segment-test limits are checked before distance
work. It records rational distances and all eligible loops; zero, one or several
candidates become `UNMATCHED`, `UNIQUE` or `AMBIGUOUS`. Typed landmark requests
are validated and sorted by ID. V0 acceptance remains a separate gate.
`diagnose_target_mesh_openings` binds full semantically validated DesignSpecs
and inline/resolved MaterialProfiles to the exact source bytes and target frame.
It recomputes ordering, directed loops and landmark evidence within explicit
limits, verifies declared component/loop counts and requires a bijection between
`REMAIN_OPEN` declarations and loops. Empty, unmatched, ambiguous, split or shared
landmark assignments fail closed. Construction-time closure declarations do not
create target boundary loops. Purpose labels are preserved, not inferred from
geometry. Sorted references make rejection evidence independent of list order.
The result remains `OPENING_BINDING_DIAGNOSTIC_ONLY`, not V0 or physical acceptance.
The isolated `orientation2d` and `orientation3d` backend evaluates outward
binary64 intervals and returns a sign only when the determinant interval
excludes zero. An inconclusive filter uses exact binary64 rationals under an
explicit fallback budget. Format and subnormal-arithmetic guards accompany
the documented correctly-rounded IEEE runtime assumptions; callers must keep
the floating environment unchanged. Results identify backend/version, path
and bounded determinant-node work. The independent 3D test oracle uses a
homogeneous determinant with independent Leibniz expansion. Deterministic
Hypothesis properties cover finite binary64 values, subnormals and overflow
against rational oracles, including sign antisymmetry. This backend is not yet wired into complete V0
admission or its mesh intersection pipeline.
The separate `adjacent_triangle_residual_squared` experiment evaluates exact
distance outside a caller-defined rational barycentric pair-local exclusion
zone. It includes mixed retained/excluded point pairs and first rejects any
original contact beyond the intended shared entity. It emits `EXPERIMENTAL`
evidence only, has no default lambda and does not change the frozen V0 profile.
Its equations and non-retessellation-invariant scope are recorded in
[`ADJACENT_RESIDUAL_EXPERIMENT.md`](ADJACENT_RESIDUAL_EXPERIMENT.md).
`propose_indexed_triangle_mesh_winding` separately recomputes source, topology,
exact geometry, ordering, all original pair relations and closed-volume
evidence. Only a reliable negative closed component can receive one recorded
whole-component reversal. Open winding is preserved; mixed open/closed meshes
are explicitly unsupported in this stage. Maps are rebuilt after reversal and
sorting. The result remains a source-bound diagnostic proposal with unresolved
admission gates, not a canonical mesh or V0 pass. See
[`MESH_WINDING_PROPOSAL.md`](MESH_WINDING_PROPOSAL.md).

`inspect_v0_mesh_v2` runs the versioned DesignSpec 1.1 barycentric
adjacent-zone policy through a complete V0 decision for supported amigurumi and
garment triangle meshes. `inspect_v0_closed_mesh_v2` retains its closed-only
scope. The check rebinds the source hash, profile hash and material reference;
checks exact topology, component and boundary counts, area and coordinate
thresholds, original face-pair relations, nonadjacent and adjacent clearance,
closed-component signed-volume orientation, and a unique declared opening
assignment when boundaries exist; then emits canonical mesh JSON, its hash,
source index maps and normalization events. Pair work and exact fallback work
are bounded. The API reports V0 `PASS` only for this admitted profile and keeps
overall verification `NOT_VERIFIED` and physical status `UNTESTED`. Flat, lace
and non-mesh V0 profiles remain outside this operation.

## Executable checks

The separately authorized local browser trial is started with
`.\.venv\Scripts\python.exe tools/run_prototype.py` or
`Start-CrochetPrototype.cmd` in the checkout. The launcher prefers the existing
project `.venv`; install the declared dependencies there for PDF export.
It listens only on <http://127.0.0.1:8765> and stores its own projects in
`artifacts/local-prototype/prototype.sqlite3`. The installed wheel also supplies
`crochet-ai-prototype --software-commit <actual-git-head>`; when started outside
a checkout, the commit must be supplied explicitly. It packages all seven
static assets and uses the same deterministic source-bound generation.
See [LOCAL_PROTOTYPE_V1.md](LOCAL_PROTOTYPE_V1.md) and
[PROTOTYP_TESTEN.md](PROTOTYP_TESTEN.md) for supported forms and honest evidence
limits. The shaped schematic display is separate from the narrow experimental
plain-strip forward pipeline.

The PDF route serves a complete printable document for a saved source-bound
artifact; no client-supplied instructions, external images or cloud renderer
are used. It includes material values, rounds and a physical-test worksheet.
ReportLab is the reviewed pagination dependency. The recipient can read/print
the exported file without this server. An unsupported font character is an
explicit export error; no missing glyph is silently substituted.

```powershell
python -B -m pytest -q
python -m ruff check src tests setup.py
python -m mypy src/crochet_ai
node tools/canonical_reference.mjs tests/conformance/canonical-vectors.json
git diff --check
```

Packaging additionally requires building/installing a wheel in a clean venv
without `--system-site-packages`, running `python -m pip check` and checking the
installed artifact outside the checkout. Invoke that venv's Python with `-I`
and the absolute path to `tools/installed_smoke.py`. The script refuses global,
user-site or source imports, compares every registered bundled schema file and the
immutable profile byte-for-byte with their authoritative sources, exercises
orientation and mesh residual diagnostics, and runs the installed console
entrypoint. It emits dependency versions in a machine-readable report.

On 2026-09-30 this clean Python 3.11.9 installation and smoke passed with
jsonschema 4.26.0 and rfc8785 0.1.4; `pip check` found no broken requirements.
The earlier inherited-dependency smoke alone was not sufficient. The V0
profile is included in the source distribution manifest. Installation evidence
covers this Windows/Python environment and the implemented subset, not every
supported Python/platform combination or full backend acceptance. See
`BACKEND_ACCEPTANCE_PLAN.md` for open release gates.
