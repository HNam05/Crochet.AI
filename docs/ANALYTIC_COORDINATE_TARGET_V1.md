# Explicit analytic meridian coordinates V1

## Scope and version boundary

DesignSpec `1.2.0` adds an explicit coordinate profile for
`SURFACE_OF_REVOLUTION`. Frozen 1.0/1.1 schemas, radial-profile hashes and native
primitive target adapters remain unchanged. Existing radius-versus-arclength
profiles do not determine axial movement signs and are never backfilled.

The initial admission package admits an ideal closed piecewise-linear surface of revolution for
target inspection and V0. It does not generate CrochetIR from this new profile,
provide a sampled mesh or V7 distance certificate, or establish physical validity.
That checkpoint deliberately rejected generation. The separate producer contract
[ANALYTIC_COORDINATE_GENERATION_V1](ANALYTIC_COORDINATE_GENERATION_V1.md) now
extends generation; the target admission and independent V7 boundaries stay intact.
Forward simulation remains target-free.

## Authoritative input

The existing `radial_profile` field uses the new discriminator
`SURFACE_OF_REVOLUTION_COORDINATE_PROFILE_CANONICAL_JSON_V1`. Its closed payload
contains `canonicalization_profile`, `samples`, `start_boundary`, `end_boundary`
and `sha256`. Each ordered sample contains exactly `sample_index`, `radius_mm`
and `axial_mm`; indexes are contiguous from zero. There are 3 to 129 samples.
Coordinates are finite represented binary64 values in millimetres; radius is
nonnegative, axial position may be signed. No arclength field is accepted.

The coordinate is relative to `origin_mm` along explicit `axis_direction`.
`AXIAL_LENGTH` is the sole parameter for this profile, exactly equal to the finite
binary64 evaluation of `max(axial_mm) - min(axial_mm)` and strictly positive.
This is extent, not endpoint displacement. Native parameters and old profiles
retain their existing definitions. DesignSpec 1.2 also retains older inputs.

The profile hash excludes only its own `sha256`; all samples and boundaries are
hashed in supplied order under the new canonical profile using the normative
domain separation in `CANONICALIZATION.md`. No sorting, reversal, coordinate
rounding, sign inference or synthesized caps is permitted. Canonical DesignSpec
identity includes the new version and complete authoritative profile.

## Bounded target admission

`ANALYTIC_COORDINATE_TARGET_V1` initially supports AMIGURUMI_3D, CLOSED targets,
two `CLOSED_POLE` boundaries, and a cardinal `axis_direction` exactly matching the declared
signed frame up axis. Other axes, open boundaries and domains return explicit
`NOT_APPLICABLE`. Boundary references still undergo ordinary semantic validation.

Admission requires distinct endpoint poles with zero radius, strictly positive
interior radii, no zero-length segment, and a simple ordered meridian polyline.
Every pair of segments is tested using exact rational predicates on represented
binary64 coordinates. Adjacent segments may share only their common endpoint;
backtracking overlap is rejected. Nonadjacent intersection, touching or overlap
is rejected, including repeated nonadjacent knots. Axial movement need not be
monotone. Explicit horizontal segments describe disk caps; no cap is invented.

At most 128 segments produce at most 8,128 unordered pair checks. The fixed
129-knot limit bounds this exact O(n^2) admission workload; it is an engineering
budget owned by the target adapter, not a geometric tolerance. No epsilon or
physical tolerance enters the predicates. Immutable metadata records the
algorithm, limit and performed pair count.

The signed orthonormal cardinal frame determines world positions. Pole positions
and four cardinal positions at every positive-radius knot must be finite and
distinct after binary64 transformation. Overflow and translation-induced collapse
are explicit invalid-input failures; unsupported representation is not a pass.
These checks cover only the named pole/cardinal witnesses. They do not certify
that every interior/non-cardinal point stays distinct in a binary64 sampler.
Finite positive characteristic length is `max(2 * max(radius_mm), axial_extent)`.

A simple meridian whose only axis contacts are distinct endpoint poles sweeps an
embedded connected closed genus-zero ideal surface. Its topology is one component,
zero boundary components, genus zero and Betti numbers (1, 0, 1). This assertion
concerns the mathematical piecewise-linear sweep, not a rendered or sampled mesh.
Indeed, equality of swept points implies equality of their meridian radius/axial
pair, then equality of the meridian parameter by simplicity and of the angle
modulo a full turn. Only the two endpoint circles collapse to their distinct
poles. The resulting interval-times-circle quotient is a sphere; its continuous
injection into three-dimensional space is an embedding by compactness. Corners
and explicit disk caps do not imply smoothness or physical stitchability.

## Evidence and failure policy

Target metadata binds the complete DesignSpec and profile hashes, immutable
ordered coordinates, origin/frame, ideal topology, characteristic length and
admission algorithm/work budget. Metadata `coordinates_mm` contains ordered
`[radius_mm, axial_mm]` pairs in the declared local frame, not world-space points.
Its own SHA-256 uses the new target version as
a domain-separated profile, excluding only its own hash. `to_dict` returns a fresh
value so callers cannot mutate admitted evidence.

V0 uses a separate versioned scope and assertion set for this adapter. Proven
coordinate contradictions yield FAIL/E_INPUT; unsupported scope yields
INDETERMINATE/E_UNSUPPORTED_FEATURE. Existing primitive V0 scope is unchanged.
Overall verification remains NOT_VERIFIED and physical testing UNTESTED.

The initial admission package added only an unsupported-profile generator guard.
Its subsequent replacement is governed by the separate producer contract above.
No count/phase replay, CrochetIR semantics, forward model,
golden fixture or existing target primitive proof is changed. Target-side V0
admission and the generator guard require separate review and adversarial tests;
target admission must never imply generative or physical acceptance.

## Acceptance checks

Admit hand-authored capped cylinder, cone, convex and simple nonmonotone meridians.
Reject crossing, exact touching, adjacent overlap, interior poles, malformed
indexes/hash/extent, oversized profiles, nonfinite arithmetic and translated
collapse. Exercise signed axes and source mutation; old ambiguous profiles remain
unsupported. Verify schema routing, API/V0 delivery, installed schema inclusion,
and structured generator rejection without modifying old canonical vectors.

The separate generator package records its own numerical arclength policy;
coordinate target admission introduces none. Independent coordinate search replay
and bounded geometry comparison remain required before wider verification.
