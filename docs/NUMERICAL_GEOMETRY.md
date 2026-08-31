# Versioned numerical geometry policy

## Registry and immutability

This document is the normative registry for tolerance-sensitive V0 mesh predicates. Domain profiles in [`MESH_PREFLIGHT.md`](MESH_PREFLIGHT.md) define **what** topology is required. A numerical profile defines **how** floating geometric classifications are made. The two identifiers are independent and both are required.

The V1 DesignSpec registry contains exactly:

| Profile ID | Profile version | Machine-readable record | Canonical record SHA-256 |
| --- | --- | --- | --- |
| `v0_num_mesh_binary64_v1` | `1.0.0` | [`../profiles/v0-mesh-numeric-profile-1.json`](../profiles/v0-mesh-numeric-profile-1.json) | `6d93723875f28f31dd0c36a4b47d26bf5b22c43e5d863cc51980d6edd2af24fc` |

An ID is immutable. Any changed value, operator, robust-predicate requirement, scale definition, or boundary behavior requires a new ID and profile record. Missing, unknown, malformed, hash-mismatched, or implementation-unsupported profiles make V0 `INDETERMINATE` with `E_INPUT`; they never select a default.

The JSON record conforms to [`../schemas/numerical-geometry-profile.schema.json`](../schemas/numerical-geometry-profile.schema.json) and its recorded hash uses `V0_NUMERICAL_GEOMETRY_PROFILE_JSON_V1` from [`CANONICALIZATION.md`](CANONICALIZATION.md). Documentation here supplies the semantic rules that schema alone cannot prove.

## Arithmetic and characteristic scale

Canonical coordinates are finite IEEE-754 binary64 millimetres. Exact index predicates never use a tolerance. Floating geometry first uses a deterministic characteristic length

```text
L = max(distance(p_i, p_j) for all canonical vertex identities i < j) millimetres.
```

This mesh vertex diameter is a semantic maximum, independent of vertex order. Its implementation may use a certified spatial acceleration structure, but pruning must use proven upper bounds and must return the same certified maximum as exhaustive pairs; otherwise V0 is `INDETERMINATE`. Distance evaluation uses overflow/underflow-safe scaled arithmetic with a certified interval. If there are fewer than two geometrically distinct positions, if the maximum cannot be certified, or if `L` is non-finite or `L <= 0`, V0 cannot pass. Exact coordinate-equal identities still receive the more specific coincidence failure.

Geometric quantities use translation-invariant coordinate differences and are divided by the corresponding power of `L`; no rounded normalized mesh is authoritative. This relative-only model has no hidden world-unit epsilon. Vertex diameter and every normalized quantity are invariant under rigid translation/rotation and covariant under positive uniform scaling and equivalent unit conversion, subject to representable inputs and certification.

**ENGINEERING DECISION:** V1 uses powers-of-two dimensionless thresholds. They are exactly representable binary64 bootstrap safety classifications, not physically calibrated acceptance thresholds. Calibration or a wider/narrower policy requires a new profile ID.

## Robust predicate tiers

Every implementation records the predicate backend/version and conforms to these semantic tiers:

1. **PROVEN / exact combinatorial rule:** IDs, index ranges, edge incidence, link topology, duplicate identity sets, and boundary connectivity use integer logic only.
2. **ROBUST NUMERICAL ALGORITHM:** signs for 2D/3D orientation and coplanarity use a filtered adaptive predicate with a certified exact sign for the accepted binary64 inputs. Fast floating filters may return a sign only when their error bound proves it; otherwise they increase precision. A library name is not semantics.
3. **TOLERANCE-BASED ENGINEERING CLASSIFICATION:** area, distance, volume stability, and landmark eligibility compare certified intervals or conservatively bounded values against this profile. If the result cannot be certified to one side of a threshold, the predicate is `INDETERMINATE`, never a guessed pass.

The robust strategy is consistent with Jonathan Richard Shewchuk, *Adaptive Precision Floating-Point Arithmetic and Fast Robust Geometric Predicates*, Discrete & Computational Geometry 18 (1997), 305–363, DOI `10.1007/PL00009321`. Publication mathematics may inform a clean implementation; no external source code or undocumented library behavior is adopted by this contract.

Triangle/segment intersection must be constructed from certified orientation/coplanarity signs plus deterministic lower-dimensional overlap tests. Signed volume uses canonical face order, a deterministically recorded component reference point, compensated or expansion summation, and a conservative accumulated error bound. Minimum-distance classifications use a certified/conservative bound; an uncertified result at the threshold is indeterminate.

## `v0_num_mesh_binary64_v1`

The `<=` failure/eligibility boundaries are inclusive. Signed-volume reliability is deliberately exclusive and requires `> volume6_normalized_min_exclusive`.

