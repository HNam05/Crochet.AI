# Closed shaped elastic diagnostic V1

Status: implementation contract, 2026-10-08. This additive P04 scope prepares
target-free rest terms, initial coordinates and initial elastic forces for the
actual closed SC constructions. It is not an optimizer, complete F0 model,
ForwardSimulationOutcome, V6 evidence or physically calibrated prediction.

## Scope and interface

The backend operation `inspect_shaped_forward_model` accepts API 1.0.0 with
exactly `api_version`, `operation`, `design_spec`, `material_profile`,
`crochet_ir`, and `forward_run`. Source admission uses DesignSpec outside the
physical execution boundary. Execution accepts only PhysicalSemanticProjection,
resolved MaterialProfile, an admitted recipe and a material validator.

The physical subset is a single closed component/branch/yarn, cyclic SC,
PLAIN 1:1, INCREASE 1:2, DECREASE 2:1, and explicit MAGIC_RING/CLOSE. Require
the existing closed-cell admission and its complete ordered attachment cycles.
No ambiguous yarn response, unknown construction or unsupported open specimen
is repaired. The older plain strip forward pipeline remains unchanged.

`forward_run` has exactly these keys:

- `profile`: `FORWARD_SHAPED_ELASTIC_DIAGNOSTIC_V1`;
- nonempty `tension_profile_id` and `fabric_state`;
- `loading`, `model_profile`, `config`: the existing FORWARD_RUN_INPUTS_V1
  admission, including explicit unloaded/unpressurized state, hypothesis course
  and wale stiffness, owned tolerances and work budgets;
- `rest_parameters`: the closed explicit hypothesis document below.

`rest_parameters` requires schema_version 1.0.0, status HYPOTHESIS,
provenance_id, and every numeric field in this table. No default is supplied.

| Field | Unit | Meaning and calibration path |
| --- | --- | --- |
| wale_rest_length_factors | dimensionless | Exact PLAIN/INCREASE/DECREASE registry; each multiplier applies to that stitch's course pitch. Transition specimens must identify transfer independently of pitch. |
| wale_stiffness_factors | dimensionless | Same registry; multiplier of declared wale stiffness for each incidence. Force/displacement fixtures must identify stiffness and arity effects. |
| ring_rest_length_mm | mm | Rest length of each ring-anchor to first-course-top incidence; ring fixture, separate from interior gauge. |
| ring_stiffness_n_per_mm | N/mm | Stiffness for those ring incidences; ring loading fixture. |
| ring_initial_chord_mm | mm | Explicit distinct-anchor polygon chord; initializer parameter, not a measured rest state. |
| ring_initial_offset_mm | mm | Ring plane offset below the first course; initializer parameter, not a physical dimension prediction. |

All numbers must be finite native nonboolean int/float, strictly positive and
compatible with the shared I-JSON/binary64 contract. Unknown fields, versions,
target/embedding/coordinate overrides and forged admitted objects fail closed.
The rest hypothesis owner is the caller's provenance_id; no evidence of
identifiability or calibration is inferred from an accepted document.

## Rest terms and initialization

Each COURSE adjacency gets the source top producer's stitch pitch and declared
course stiffness. Each WALE base/top incidence gets its owning stitch's course
pitch times the shape-specific length factor, and wale stiffness times the
shape-specific stiffness factor. INC/DEC retain all ordered incidences. Stiffness
is not automatically divided by arity. Ring incidences instead use the explicit
ring rest length and stiffness; the interior gauge is not transferred to them.

Initialization uses the physical ordered top cycle of each course as a regular
polygon with uniform stitch-pitch chord. The first course is at z=0; subsequent
courses advance by their own uniform course pitch. Ring anchors form a distinct
polygon at negative ring_initial_offset_mm with ring_initial_chord_mm. Polygons
use a fixed counterclockwise geometric layout relative to the closed-cell face
ordering. This fixes a deterministic coordinate gauge, not the finished shape.
Every surface vertex has exactly one finite coordinate; nothing is collapsed,
inferred from target geometry or silently omitted. Fan caps remain the existing
topological convention; this does not implement closure mechanics.

Evaluate the existing spring kernel at these initial points:
E = sum(0.5 k (distance - rest_length)^2), in N mm. Forces are the negative
coordinate gradient, in N. Reusing this computational kernel is explicit;
this operation is not an independent verifier of its physical accuracy.
Rest lengths are prepared before and independently of initial coordinates.
Nonfinite or zero-distance force evaluation returns an error with no bundle.

## Bounds and evidence

One initialization only; maximum 2,048 vertices, 4,096 closed-cell faces and
8,192 spring terms. The caller's vertex budget can be lower. Check allocation
budgets before coordinate/term output. These exact integer limits are backend
work policies, not numerical or physical acceptance tolerances. No new epsilon
is introduced. Existing request byte/node/depth bounds and job watchdog remain.
Optimizer/contact budgets are recorded input policy, not counters of executed
optimization/contact work; neither operation runs here.

The deterministic bundle binds physical projection, material, recipe, closed
cells, explicit spring/rest parameters, complete coordinate/face labels,
elastic energy, forces and maximum force with domain-separated JCS hashing.
Keep the source CrochetIR hash outside this bundle. Target identity, solver
seed/provenance and color-only edits cannot affect the physical bundle.

Always report EXPERIMENTAL_INITIAL_ELASTIC_DIAGNOSTIC, comparison_eligible=false,
NOT_VERIFIED, physical UNTESTED and V6 NOT_RUN. Missing closure mechanics,
shear/bending, loading/contact response, optimization/V6 and physical calibration
remain explicit. Zero energy or small residual cannot promote this diagnostic
to a simulation or release pass. Dedicated open calibration-tube mechanics,
pressure, collision response and V6-V8/V10 are subsequent work.

## Validation

Require hand-checkable PLAIN/INC/DEC and ring cases, unequal declared factors,
all base/top incidences, deterministic bindings, nonzero energy independent of
initialization, material resolution failures, malformed/forged recipes,
allocation ceilings and finite-output failures. Independently check force
balance and gradients, metadata exclusion and API/CLI/durable-job delivery.
Integrate only after the full suite, lint/type checks and isolated wheel checks.
No canonical schemas, goldens or physical records are changed by this scope.
