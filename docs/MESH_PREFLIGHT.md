# Domain-specific V0 geometry preflight

## Scope and boundary

V0 turns an external target asset into a deterministic, validated target representation or rejects it. It does not generate CrochetIR, choose a Construction Graph, repair topology, or evaluate crochet feasibility.

- **ENGINEERING DECISION:** preflight selection depends on both `project_type` and `target_geometry.geometry_type`; one universal mesh policy is forbidden.
- **PROVEN / FORMAL:** preflight acceptance cannot establish crochet reachability, physical plausibility, or geometric fidelity.
- **ENGINEERING DECISION:** source bytes remain immutable and retain their raw-byte hash. Normalized output is a separate derived artifact with its own hash and a complete normalization record.

## Profile selection

| Project / geometry | V0 profile | Accepted topology |
| --- | --- | --- |
| `AMIGURUMI_3D` / closed `MESH_3D` | `V0_AMIGURUMI_CLOSED_SURFACE_V1` | One or more explicitly expected, disjoint, closed orientable two-manifold components |
| `AMIGURUMI_3D` / open `MESH_3D` | `V0_AMIGURUMI_DECLARED_BOUNDARY_SURFACE_V1` | Orientable two-manifold components whose every boundary loop maps to a `REMAIN_OPEN` DesignSpec opening |
| `GARMENT` / `MESH_3D` | `V0_GARMENT_DECLARED_BOUNDARY_SURFACE_V1` | One or more orientable two-manifold sheet/panel components with declared boundary loops |
| `AMIGURUMI_3D` / `ANALYTIC_SHAPE` | `V0_ANALYTIC_SHAPE_V1` | The exact analytic contract in [`DESIGN_SPEC.md`](DESIGN_SPEC.md) |
| `GARMENT` / `GARMENT_MEASUREMENTS` | `V0_GARMENT_MEASUREMENTS_V1` | Typed, complete measurement/reference set; no mesh assumptions |
| `FLAT` / `PLANAR_REGION` | `V0_FLAT_PLANAR_REGION_V1` | Finite simple planar components with declared holes/repeats |
| `LACE_MOTIF` / `MOTIF_GRAPH` or `PLANAR_REGION` | `V0_LACE_MOTIF_GRAPH_V1` or `V0_LACE_PLANAR_REGION_V1` | Typed motif graph or planar region; lace voids are intentional topology, not mesh defects |

V1 rejects `MESH_3D` for flat and lace projects. A future 3D blocking/drape target requires a new profile and domain contract rather than reuse of amigurumi preflight.

## Common mesh requirements

Every V1 mesh profile requires:

1. a parseable, content-addressed indexed triangle mesh;
2. finite binary64 coordinates in an explicit right-handed millimetre frame;
3. the exact expected connected-component count;
4. every edge incident to one face at a declared boundary or exactly two faces in the interior;
5. orientable components with consistent local winding;
6. no zero-area, repeated-index, duplicate-face, isolated-face, or non-manifold edge/vertex under the versioned numerical profile;
7. no self-intersection within a component;
8. no intersection or zero-clearance contact between components;
9. the exact expected boundary-loop count and unambiguous loop-to-opening mapping when boundaries are permitted;
10. a deterministic result and complete diagnostic list under the declared `preflight_numerical_profile_id`.

Multiple components are allowed only when their exact count is declared. They do not imply separate CrochetIR components or a required seam; that decision belongs to domain solvers and verification. Intentional component contact is unsupported in V1 because tolerance-dependent contact declarations would otherwise hide intersections. It fails with `E_UNSUPPORTED_FEATURE`, not silent separation.

## Profile-specific predicates

### Closed amigurumi

`V0_AMIGURUMI_CLOSED_SURFACE_V1` requires `boundary_policy = FORBIDDEN` and `expected_boundary_components = 0`. Every component is closed and has a non-zero signed volume after consistent orientation. A construction-time stuffing opening whose DesignSpec expectation is `CLOSE_DURING_CONSTRUCTION` is not a target-mesh boundary.