| Field | Quantity and units | Threshold/operator | Required outcome |
| --- | --- | --- | --- |
| `triangle_area2_normalized_max` | `||cross(p1-p0,p2-p0)|| / L^2`, dimensionless doubled area | `<= 2^-40` | face is near-zero/degenerate, `FAIL/E_INPUT` |
| `coordinate_distance_normalized_max` | certified Euclidean distance between distinct vertex coordinates divided by `L` | `<= 2^-40` | numerically coincident, `FAIL/E_INPUT`; exact equality is also reported |
| `near_contact_distance_normalized_max` | certified minimum distance between non-adjacent primitives divided by `L` | `<= 2^-40` | same-component or forbidden inter-component near contact; hard failure |
| `volume6_normalized_min_exclusive` | `abs(6 * signed_volume) / L^3`, dimensionless | pass sign reliability only when `> 2^-36` and the certified sign interval excludes zero | otherwise `INDETERMINATE/E_INPUT` with `geometry.orientation_indeterminate` |
| `landmark_numeric_slack_normalized_max` | numerical assignment slack divided by `L` | `2^-40` | added only to the declared landmark tolerance for eligibility and tie classification |

The exact decimal values are stored in the machine-readable profile. There is no generic `EPSILON`.

### Triangle degeneracy

Repeated vertex indices are exact failures. For three distinct indices, a certified exact collinearity result is geometric zero area. Independently, normalized doubled area at or below `2^-40` fails as near-zero. A comparison interval straddling the threshold is indeterminate and prevents pass. Extremely skinny but above-threshold triangles are retained; the report records the minimum normalized area as evidence.

### Coordinate coincidence

Same vertex ID is topology, not coincidence. Distinct IDs with bitwise/canonical numeric equal positions are exact coordinate coincidence. Otherwise a certified normalized distance at or below `2^-40` is numerical coincidence. Both fail, and neither permits welding. A distance interval straddling the threshold is indeterminate.

### Contact and intersection

Certified orientation/coplanarity signs first classify exact relations:

| Relation | Same component | Different components |
| --- | --- | --- |
| Exact intended shared edge/vertex only | permitted adjacency, subject to manifold checks | not applicable because identities do not cross components |
| Proper non-adjacent intersection | `FAIL/E_INPUT` | `FAIL/E_INPUT` |
| Vertex-face or edge-edge touch | `FAIL/E_INPUT` | `FAIL/E_UNSUPPORTED_FEATURE` |
| Coplanar positive-area overlap | `FAIL/E_INPUT` | `FAIL/E_INPUT` |
| Coincident triangles | `FAIL/E_INPUT` | `FAIL/E_INPUT` |
| Disjoint distance `<= 2^-40 * L` | `FAIL/E_INPUT` | `FAIL/E_UNSUPPORTED_FEATURE` |

For adjacent triangles, the implementation subtracts the intended shared entity from the relation test; any remaining overlap/contact fails. A certified disjoint distance greater than the threshold passes this predicate. An ambiguous sign or distance interval yields `INDETERMINATE/E_INPUT`. Garment and amigurumi mesh profiles use the same V1 contact table; legitimate garment boundaries do not authorize panel contact.

### Volume and outward orientation

Only a closed, combinatorially orientable, consistently wound component is eligible. Compute a certified interval for normalized signed six-volume. If the interval excludes zero and its minimum absolute magnitude is strictly greater than `2^-36`, the sign is reliable. Positive is canonical outward; reliable negative permits one recorded whole-component reversal. Equality, an interval touching zero, or magnitude `<= 2^-36` is `ORIENTATION_INDETERMINATE`; no reversal occurs.

### Landmark-to-boundary assignment

For landmark `k` with declared `tolerance_mm = t_k`, compute each loop's certified minimum distance `d(k, loop)` in canonical loop order. The eligibility threshold is

```text
T_k = t_k + 2^-40 * L.
```

A loop is eligible when its certified upper distance bound is `<= T_k`. A certified lower bound `> T_k` is ineligible. A bound straddling `T_k` is ambiguous. Zero eligible loops fails unmatched; more than one eligible loop or any threshold ambiguity fails ambiguous. One eligible loop assigns the landmark. Opening assignment then requires every landmark of exactly one compatible `REMAIN_OPEN` opening on that loop; multiple complete matchings fail. Canonical ordering is diagnostic only and never resolves a semantic tie.

## Deterministic evidence

V0 records `L`, normalized extrema, every threshold field/value/operator, predicate backend/version, uncertified predicate count, minimum area/distance/volume margins, landmark candidate sets, and the profile record hash. Diagnostics use canonical mesh identities after source maps are retained. Translation/rotation, source renumbering/order, and positive uniform scale with corresponding unit/tolerance conversion preserve classification. Threshold tests include the representable values immediately below, exactly at, and immediately above each boundary.

## Known limits and future versions

This profile classifies binary64 triangle surfaces; it is not a manufacturing clearance, cloth-thickness, or collision model. The relative-only scale deliberately rejects features below its normalized safety bands. Large-coordinate cancellation, nearly coplanar arrangements, and tiny signed volumes must be certified by the robust backend or become indeterminate. Future calibrated thresholds, physical thickness/contact, or alternative exact kernels require new profile IDs and benchmark evidence.
