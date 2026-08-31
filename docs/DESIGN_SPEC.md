# DesignSpec Contract

Normative schema: [`schemas/design-spec.schema.json`](../schemas/design-spec.schema.json)

## Purpose and authority

`DesignSpec` is the strict boundary between interpretation and deterministic compilation. It records design intent, referenced target geometry, measured dimensions, material binding, construction constraints, solver budgets, and verification requirements.

**ENGINEERING DECISION:** Natural-language or image systems may propose a `DesignSpec`; their output remains untrusted until schema and semantic validation pass.

**PROVEN / FORMAL:** `DesignSpec` contains no authoritative final stitch quantities, per-course quantities, increase placement, or decrease placement. The closed schema rejects undeclared fields, including attempted count fields. Authoritative construction first appears as explicit nodes and references in `CrochetIR`.

**ENGINEERING DECISION:** Unresolved ambiguity is represented only by rejection. `interpretation_provenance.unresolved_ambiguities` must be empty; assumptions must be individually recorded as user-confirmed or an explicit versioned-profile default.

## Version and identity

- `schema_version` is exactly `1.0.0`.
- `design_spec_id` is an ASCII identifier beginning `ds_`.
- All content-addressed references use lowercase SHA-256 hex.
- All lengths are finite millimetre values. Masses, where present in bound profiles, are grams.
- Object boundaries are closed with `additionalProperties: false`; extension requires a schema-version change.

**ENGINEERING DECISION:** IDs provide reference identity; hashes provide content identity. A resolver must reject an ID whose resolved bytes do not match the declared hash.

## Required sections

| Field | Contract |
| --- | --- |
| `project_type` | `AMIGURUMI_3D`, `GARMENT`, `FLAT`, or `LACE_MOTIF` |
| `dimensions` | Named positive measurements with `value_mm` and non-negative `tolerance_mm`; measurement IDs are reference targets |
| `target_geometry` | A typed analytic, mesh, planar, garment-measurement, or motif-graph target |
| `symmetries` | Explicit frame, origin, axis/normal, order, and tolerance |
| `landmarks` | Explicit target-frame positions, tolerances, and perceptual importance |
| `material_profile` | Inline `MaterialProfile` or content-addressed profile reference |
| `construction_constraints` | Hard geometry gate, seam/cut/reattachment limits, join methods, and declared openings |
| `colors` | Stable color IDs, display sRGB values, and semantic roles |
| `difficulty_constraints` | Allowed canonical stitches, shaping, operations, and active-frontier limit |
| `solver_options` | Allowed/preferred solver families, deterministic seed, and deterministic search budgets |
| `verification_requirements` | Mandatory gates, metric stack, threshold profile, robustness/export requirements, and physical status floor |
| `domain_constraints` | Strict domain-specific intent |
| `interpretation_provenance` | Authoring mode, producer, source hashes, and resolved assumptions |

The schema intentionally has no generic options map. New solver or domain options require a reviewed schema revision rather than silently changing compiler behaviour.

## Target geometry

The allowed discriminated variants are:

- `MESH_3D`: content-addressed mesh, right-handed coordinate frame, domain-compatible V0 preflight profile, numerical-profile ID, and exact topology/boundary policy;
- `ANALYTIC_SHAPE`: `SPHERE`, `CYLINDER`, `CONE`, `ELLIPSOID`, or `SURFACE_OF_REVOLUTION`, with a typed, complete primitive parameter binding and explicit origin;
- `PLANAR_REGION`: content-addressed 2D region in a declared frame;
- `GARMENT_MEASUREMENTS`: references to body measurements;
- `MOTIF_GRAPH`: content-addressed target topology.

Domain compatibility is schema-enforced: amigurumi accepts analytic or 3D mesh targets; garments accept measurements or a 3D mesh; flat work accepts a planar region; lace accepts a motif graph or planar region.

### Analytic primitive parameters

`target_geometry.parameters` is a set keyed by `parameter`; every entry binds that named parameter to one declared measurement. Semantic validation resolves the measurement, confirms its positive millimetre value, and rejects an extra, missing, or duplicate parameter. Required parameter sets are exact:

