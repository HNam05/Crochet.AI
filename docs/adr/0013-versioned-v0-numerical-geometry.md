# ADR-0013: Versioned V0 numerical geometry policy

- Status: Accepted
- Date: 2026-08-31

## Context

V0 needs tolerance-sensitive area, distance, volume, contact, and landmark classifications. Hidden epsilons, fixed world-unit floors, or library defaults would make results scale-dependent and non-reproducible.

## Decision

DesignSpec V1 resolves `preflight_numerical_profile_id = v0_num_mesh_binary64_v1` to immutable profile version `1.0.0`. Integer incidence and topology remain exact. Orientation/coplanarity signs require filtered adaptive predicates that certify the exact sign of accepted binary64 inputs. Threshold comparisons use certified intervals or conservative bounds and return `INDETERMINATE` when they cannot establish a side.

The characteristic length is the certified maximum Euclidean distance between any two canonical mesh vertices, `L`, in millimetres. Geometric quantities use translation-invariant differences normalized by the corresponding power of `L`; a rounded normalized mesh is not authoritative. V1 uses relative, exactly representable powers-of-two bootstrap thresholds with no hidden absolute floor. Any changed value, operator, boundary rule, predicate certification requirement, or scale definition creates a new profile ID.

## Alternatives

- A global fixed millimetre epsilon was rejected because uniform scaling changes classification.
- An axis-aligned bounding-box diagonal was rejected because rigid rotation changes it.
- Median edge length was rejected because tessellation density and local edge distribution can change the global policy scale.
- Machine epsilon or a geometry-library default was rejected because neither states a domain acceptance policy.
- Exact rational arithmetic for every distance and derived norm was rejected as unnecessary for V0; certified filters/intervals preserve fail-closed decisions with a simpler implementation boundary.
- Guessing uncertain signs or resolving landmark ties by iteration order was rejected as nondeterministic ambiguity repair.

## Consequences

V0 output records the resolved profile hash and predicate backend/version. Computational passes under bootstrap thresholds are at most `EXPERIMENTAL` until calibration supports stronger claims. Threshold calibration may proceed independently without changing the mesh representation or weakening historical results.
