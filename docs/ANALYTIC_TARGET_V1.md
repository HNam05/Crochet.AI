# Analytic target adapter V1

## Scope and admission

`ANALYTIC_TARGET_V1` is an immutable target-side decoding adapter for semantically valid `AMIGURUMI_3D` DesignSpecs whose target is a closed `SPHERE` or `ELLIPSOID`. It is not a solver, mesh, forward-model input or independent V0 evidence record. The verification pipeline uses its explicit ideal-primitive predicates for the supported analytic V0 gate; sampling alone does not prove V0. Admission first calls `SemanticValidator.validate_design_spec`; a failed report raises `AnalyticTargetError` with `INVALID_SOLVER_INPUT`. Unsupported applicability raises the same exception with `NOT_APPLICABLE`.

`CYLINDER` and `CONE` are inapplicable because V1 does not define their construction-interface or cap semantics. `SURFACE_OF_REVOLUTION` is inapplicable because an ordered nonnegative `r(s)` profile does not encode axial signs. For example, the symmetric profile `(s,r) = (0,0),(5,3),(10,0)` admits axial increments `(+,+),(+,-),(-,+),(-,-)` with magnitude four; the target schema does not select one. The adapter never guesses a positive axis or disk caps. Sphere and ellipsoid admission also requires `surface_mode = CLOSED` and rejects a target opening declared `REMAIN_OPEN`.

## Canonical metadata

Metadata records the full validated DesignSpec hash using `DESIGN_SPEC_CANONICAL_JSON_V1`, target primitive, center in millimetres, signed orthonormal frame basis, semiaxes, ideal topology, and the largest full extent. The target metadata digest is SHA-256 over:

```text
ASCII("Crochet.AI") || NUL || ASCII("ANALYTIC_TARGET_V1") || NUL || JCS(metadata_without_sha256)
```

The ideal sphere and ellipsoid have one connected component, zero boundary components, genus zero, and Betti numbers `(1, 0, 1)`. The frame uses the declared `up_axis` as `a`; it derives `right_axis = cross(up_axis, front_axis)` and `second_axis = cross(up_axis, right_axis)`. Thus `right_axis`, `second_axis`, `up_axis` is right-handed. Basis axes are exact signed integer coordinate vectors, not fitted directions.

For a sphere, both radii equal its resolved `RADIUS`; an ellipsoid uses `EQUATORIAL_RADIUS` and `POLAR_RADIUS`. `characteristic_length_mm = 2 * max(equatorial_radius_mm, polar_radius_mm)` is the largest full extent reported by this adapter. A later V7 metric profile owns its own characteristic length, commonly a bounding-box diagonal; this adapter value is not a V7 override.

## Bounded sampling

`sample(ring_count, sector_count)` emits the `ANALYTIC_TARGET_LATITUDE_AZIMUTH_GRID_V1` latitude/polar and azimuth grid in millimetres. The algorithm ID is included in the sampled-cloud hash. Both counts are explicit integers: `2 <= ring_count <= 256` and `4 <= sector_count <= 256`. The point count is `2 + (ring_count - 1) * sector_count` and must not exceed 65,536. The two poles are emitted once each. Even ring counts include the exact equator; sector counts divisible by four include exact quarter-turn azimuths. Pole, equator, and quarter-turn trigonometric values are assigned exactly to zero or one where applicable.

Every computed local and translated coordinate must be finite in binary64. Repeated local grid coordinates or translation-induced coordinate collapse fail with `INVALID_SOLVER_INPUT`; no tolerance or repair is applied. These checks prevent representational collapse in this finite sample. They do not establish a geometric error bound.

The parametric grid is not equal-area and does not provide certified Hausdorff coverage, V0 proof, a certified surface representation, or physical evidence. Its point cloud has a separate SHA-256 domain from the analytic target metadata and includes the target hash and both sampling counts. A sampled cloud or its digest must not be treated as the ideal surface identity.

## Numeric domain and failures

Input numeric values have already passed the DesignSpec schema and semantic validator. Radii must remain positive and finite after Python binary64 conversion. Origin coordinates and the derived largest full extent must be finite; overflow or invalid derived dimensions reject. Admission also evaluates the six cardinal surface points and rejects non-finite or coincident binary64 positions, including collapse against the center. Positive subnormal radii remain admissible when all six cardinal points are representable and distinct; a denser requested sampling grid can still reject if its points collapse.

Sampling uses binary64 arithmetic, exact integer frame transforms, Python `math` trigonometric functions for non-cardinal angles, and no numerical tolerance. Bit-for-bit sampled point/hash reproducibility is scoped to the same Python implementation, version, platform math library, and IEEE 754 binary64 behavior. The adapter makes no cross-runtime promise for non-cardinal trigonometric results. Overflow, non-finite coordinates, duplicate grid coordinates, invalid count types, and out-of-range budgets all reject. `bool` is not accepted as an integer count.

This adapter makes no claim about stitch counts, course placement, fit, finite discretization error, material response, V0 mesh eligibility, or V7 thresholds. Those remain owned by their separate solver and verification contracts.

## API and CLI

API 1.0 `inspect_analytic_target` requires exactly `design_spec` and the resolved
`material_profile` in addition to the API version/operation. The resolved material
must match its DesignSpec binding. The response contains metadata, not the sampled
cloud, and retains `NOT_VERIFIED` / `UNTESTED`. Generic CLI `request` and durable
jobs expose the same operation. Sampler counts are explicit only in the internal
target-side interface; they cannot become forward-model inputs.
