# Experimental forward pipeline V1

Status: implemented experimental B4/B6 integration checkpoint (2026-10-04). This is an
additive orchestration profile, not `ForwardSimulationOutcome`, complete F0,
V6 admission, calibrated physics or frontend work.

## Purpose and ownership

Connect the existing physical projection, graph, initialization, stretch,
shear, bending, optimizer and exact final-contact diagnostic through one bounded
local API/CLI operation. Owner: backend/forward-model integration. Numerical
algorithms, independent semantic validator, contact predicates, frozen schemas,
profiles and goldens remain unchanged.

## Request

Add `run_forward_prototype` to API envelope `1.0.0`. Required top-level fields:
`api_version`, `operation`, `design_spec`, `material_profile`, `crochet_ir`,
`forward_run`. The DesignSpec is used for admission and source binding outside
the simulator. No target asset is fetched or passed into physical execution.

`forward_run` is a closed object with exactly:

- `profile`: `FORWARD_STRETCH_SHEAR_BENDING_PIPELINE_V1`;
- `tension_profile_id` and `fabric_state`: explicit nonempty strings;
- `loading`, `model_profile`, `config`: unchanged documents admitted by
  `admit_forward_inputs`, including all unit-bearing, owned tolerances;
- `shear_parameters`: a closed object containing `schema_version: "1.0.0"`,
  `status: "HYPOTHESIS"`, `provenance_id`, `stiffness_n_mm`, `rest_cosine`;
- `bending_parameters`: a closed object containing `schema_version: "1.0.0"`,
  `status: "HYPOTHESIS"`, `provenance_id`, `stiffness_n_mm`, `rest_dihedral_rad`.

Parameter admission uses the existing hypothesis helpers. No stiffness, angle,
rest cosine, material response, tolerance or loading default is inferred from
geometry. Unknown fields and versions, including target/embedding/initial
coordinate overrides, fail closed. The legacy input `model_version` remains
`F0_STRETCH_PROTOTYPE`; the new orchestration profile explicitly binds its
additional shear and bending parameters rather than mutating that input format.

## Resource contract

Client work budgets must be positive valid integers and not exceed these local
server limits. Oversized budgets are rejected, never clamped:

| Budget | Maximum |
| --- | ---: |
| max_initializations | 1 |
| max_initialization_vertices | 128 |
| max_line_search_trials | 32 |
| max_optimizer_iterations | 128 |
| max_energy_evaluations | 4096 |
| max_linear_iterations | 2048 |
| max_contact_pairs_evaluated | 32640 |

These are operational integer work limits owned by backend integration, not
numerical/physical acceptance thresholds. Existing request byte/node/depth
limits remain in force. Before optimization, reject a surface whose full
unordered triangle pair count exceeds the requested contact budget. Diagnostic
work is exhaustive, not an AABB-only subset. No partial surface/contact report
is presented as a completed run.

## Execution and independence

1. Validate external source and material binding using existing admission.
2. Build the immutable target-free physical-semantic projection.
3. Lower graph with exact material-response selection.
4. Admit explicit run inputs and enforce operational limits before numerical work.
5. Build supported surface cells and triangulation; precheck full pair work.
6. Initialize from the physical projection/graph and admitted inputs only.
7. Prepare stretch, shear and bending terms; run existing combined optimizer.
8. Only if optimizer returns `EXPERIMENTAL_FORCE_BALANCED`, run the existing
   exact final-coordinate self-contact diagnostic.
9. Return bounded experimental data and a deterministic evidence bundle.

The admitted surface is the existing plain, aligned, cyclic 1:1 quad strip.
Ring/closure caps, shaping, branching, garment/lace/flat support, pressure,
contact response and V6 convergence are not invented by orchestration.
Unsupported semantically valid construction yields `E_UNSUPPORTED_FEATURE`.

The physical execution function accepts a physical projection, material,
admitted recipe and material-only validator, not a DesignSpec or raw target
geometry. The API must not pass the source admission validator's DesignSpec
registry into physical execution; it constructs a separate material-only
validator for the existing graph-lowering admission.
DesignSpec/IR source hashes may be returned by the API outside the experimental
bundle for source identification. They must not enter physical initialization,
recipe or execution hashing. Excluded target/solver/color provenance changes
must leave physical bundle bytes and coordinates identical.

## Result and failure contract

`ok:true` means the API handled the run, not that the pattern passed verification.
The response always keeps `verification_state: "NOT_VERIFIED"`,
`physical_status: "UNTESTED"` and `v6_outcome: "NOT_RUN"` for this profile.

The experimental bundle records its profile/version, run status, unit `mm`,
geometry role `EXPERIMENTAL_DEBUG_ONLY`, physical input and term hashes,
optimizer counters/trace, exact final-contact data when run, known limitations,
canonical bytes represented as a JSON object and a domain-separated SHA-256.
No timing, machine/path, target/source-IR identity or client-supplied software
provenance enters its hash. Existing optimizer payload binds initialization and
all three force-term identities.

The optimizer retains non-surface magic-ring anchors. The existing contact
diagnostic requires exactly the surface location domain. An explicit
`FORWARD_SURFACE_COORDINATE_RESTRICTION_V1` adapter therefore restricts the
optimizer coordinates to the union of cell locations without changing any
coordinate or inventing missing values. Missing surface locations fail closed.
The bundle preserves the original `optimizer_sha256` and records a separate
`contact_optimizer_sha256` for the restricted diagnostic input; the contact
report binds the latter. The adapter records retained and excluded location
IDs. Returned surface geometry contains only the retained locations. This
restriction does not create a new optimizer run or a physical acceptance claim.

- Balanced optimizer plus zero forbidden final intersections may return the
  experimental coordinates, triangle attachment IDs and both open boundaries.
  They are not authoritative predicted geometry or eligible V7 evidence.
- Budget exhaustion, numerical/line-search failure: preserve the exact optimizer
  status and counters; geometry is null and final contact is not run.
- Balanced optimizer plus forbidden final intersections: run status
  `FORBIDDEN_FINAL_INTERSECTION`, retain diagnostic evidence, geometry is null.
  The nested optimizer coordinates are redacted as well. Its recorded hash
  identifies the original internal artifact, not the redacted JSON view; the
  enclosing pipeline hash binds the published, redacted view.
- Admission/unsupported/budget-precheck errors use structured API errors with
  no geometry. Arbitrary programming exceptions are not silently swallowed.
- No collision-free, thickness-clearance, overall VERIFIED or physical pass is
  inferred from a zero-intersection diagnostic or a permissive force tolerance.

## Acceptance checks

- A project-authored aligned multi-course fixture runs through API and CLI with
  exact coordinate/triangle/boundary binding and byte-identical repeat results.
- Local durable jobs persist the same response without changing storage format.
- Malformed, missing/unknown fields, wrong versions, bool coefficients,
  prohibited target overrides and over-limit budgets return structured errors.
- Unsupported shaping/course-phase/construction fails with no repair.
- Budget and numerical failures expose no geometry; final-contact rejection is
  independently exercised at the orchestration boundary.
- Target/solver provenance changes outside physical semantics cannot affect the
  experimental bundle; response source identity changes remain outside it.
- Full Python suite, Ruff, strict mypy, independent Node canonical vectors,
  wheel build and out-of-checkout installed smoke at integration.

No new goldens or physical measurements are required for this additive software
checkpoint. B4/B5/B11 and backend release remain open after it.