| Primitive | Exact parameters | Additional fields |
| --- | --- | --- |
| `SPHERE` | `RADIUS` | `origin_mm` only |
| `CYLINDER` | `RADIUS`, `AXIAL_LENGTH` | `origin_mm` only |
| `CONE` | `BASE_RADIUS`, `AXIAL_LENGTH` | `origin_mm` only; the opposite end has zero radius |
| `ELLIPSOID` | `EQUATORIAL_RADIUS`, `POLAR_RADIUS` | `origin_mm` only; polar radius follows the frame up axis |
| `SURFACE_OF_REVOLUTION` | `MERIDIONAL_LENGTH` | `origin_mm`, non-zero `axis_direction`, and `radial_profile` |

`SURFACE_OF_REVOLUTION` is deliberately not a prose or fitted-curve placeholder. Its profile is a content-addressed, explicitly ordered value:

- `canonicalization_profile` is `SURFACE_OF_REVOLUTION_PROFILE_CANONICAL_JSON_V1`;
- `samples` are the authoritative meridional samples `(sample_index, s_mm, radius_mm)` in ascending `sample_index` order;
- `s_mm` starts at zero, increases strictly, and the final value equals the bound `MERIDIONAL_LENGTH` measurement; `radius_mm` is non-negative;
- `sha256` is the domain-separated `SURFACE_OF_REVOLUTION_PROFILE_CANONICAL_JSON_V1` digest defined in [`CANONICALIZATION.md`](CANONICALIZATION.md), computed over the profile payload excluding its own `sha256` field;
- each end is classified as `CLOSED_POLE`, `INTENTIONAL_OPENING`, or `CONSTRUCTION_INTERFACE`; an intentional opening carries its declared `opening_requirement_id`.

Semantic validation checks the sequence, hash, endpoint classification, unit/range rules, normalized axis direction, and that a `CLOSED_POLE` endpoint is within the versioned `radius_zero_tolerance_mm` of radius zero. The profile is target intent, not construction: it never contains stitch counts, course counts, shaping placement, or solver output.

**PROVEN / FORMAL:** Every measurement, landmark, frame, source artifact, and opening requirement reference must resolve uniquely to the declared type. JSON Schema cannot prove this graph-wide property; semantic validation must.

**ENGINEERING DECISION:** Target assets carry both a URI and hash. The URI is a retrieval hint; the hash is authoritative. Mesh preflight and normalization do not mutate the DesignSpec.

### Domain-specific V0 profile

The normative domain profiles and adversarial cases are in [`MESH_PREFLIGHT.md`](MESH_PREFLIGHT.md). Canonical mesh identity, source-adapter conversion, right-handed millimetre units, and zero-based indexing are in [`GEOMETRY_MODEL.md`](GEOMETRY_MODEL.md). A mesh target declares `preflight_profile_id`, `preflight_numerical_profile_id`, and a closed topology expectation containing exact component/boundary counts plus orientability, manifold, self-intersection, and inter-component-contact policies.

DesignSpec schema version `1.0.0` accepts exactly `preflight_numerical_profile_id = v0_num_mesh_binary64_v1`. The ID resolves through [`NUMERICAL_GEOMETRY.md`](NUMERICAL_GEOMETRY.md) to immutable version `1.0.0` and its machine-readable record. The implementation must validate and hash that record before V0; missing, unknown, malformed, hash-mismatched, or unsupported resolution is `INDETERMINATE/E_INPUT`, never an implicit default.

- Amigurumi selects `V0_AMIGURUMI_CLOSED_SURFACE_V1` or `V0_AMIGURUMI_DECLARED_BOUNDARY_SURFACE_V1` consistently with `surface_mode`.
- Garments select `V0_GARMENT_DECLARED_BOUNDARY_SURFACE_V1`.
- Flat and lace V1 do not accept `MESH_3D`; they use planar or motif-graph preflight.

Closed amigurumi requires zero mesh boundary loops. Declared-boundary profiles require at least one loop and a one-to-one, landmark-supported match to `closure_expectation = REMAIN_OPEN` opening requirements. A stuffing or assembly opening that closes during construction is not a target-mesh boundary. Multiple components are accepted only at the exact declared count; V1 forbids self-intersection and intentional inter-component contact.

## Materials and colors

`material_profile.binding_type` is either:

- `INLINE`, containing an object validated by `material-profile.schema.json`; or
- `REFERENCE`, containing `profile_id`, `revision`, and `sha256`.

