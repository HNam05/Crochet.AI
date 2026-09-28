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

## Analytic proposal policy

`analytic-closed-sc/1` supports a single yarn/color, non-branching closed-pole
cyclic SC construction starting in a magic ring and ending in CLOSE. Sphere,
ellipsoid and eligible explicit radial profiles are decoded. Cylinder/cone
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

## Durable local jobs

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
failure and child termination produce explicit job failure. The watchdog is an
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
of complete F0: shear, bending, contact, pressure and boundary mechanics remain
unimplemented, and neither coefficients nor thresholds are physically calibrated.

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

## Executable checks

```powershell
python -B -m pytest -q
python -m ruff check src tests setup.py
python -m mypy src/crochet_ai
node tools/canonical_reference.mjs tests/conformance/canonical-vectors.json
git diff --check
```

Packaging additionally requires building/installing a wheel in an isolated
environment, checking bundled schema bytes, and invoking the console script
from outside the checkout. Passing these checks covers the implemented subset
only. See `BACKEND_ACCEPTANCE_PLAN.md` for open release gates.
