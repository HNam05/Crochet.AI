# Local human-test prototype V1

Owner: main integration agent. User requested a usable prototype and local
browser testing on 2026-10-04; a separate mobile app is explicitly deferred.
This supersedes the prior frontend-out-of-scope sequencing for this limited
prototype, not backend release acceptance or mandatory verification gates.

## Scope and trust

Support SPHERE, ELLIPSOID and versioned closed revolution profiles for cylinder,
cone, capsule and pear, one yarn/color, continuous cyclic single crochet,
binary increases/decreases, magic ring and closure. Reuse the existing bounded
analytic generator, semantic validator and Pattern V1 exporter/round trip.
No solver/verifier/schema/golden edits. No fixture files imported at runtime.
All results remain NOT_VERIFIED and UNTESTED. Human testing is authorized;
feedback is self-reported, unreviewed evidence, never automatic calibration.

The visual thesis is a quiet workshop: warm neutral background, dark ink,
one rust accent, square controls, readable system typography and a large actual
maschen/work surface. Content is inputs, schematic object, rounds/instructions,
then making controls and test feedback. Interaction is direct orbit/zoom,
selection and progress changes; no ornamental or hover animation. Respect all
user design exclusions. No external code, pattern, imagery, fonts or framework.

## Wire contract

Loopback-only local server. Envelope is `{ok:true,data:...}` or
`{ok:false,error:{code,reason}}`. Bootstrap supplies prototype_version `1.0.0`,
csrf_token and default_request. Every mutation requires same-origin request,
correct Host and X-CSRF-Token. Bind only 127.0.0.1; no CORS, account or remote API.
Allowlist static assets; reject traversal, invalid origins/hosts, excessive
bodies, duplicate keys, unsafe integers and nonfinite numbers. Maximum body
65,536 bytes. One active generation at a time, bounded input/search/storage;
no partial candidate selected after an exhausted batch.

Routes:

- GET /api/bootstrap -> data with prototype_version, csrf_token, default_request.
- POST /api/generate -> data is a complete project as below.
- GET /api/projects -> data.projects is a summary array.
- GET /api/projects/{id} -> data is the complete saved project.
- POST /api/session -> data is {project_id,revision,cursor}.
- POST /api/feedback -> data is the appended feedback record.
- GET /api/projects/{id}/feedback -> data.feedback is the record array.
- GET /api/projects/{id}/pattern.pdf -> downloadable application/pdf attachment.

Generation body is closed, all fields required:
prototype_version, shape (`sphere`, `ellipsoid`, `cylinder`, `cone`, `capsule`,
`pear`), diameter_mm, height_mm,
stitches_per_100mm, courses_per_100mm, hook_diameter_mm, yarn_label, color_hex,
uncertainty_percent. Counts are integer observations over 100 mm, 5..60;
dimensions 20..100 mm, hook 0.5..12 mm, uncertainty 1..50 percent, yarn 1..120
characters, sRGB six-hex color. Sphere requires height_mm == diameter_mm;
capsule requires height_mm >= diameter_mm.
Use full user-entered observations; metadata alone never substitutes gauge.
Default example: sphere 40x40 mm, 25 stitches and 28 courses per 100 mm, 3 mm
hook, yarn 'Meine Testwolle', #B88757, engineering uncertainty 10 percent.
Defaults are editable demonstration values, not measured user material.

Bootstrap additionally exposes `shape_catalog`: closed example descriptions and
dimensions owned by the backend. Loading example dimensions preserves gauge,
hook, yarn, color and uncertainty. Invalid/duplicate catalog entries are rejected
by the browser. Existing 1.0.0 requests and persisted artifacts remain supported;
new accepted shape identifiers are an additive prototype capability.

### Additional target profiles

`prototype_{shape}_silhouette_v1` records original target design definitions:
cylinder has a radial base disk, straight side and top disk; cone has a radial
base disk and linear taper to the tip. These are explicitly closed solids,
distinct from the existing open-interface CYLINDER/CONE primitives.
Capsule has quarter-circle sampled caps (32 segments per cap) and an explicit
straight middle; height equal to diameter has no duplicate equator point.
Pear uses 129 normalized silhouette samples with a wider lower belly and narrow
upper region. It is a single rotational body, not arbitrary organic topology.

All new targets use the existing content-addressed SURFACE_OF_REVOLUTION
contract. Ordered axial/radial silhouette samples are converted to cumulative
meridional arc lengths in mm. End radii are zero and interior radii positive.
Sampled maximum radius equals requested diameter/2. The samples themselves
define piecewise-linear design intent; sample count is recorded resolution,
not a certified geometric approximation bound. No stitch counts enter the
target, and target coordinates never constrain independent forward simulation.