The profile keeps effective stitch pitch and course pitch separate. Yarn/hook metadata alone is not accepted as measured gauge.

**HYPOTHESIS:** The V1 material profile and its uncertainty bounds adequately characterize first-order shape. This remains experimental until physical calibration.

Colors express intent, not canonical stitch terminology. A solver must preserve stable `color_id` references when compiling yarn sources and `COLOR_CHANGE` operations.

## Construction objective

`construction_constraints.priority_policy` is fixed to `GEOMETRY_GATED_SEAMLESS_LEXICOGRAPHIC_V1`, and `hard_geometry_gate_required` is always true. Candidate ordering is:

1. all mandatory structural/semantic gates pass;
2. all hard geometry thresholds pass;
3. minimize sewn seams;
4. minimize yarn cuts and reattachments;
5. minimize the versioned geometry-error vector;
6. minimize unnecessary construction complexity.

**PROVEN / FORMAL:** A candidate outside the hard geometry acceptance region cannot win by being more seamless.

Each intentional opening has a stable `opening_requirement_id`, purpose, boundary landmarks, and closure expectation. A CrochetIR opening may cite it. Unmatched terminal open frontiers fail unless another domain rule explicitly proves an intentional opening.

## Solver and verification controls

Solver options use deterministic work budgets (`max_candidate_evaluations`, `max_backtracks`, and `max_beam_width`) and a 32-bit seed. Wall-clock time is not a canonical selection input. If an operational timeout prevents completion, the solver reports failure rather than returning an unverified partial candidate.

`solver_family_preference` is an ordered subset of `allowed_solver_families`; semantic validation enforces the subset and project-type compatibility.

Verification requirements select V0–V10 gates, a versioned threshold profile, required geometry metrics, export round trip, collision, robustness, and minimum physical-validation status. Critical gates are conjunctive; no aggregate score can override a failure.

The schema enforces the following dependency profile, rather than leaving it to caller convention:

- `V0` through `V7` and `V10` are always mandatory. In particular, a schema-valid request cannot claim geometry acceptance while omitting independent forward simulation (`V6`) or target comparison (`V7`).
- `TOPOLOGY` and at least one non-topological geometry metric are always required; neither topology nor geometric fidelity can be hidden by a scalar summary.
- `require_material_robustness = true` requires `V8`; `false` forbids listing `V8` as required.
- `require_export_round_trip = true` requires `V9`; `false` forbids listing `V9` as required.
- `minimum_physical_validation` is evaluated at mandatory `V10`, including when its value is `UNTESTED`; it is a claimed evidence floor, not permission to omit provenance.

`require_collision_check` selects the collision assertion inside mandatory V6. A V6 result with an unresolved forbidden collision always fails, regardless of that flag.

## Domain constraints

- Amigurumi records stuffing level and whether the surface is closed or has declared openings.
- Garments record body-measurement references, signed ease allowances, and allowed garment constructions. A garment solver is mandatory.
- Flat work records rows/rounds/grid/C2C/motif structure and repeat policy.
- Lace records required primitive families. Requesting a family not supported by the active semantic profile fails capability validation.

**FUTURE:** Listing lace primitive families in the schema provides typed intent only. It does not claim implementation of picots, post stitches, clusters, puffs, bobbles, shells, or motif attachment semantics.

## Validation beyond JSON Schema

V1 semantic validation must additionally prove:

1. all IDs are unique within their typed namespaces and all references resolve;
2. coordinate-frame axes are distinct and form a valid right-handed frame;
3. analytic primitives have exactly the required parameter set, and a radial profile passes its ordering, endpoint, axis, and content-hash contract;
4. domain, target geometry, solver families, and domain constraints agree;
5. solver preference is a subset of allowed solvers;
6. source, material, target, and radial-profile hashes resolve to matching bytes;
7. opening boundary landmark references resolve;
8. requested techniques are implemented by the selected semantic profile;
9. every required tolerance is finite, non-negative, and has the unit declared by its field;
10. required gate dependencies and collision/robustness/export implications are consistent;
11. a mesh preflight profile is compatible with the project type and surface mode, with exact component/boundary policies and no undeclared contact/repair;
12. every mesh numerical-profile ID resolves to the exact immutable registry record required by this DesignSpec schema version;
13. no unresolved interpretation ambiguity or undeclared default exists.

