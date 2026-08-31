# ADR-0010: Domain-specific V0 preflight profiles

- Status: Accepted
- Date: 2026-08-31

## Context

A closed stuffed mesh, an open garment sheet, a planar blanket region, and a lace motif graph have incompatible validity predicates. A universal watertightness flag cannot represent them safely.

## Decision

V0 selects a versioned profile from project domain plus target-geometry kind. Amigurumi has separate closed and declared-boundary mesh profiles; garments use a declared-boundary sheet profile; flat and lace V1 reject `MESH_3D` and use planar/motif profiles. Mesh profiles require orientable two-manifolds, exact declared component/boundary counts, no self-intersection, and no inter-component contact. Only lossless deterministic normalization is permitted.

Target boundary loops map one-to-one to `REMAIN_OPEN` DesignSpec opening requirements. Construction-time openings that later close are not target boundaries. Numerical geometry checks require an explicit unit-bearing profile.

## Alternatives

- One strict closed-mesh policy was rejected because it excludes garments and intentional openings.
- One permissive policy was rejected because it silently admits holes, contacts, and non-manifold ambiguity.
- Automatic mesh repair was rejected because it changes the design input and invalidates provenance.

## Consequences

V0 remains independent of solver choice and CrochetIR. Multiple components are allowed only by exact declaration and do not dictate construction components. Future garment thickness/contact or 3D lace blocking needs a new profile rather than weakening V1.
