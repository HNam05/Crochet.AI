# Fixture index

`schema-valid/` contains minimal positive JSON Schema examples for the current
`MaterialProfile`, `DesignSpec`, and `CrochetIR` contracts. They protect the
invariant that each published schema admits at least one deliberately small,
well-formed instance. These fixtures are schema-shape examples only: they are
not golden outputs, do not assert graph-wide semantic validity, and must never
be auto-updated.

Planned fixtures include sphere, cylinder, cone, ellipsoid, hourglass, thin-neck invalid, two-lobe, Y-branch, two-leg split, torus/handle, non-manifold mesh, self-intersecting mesh, unreachable transition, color transition, and human-pattern round trip cases. See [`../../docs/BENCHMARKS.md`](../../docs/BENCHMARKS.md) for acceptance contracts.