### Amigurumi with declared target openings

`V0_AMIGURUMI_DECLARED_BOUNDARY_SURFACE_V1` requires `boundary_policy = DECLARED_ONLY` and at least one boundary loop. Every loop maps one-to-one to a DesignSpec intentional opening with `closure_expectation = REMAIN_OPEN`, using the declared boundary landmarks. Ambiguous or unmatched loops fail.

### Garment surface

`V0_GARMENT_DECLARED_BOUNDARY_SURFACE_V1` requires `boundary_policy = DECLARED_ONLY` and at least one boundary loop. Necklines, armholes, cuffs, hems, sleeve/front openings, and other retained boundaries must be declared. Multiple panel components are permitted when their exact count is stated, but overlaps, contact, thickness shells, and self-intersections are not accepted by V1.

## Deterministic normalization

Allowed normalization is deliberately narrow:

- decode the declared format into the versioned indexed-triangle representation;
- reorder vertices, faces, components, and boundary-loop starting positions by a versioned canonical ordering while retaining a source-index map;
- reverse the complete winding of one consistently oriented component when the profile's orientation convention proves it is globally inverted;
- rotate a boundary-loop serialization to its unique canonical landmark/vertex anchor without changing connectivity.

Every normalization is recorded in order with before/after hashes. The following are repairs and are forbidden in V0: vertex welding, hole filling, remeshing, decimation, subdivision, smoothing, face deletion, component merging/splitting, local winding guessing, intersection removal, and unit guessing. A proposed repaired asset is a new input requiring a new DesignSpec and V0 run.

## Boundary matching

Detected mesh boundary loops are canonical ordered vertex cycles. A loop matches a DesignSpec opening only when all declared boundary landmarks resolve to that loop and exactly one opening requirement is compatible with its purpose and closure expectation. Count equality alone is insufficient. A second valid matching is ambiguity and fails closed.

Mesh boundary identity never becomes a CrochetIR frontier ID. Solvers may derive a solver-private relation from target loops to Construction Graph ports. Only compiled attachment locations, frontier snapshots, and opening requirements enter CrochetIR.

## Numerical profile

Exact index-topology predicates use no tolerance. Geometric predicates such as near-zero triangle area, coincident vertices, intersection classification, signed-volume stability, and landmark-to-boundary matching require a versioned `preflight_numerical_profile_id`. Each value records units, comparison operator, rationale, owner, and convergence/adversarial validation path. Bootstrap chooses no hidden numerical values.

## Adversarial acceptance table

| Case | Required outcome |
| --- | --- |
| Closed consistently wound sphere | Pass closed-amigurumi profile |
| Same sphere with every face reversed | Pass only through one recorded whole-component reversal |
| Sphere with one face reversed | Fail ambiguous/inconsistent orientation |
| Sphere with one missing face | Fail closed profile; pass open profile only with one matching `REMAIN_OPEN` requirement |
| Two disjoint closed spheres, expected count two | Pass closed-amigurumi preflight; solver still decides construction relationship |
| Two spheres touching at one vertex | Fail V1 intentional-contact support |
| Self-intersecting hourglass | Fail `E_INPUT` |
| Open garment sheet with four declared loops | Pass only when all four map uniquely to garment openings |
| Garment panel overlap | Fail; no implicit cloth-contact interpretation |
| Flat rectangle supplied as `MESH_3D` | Fail domain/profile compatibility; use `PLANAR_REGION` |
| Lace planar region with intended holes | Validate under lace planar profile; do not run closed-surface rules |

## Output evidence

V0 evidence records source hash, selected profile, numerical-profile ID, parser/version, exact and numerical predicates, normalization events, derived normalized-artifact hash, component/boundary summaries, and diagnostics. Any required predicate that is unsupported, ambiguous, indeterminate, or fails prevents V1 from running.
