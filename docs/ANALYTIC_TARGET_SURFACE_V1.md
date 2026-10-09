# Analytic target surface discretization V1

`ANALYTIC_TARGET_SURFACE_V1` converts an already admitted `AnalyticTarget` or
`AnalyticCoordinateTarget` into a bounded `IndexedTriangleMeshV1` approximation.
It is target-side comparison input. The module does not import or call the
forward simulator, and mesh production does not prove V0, certify the ideal
surface, or establish physical validity.

## Inputs and deterministic policy

The caller supplies the exact DesignSpec, its admitted analytic target, a
`SemanticValidator`, and one closed policy object. The adapter revalidates and
re-admits the DesignSpec, then requires the result and canonical DesignSpec hash
to match the supplied immutable target. It records both the full DesignSpec JCS
bytes and SHA-256 and the canonical DesignSpec identity.

Policies use `profile = ANALYTIC_TARGET_SURFACE_SAMPLING_V1` and
`schema_version = 1.0.0`. Sphere and equal-axis ellipsoid inputs require exactly
`ring_count` and `azimuth_sectors`, with ranges 2–64 and 4–64. Coordinate
revolution inputs require exactly `linear_segment_subdivisions` and
`azimuth_sectors`, with ranges 1–8 and 4–64. Booleans are not integers for these
fields. Unknown, missing, or target-inappropriate fields fail closed.

The sampler computes output counts before allocating coordinates. It enforces
512 vertices and 1,024 faces. With `R` meridian intervals and `S` sectors, the
counts are `2 + (R - 1)S` vertices and `2S(R - 1)` faces. The shared pole
vertices occur once each, adjacent azimuth sectors share ring vertices, and
faces wrap across the seam by index. Coordinate profiles retain every authored
meridian knot; optional subdivision inserts exact rational linear interpolants
before binary64 conversion.

The frame basis is copied from admitted target semantics and transformed with
the DesignSpec origin. The emitted source mesh uses the DesignSpec's exact
`coordinate_frame_id`, millimetres, and right-handed basis. A signed exact
volume predicate over represented binary64 mesh coordinates chooses the one
global orientation that yields positive enclosed volume; exact zero volume or a
zero-area triangle rejects. An independent combinatorial audit must then report
one closed component with sphere Betti numbers `(1, 0, 1)`.

## Approximation and evidence

The mesh is serialized as JCS `IndexedTriangleMeshV1` bytes and retains those
bytes plus their SHA-256. Artifact identity binds the analytic target, canonical
and JCS DesignSpec hashes, source coordinate-profile hash when applicable,
sampling policy, output-mesh hash, topology-audit hash, poles, and authored knot
representatives. The complete triangulation and vertex table are retained.

The reported analytic discretization bound is for the exact-real parameterized
surface and its linear triangle interpolation. For the analytic latitude grid,
with equatorial radius `a`, polar radius `b`, latitude spacing `dt = pi/R`, and
azimuth spacing `dp = 2pi/S`, it uses
`0.5 * (a + max(a,b)) * (dt^2 + dp^2)` millimetres. This bounds the second
derivatives of the ellipsoid parameterization over each parameter triangle.
For an explicit meridian with maximum subdivided segment length `L`, maximum
radius `r`, and azimuth spacing `dp`, it uses
`L*dp + 0.5*r*dp^2` millimetres; each meridian strip is linear and only its
azimuthal interpolation is curved.

The formula describes discretization only; binary64 trigonometric and
coordinate-rounding error is excluded from that bound. Evidence labels this
scope explicitly and sets `ideal_surface_certificate` and `v0_certificate` to
`NOT_PROVIDED`. The bound is not an ideal-surface acceptance threshold, a V0
intersection proof, or physical evidence. Numerical collapse and exact
degeneracy are rejected, not repaired.

## Work and failure states

Sampling work is linear in emitted vertices and faces. Policy bounds are checked
before allocation; exact triangle checks and topology auditing are bounded by
the 512/1,024 caps. Invalid target binding, malformed policy, non-finite or
collapsed coordinates, zero volume, degenerate triangles, mesh-cap overflow,
and topology failure raise `AnalyticTargetSurfaceError` with a stable code and
reason. No partial mesh is returned.
