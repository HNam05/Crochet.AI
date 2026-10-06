# 0017: Explicit analytic meridian coordinates

Status: accepted implementation decision, 2026-10-06.

## Problem and alternatives

The existing ordered radius/arclength profile leaves axial movement signs
undetermined. Inferring positive movement would silently choose a different
surface for reentrant shapes. Adding a sign to each segment would still require
recovering axial coordinates through square roots and a new numeric error policy.
Accepting both arclength and axial positions would add redundant coordinates
whose general exact consistency is not representable in binary64.

## Decision

DesignSpec 1.2 adds ordered physical radius/axial knots under a new coordinate
canonical profile. The ideal meridian is piecewise linear; its actual coordinates
are authoritative. Full axial extent binds AXIAL_LENGTH. Arclength is a future
derived solver quantity, under a separately recorded numeric contract.
The new schema retains old forms, and old schemas/hashes/goldens remain frozen.
There is no automatic upgrade, sign inference or cap insertion.

The first adapter supports simple closed pole-ended meridians and explicit signed
cardinal frames. Exact rational segment predicates and bounded cardinal witness
checks provide ideal-target V0 evidence. They do not certify a sampled mesh,
smoothness, physical stitchability or candidate geometry fidelity. See the
[normative contract](../ANALYTIC_COORDINATE_TARGET_V1.md) for scope and budgets.

## Consequences and independent boundaries

Generation from the new profile is deliberately unsupported until its separate
solver package is implemented. The only solver-side change is an explicit
admission guard, preventing old code from interpreting axial coordinates as
arclength. Search/replay, CrochetIR and target-free physical simulation are
unchanged. The new target-side checks are independently reviewed using
hand-authored crossing, contact, overlap, nonmonotone and signed-frame cases.

Generic/arbitrary-axis/open target domains, sampling/V7 comparison and physical
acceptance remain separate work. No frozen golden is added or regenerated.