Failure is structured and fail-closed; a validator must not insert defaults or repair ambiguity.

## Canonical form

**ENGINEERING DECISION:** `DESIGN_SPEC_CANONICAL_JSON_V1` first applies the following complete array registry, then the shared I-JSON/binary64/JCS/domain-separated SHA-256 contract in [`CANONICALIZATION.md`](CANONICALIZATION.md). Duplicate keys, non-finite or overflowing numbers, unsafe integers, invalid Unicode, and values outside schema/semantic bounds are rejected before hashing. “Set” means sort by the stated key; “ordered” means preserve supplied order exactly.

Before applying the DesignSpec-owned registry, an `INLINE` `material_profile.profile` is schema- and semantically validated and replaced in the working value by `CANONICAL_MATERIAL_PROFILE_PROJECTION_V1(profile)` from [`MATERIAL_MODEL.md`](MATERIAL_MODEL.md). This is recursive projection composition, not a second material normalizer: DesignSpec code must call the authoritative MaterialProfile projection and must not reproduce its collection rules. A `REFERENCE` binding is left as its declared ID/revision/hash object.

| Field | Canonical treatment | Key or order contract |
| --- | --- | --- |
| `dimensions.measurements` | Set | `measurement_id` |
| `symmetries` | Set | `symmetry_id` |
| `landmarks` | Set | `landmark_id` |
| `colors` | Set | `color_id` |
| `target_geometry.parameters` | Set | `parameter` |
| `target_geometry.radial_profile.samples` | Ordered | Ascending contiguous `sample_index`; never sorted independently |
| `construction_constraints.allowed_join_methods` | Set | Enum ordinal: `CROCHETED`, `SEWN` |
| `construction_constraints.intentional_openings` | Set | `opening_requirement_id` |
| `construction_constraints.intentional_openings[].boundary_landmark_ids` | Set | `landmark_id` |
| `colors[].roles` | Set | Unicode code-point order |
| `difficulty_constraints.allowed_stitch_types` | Set | Canonical stitch enum ordinal |
| `difficulty_constraints.allowed_shaping` | Set | Enum ordinal: `INCREASE`, `DECREASE` |
| `difficulty_constraints.allowed_construction_operations` | Set | Canonical operation enum ordinal |
| `solver_options.allowed_solver_families` | Set | Solver-family enum ordinal |
| `solver_options.solver_family_preference` | Ordered | Explicit solver priority; preserve supplied order |
| `verification_requirements.required_gates` | Set | Gate ordinal `V0` through `V10` |
| `verification_requirements.required_geometry_metrics` | Set | Metric enum ordinal |
| `domain_constraints.body_measurement_ids` | Set | `measurement_id` |
| `domain_constraints.ease_allowances` | Set | `measurement_id` |
| `domain_constraints.allowed_constructions` | Set | Garment-construction enum ordinal |
| `domain_constraints.required_primitive_families` | Set | Lace-primitive enum ordinal |
| `interpretation_provenance.source_artifacts` | Set | `artifact_id` |
| `interpretation_provenance.assumptions` | Set | `assumption_id` |
| `interpretation_provenance.unresolved_ambiguities` | Ordered and empty | Must contain no values |
| every `vector3` (`origin_mm`, axes, landmark positions) | Ordered | Coordinate tuple `[x, y, z]`; preserve component order |

No other DesignSpec-owned V1 field is an array. Arrays inside an inline MaterialProfile are owned exclusively by `CANONICAL_MATERIAL_PROFILE_PROJECTION_V1`; this registry is normative for the remaining complete DesignSpec value and the nested surface-of-revolution profile hash. A consumer must reject a nonconforming radial sample sequence rather than sorting it.

The canonical hash covers the complete DesignSpec, including the normalized inline MaterialProfile, recorded assumptions, and provenance. Material canonical bytes are embedded as a JSON value, not as the standalone MaterialProfile hash or as a JSON string. The enclosing hash therefore uses the DesignSpec domain separator while the same material projection may independently use the MaterialProfile domain separator. Locale, whitespace, object insertion order, harmless spellings such as `1`, `1.0`, or `1e0`, and reordering of material collections declared semantically unordered do not change the DesignSpec hash; different binary64 values or meaningful array order do.