Binary64 hypot/add may shorten a represented increment. Exact rational
comparisons of the represented radii/s values admit a single outward nextafter
step when necessary; at most one cumulative-s ULP per sample, owned by prototype
integration. Failure to satisfy strict |dr| <= ds after that step rejects the
request; the existing decoder is unchanged. This is a bounded target-authoring
rounding allowance, not physical accuracy. MERIDIONAL_LENGTH equals the final
serialized s exactly and its authoring tolerance is zero. Profiles are bounded
to 129 samples. Course proposal uses the profile's meridional length; existing
integer search budgets, admission limits and zero-phase compilation still apply.

### Printable export

Pattern PDFs use US English crochet terminology (`sc`, `inc sc`, `dec sc`, `MR`)
and compact numbered rounds (`R1`, `R2`, ...). The final parentheses contain the
total stitches at the end of the round, including both tops of every increase.
Repeated motifs retain the exact canonical work order; explicit insertion
positions are preserved when the construction differs from sequential traversal.

PDF export derives instructions from the saved validated IR and binds its
source hash, design and material. It does not use submitted prose or current
session progress as the pattern. A4 pagination includes English preparation,
the exact round order, totals, shaping meanings, source identity, verification
limits, and a printable report worksheet for remote human feedback.
ReportLab is the reviewed local pagination dependency; no cloud, external font,
image URL or rendering service is used. Unsupported text encoding or source
inconsistency returns E_EXPORT rather than a damaged or misleading PDF. The PDF
is a presentation artifact; controlled Pattern V1 remains the semantic round-trip
boundary. See the [dependency review](research/PROTOTYPE_PDF_REVIEW_2026-10-05.md).

Backend-owned numeric profile is PROTOTYPE_ANALYTIC_V1. Record every actual
budget/tolerance in run_config and source provenance. Arc/zero/roundoff limits
are operational analytic approximation limits in mm, not calibrated acceptance
thresholds. Primary integration reviews the selected limits and executable
default/ellipsoid/scaling fixtures before acceptance. Candidate selection is
the first deterministic emitted candidate only when batch CANDIDATES_EMITTED.
V6/V7/V8/V10 are not passed or replaced by this choice.

### Continuous human work order

The general analytic phase optimizer can rotate a course's first base location.
The default proposal contains such rotations. That is not an instruction to
jump over unworked stitches in a continuous hand-crocheted spiral. The local
prototype therefore uses the completely emitted analytic candidate as a count
proposal, then calls the existing canonical closed-schedule compiler with
all course phases fixed to zero. This is the explicit prototype policy
`FIXED_ZERO_CONTINUOUS_V1`, recorded in compile provenance and run_config.
The final recompiled IR is independently validated and round-tripped. The
original proposal's phase work is recorded as proposal work only.

Invariant: in every course, the concatenation of stitch base locations is
exactly its ordered input frontier. Binary increases consume one base and
produce two tops; binary decreases consume the next two bases and produce
one top. No skipped stitches, invented yarn floats, cuts or repositioning are
introduced. Fixed phases sacrifice angular shaping optimization; stacking,
surface appearance and geometry acceptance remain unverified. The solver and
independent verifier contracts are unchanged.

### Numerical profile rationale

One course-count hypothesis is rounded from an explicitly approximate half
ellipse meridian length divided by measured course pitch. Only 3..32 courses
are admitted; out-of-range proposals are rejected rather than clamped. Counts
are restricted to 2..32, initial ring 6..10, terminal count at most 6, with a
count window of four stitches and bounded shaping per course. These are
prototype construction/search limits, not shape-accuracy guarantees.

Meridian absolute tolerance is 0.05 mm (below the minimum allowed course pitch
100/60 mm); roundoff allowance is 1e-8 mm and numerical zero radius is 1e-9 mm.
These are operational solver hypotheses under recorded binary64 arithmetic,
not certified physical tolerances. Up to 10,000 arc panels, 100,000 count
transitions, 100,000 placement transitions, 1,000,000 placement pairs and
10,000 compiled stitch events bound work. The full named limits are serialized
in each project. Owner: prototype integration; calibration path: user samples
followed by independently reviewed material and geometry acceptance profiles.
Search exhaustion yields a rejection. The user uncertainty percentage remains
an engineering assumption; it is not a measured confidence interval.

The `local_user_entry_v1` protocol records integer stitch/course **interval**
counts across 100 mm on relaxed, unstuffed cyclic SC fabric. The entered
percentage defines a hypothetical relative bound `b = pitch * percent / 100`.
Its identity conversion `u = b` is a conservative engineering proxy for the
standard-uncertainty field, with unknown distribution and covariance; no
probability, coverage or calibrated error bound is inferred. This prototype
does not run robustness verification or use that hypothesis to certify size.
The 1 mm DesignSpec dimension tolerance is a prototype authoring default owned
by integration, not an independently passed dimensional acceptance threshold.

