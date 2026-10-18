# FLAT_SC_ROWS_V1

## Status and support boundary

`FLAT_SC_ROWS_V1` is a bounded producer for one narrow construction: a single
color and yarn, one independent fabric `ATTACH` anchor, a straight foundation
chain, and plain single-crochet rows. The foundation-chain course and following
rows are linear. The chain is emitted from its first to last loop, so the hook
is at the last loop. The first SC row returns from that end toward the first
loop (`REVERSE`), and later rows alternate direction. Each SC explicitly
replaces one `TOP_LOOP` at its oriented position. The untouched fabric anchor
remains live until terminal `CLOSE` retires the logical frontier. Logical close
does not claim that the fabric is physically closed in three dimensions.

ATTACH creates an unbound external fabric attachment point. The planar target
record does not locate or validate that point against the rectangle, and the
solver has no substrate geometry or demonstrated attachment. This is a logical
anchor needed to emit a complete CrochetIR component, not a physical
foundation-edge construction. No separate turning CHAIN is emitted: turn
behavior is represented only by each course's `TURN` metadata and work
direction. Whether a traditional turning chain is required for a particular
yarn, hook, or edge convention remains unverified.

The solver accepts only `project_type=FLAT`,
`work_structure=ROWS`, `repeat_policy=NONE` or
`FIT_WITHIN_DIMENSION_TOLERANCE`, one color, allowed SC/ATTACH/CLOSE, and a
explicitly allowed `CHAIN` foundation and `SINGLE_CROCHET` rows, plus a
resolved `SINGLE_CROCHET` / `LINEAR` material response for the requested
tension profile and fabric state. It does not implement repeated stitch
patterns, increases/decreases, rounds, grids, C2C, motifs, openings, tapestry,
or multi-yarn work. Unsupported cases fail closed.

## Input target record

The caller supplies the exact raw bytes for a UTF-8 JSON object no larger than
65,536 bytes. Its only keys are:

```json
{
  "profile": "FLAT_RECTANGLE_TARGET_V1",
  "version": "1",
  "coordinate_frame_id": "frame_target",
  "width_measurement_id": "dim_width",
  "height_measurement_id": "dim_height"
}
```

Duplicate keys, invalid UTF-8, non-I-JSON values, unknown keys, other profiles,
and other versions are rejected. The raw-byte SHA-256 must equal the
DesignSpec's `PLANAR_REGION.artifact.sha256`; its frame ID must equal the
DesignSpec planar frame. No target URI is fetched. Width and height values and
tolerances come only from the two referenced DesignSpec measurements, whose
semantics must be `OVERALL_WIDTH` and `OVERALL_HEIGHT`. The record binds which
rectangle dimensions the planar asset represents; it supplies no alternate
coordinates, geometry, or dimensions.

## Versioned run configuration

`FlatRowsRunConfig` has exactly these fields:

| Field | Contract |
| --- | --- |
| `parameter_profile_id` | Must equal `DesignSpec.solver_options.parameter_profile_id`. |
| `tension_profile_id`, `fabric_state` | Must select exactly one calibrated SC/LINEAR response in the resolved material profile. |
| `random_seed` | Must equal the DesignSpec seed and is recorded; this solver is deterministic and does not sample. |
| `max_columns`, `max_rows` | Inclusive search ranges are 1 through each maximum; each maximum is at most 512. |
| `max_candidate_evaluations` | Must not exceed the DesignSpec limit or 262,144 column/row pairs. |
| `max_events`, `max_attachment_locations`, `max_memberships` | Explicit candidate ceilings, at most 8,192 events, 16,384 locations, and 262,144 repeated references. |

The membership counter sums emitted entity-ID array entries: frontier location
snapshots, stitch bases/tops, course members and order, branch and component
memberships, transition frontiers and locations, operation IDs, yarn
path/segment references, provenance input artifacts, and derivation subject
references. Scalar ID fields and entity-table records are excluded. The report
exposes the selected candidate's event, location, and membership counts for
comparison with emitted IR.

Run config identity is SHA-256 over JCS bytes domain-separated by
`FLAT_SC_ROWS_RUN_CONFIG_V1`. Candidate derivation parameters are separately
hashed under `FLAT_SC_ROWS_PARAMETERS_V1`. Caller-supplied provenance names
beginning with `flat.` or equal to `source_snapshot_sha256` are rejected.
Provenance fields are checked for native string, tuple, and scalar types before
hashing or canonicalization.

## Discrete model and ordering

For each candidate pair `(columns, rows)` in ascending column-major order,
the solver evaluates exact rational predicates:

```text
abs(columns * stitch_pitch - target_width) <= width_tolerance
abs(rows * course_pitch - target_height) <= height_tolerance
```

Every DesignSpec/material binary64 value is converted with
`float.as_integer_ratio()` before arithmetic (integer-valued JSON numbers remain
exact integers). No tolerance is inferred or enlarged by the solver. Material
pitch multiplication is a **cell-coverage hypothesis**; it does not establish
physical fit, edge behavior, drape, or dimensional accuracy.

Exact rational report pairs use decimal strings for numerator and denominator;
binary64 fractions routinely exceed I-JSON's safe-integer range. These strings
preserve exact values without rounding the JSON response.

Among candidates that satisfy both exact predicates and fit the declared IR
resource ceilings, the total order is:

```text
(width residual, height residual, stitch count, course count, rows, columns)
```

The solver emits the best candidate found in the examined prefix. A candidate
from an incomplete prefix is marked with `SEARCH_BUDGET_EXHAUSTED`; it is not
claimed to be the global best. Complete enumeration with no resource-admissible
pair returns `NO_FEASIBLE_CONSTRUCTION`. Candidate evaluations, geometric pair
count, declared domain size, completion, and exhaustion are reported explicitly.

Before allocating CrochetIR tables, the producer computes the exact required
counts for events, locations, and repeated reference memberships. The candidate
is built only if every count is within both hard implementation ceilings and
run-config limits. The search uses at most `max_columns * max_rows` predicate
evaluations, which is bounded by 262,144. Building one candidate is linear in
its emitted events and frontier snapshots.

## Compilation and evidence boundary

The producer has a dedicated FLAT lowering and emits complete
`CROCHET_CORE_1.0.0` CrochetIR. It then calls the independent
`SemanticValidator` for DesignSpec, MaterialProfile, and final CrochetIR
validation. The report binds DesignSpec, material, raw target bytes, run config,
source snapshot, commit, and canonical CrochetIR hashes, along with selected
counts, exact residuals, and actual work. It never labels a generated candidate
as geometry-verified; `physical_status` remains `UNTESTED`.

The algorithm, output ceilings, calibrated response selection, and exact
rational comparison are engineering contracts for this version. Calibration
transfer to a blanket, edge handling, tension variation, and actual physical
dimensions remain unverified. Independent forward simulation, target
comparison, export round-trip, and physical swatches are separate acceptance
work.