A complete project contains:

- prototype_version `1.0.0`, project_id (full source CrochetIR SHA-256), request;
- design_spec, material_profile, crochet_ir, run_config, pattern_text;
- source_crochet_ir_sha256, semantic_validation `PASS`, round_trip_state `PASS`,
  verification_state `NOT_VERIFIED`, physical_status `UNTESTED`;
- generation {status,reason,work,search_trace,search_trace_sha256,
  proposal_to_final,proposal_to_final_sha256,proposal_bundle,
  proposal_bundle_sha256} for newly saved traced projects;
- courses [{course_id,number,total_stitches,summary_de,step_ids}];
- steps [{step_id,event_index,course_id,course_number,kind,stitch_id,
  instruction_de,base_location_ids,top_location_ids,produced_stitches,
  course_stitches_after}];
- preview {profile:`SCHEMATIC_COURSE_LAYOUT_V1`,unit:`mm`,
  role:`ILLUSTRATIVE_NOT_PHYSICAL`,points:[{location_id,stitch_id,step_id,
  course_id,xyz_mm,color_hex}]};
- session {project_id,revision,cursor}.

Presentation consumes validated IR event/course order, compound shaping nodes
and exact attachment identities, never prose as construction. Ring/closure
are explicit steps. Human German mapping exists only at this presentation
boundary. If work order needs explicit base positions, instructions show them;
never compress away essential attachment/phase information. Summary text is
only a course overview. Controlled Pattern V1 remains separately downloadable.

Preview is an explicit schematic course layout computed from canonical top
counts and reported stitch/course pitch. No target geometry, solver sample,
physical simulation or invented closure cap enters this display layout.
All top locations map to their producer event and course. Unsupported display
construction is rejected. The UI labels this schematic, not a predicted shape.

Session POST body: prototype_version, project_id, expected_revision, cursor.
Cursor means the next instruction index, 0..len(steps). Completion does not
promote physical status. Revision 0 initially; compare-and-update atomically,
409 E_CONFLICT on stale writes. Regeneration/restoration of the same artifact
preserves progress; a changed IR gets a separate project/session.

Feedback POST body: prototype_version, project_id, outcome (WORKED,
NEEDS_CHANGES or NOT_FINISHED), notes (0..4000 chars), actual_diameter_mm and
actual_height_mm (null or finite 0..1000, strictly positive when provided).
Append source-bound records with id/time; do not overwrite prior reports or
alter canonical material/IR. Human reports are HUMAN_FEEDBACK_UNREVIEWED.
Project and feedback downloads retain exact source/material binding.

Persist with bounded SQLite in a user-selected local data directory, default
artifacts/local-prototype. Atomic session/feedback writes and explicit storage
errors. Do not erase/migrate unrelated databases or data automatically.

New generation retains the original complete proposal CrochetIR in the
domain-hashed [proposal snapshot bundle](PROTOTYPE_PROPOSAL_BUNDLE_V1.md),
including trace/input bindings and the existing final-phase-policy link. It is
stored atomically with the project/session inside the existing payload limits.
Restart, downloads, progress updates and feedback preserve these snapshots.
Same-ID legacy projects retain their original generation record without backfill.
Before `/api/verify`, admit a present bundle strictly and pass its originals to
the unchanged independent trace auditor; partial or corrupted bundles fail
explicitly. Complete sphere traces can now pass their scoped audit. The final
zero-phase relation and physical feasible selection still need independent
verification, so overall `NOT_VERIFIED` and `UNTESTED` remain unchanged. Large
verification envelopes can exceed the existing 2 MB/100,000-node API limits;
they fail explicitly without truncating evidence or enlarging those limits.

## Live acceptance

Start with one command; open the actual local browser UI. Generate editable
default sphere and ellipsoid with measured/user-reported gauge. Validate IR,
export round trip, step/top/base identity and full event coverage. Generate
twice deterministically, check size/gauge effects, structured invalid inputs,
resource failure and unsupported version. Test loopback/Host/Origin/CSRF/path
boundaries and session optimistic locking/feedback persistence.
In browser exercise orbit, step forward/back, course and object selection,
reload/restore progress, downloads, feedback and a narrow mobile viewport.
No new third-party runtime dependency is required. Run full Python/Ruff/mypy,
Node canonical/reference and meaningful frontend checks, package/install smoke.
Physical sample remains for the user; include concise test instructions and
clear limitations rather than claiming their future report already exists.
