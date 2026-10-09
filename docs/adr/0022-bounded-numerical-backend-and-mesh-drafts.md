# ADR 0022: Bounded numerical backend and mesh drafts

Date: 2026-10-09. Status: accepted for experimental implementation only.

## Problem

The closed SC compiler and local pilot could deliver instructions, but the
mechanical diagnostics did not supply an auditable complete prediction or a
connected geometry/material-scenario check. Mesh admission alone could not
generate instructions. Calibration records also needed a clear distinction
between integrity, local review claims, and authenticated physical acceptance.

## Decision

Add separately versioned experimental profiles without changing canonical
schemas, approved goldens, existing project bytes or default verification.

`FORWARD_CLOSED_F0_V1` composes declared stretch, closure, pressure, shell and
contact terms on closed single-yarn SC cells. It runs every declared bounded
initialization, certifies continuous movements conservatively and exposes
geometry only on numerical convergence and agreement between observed modes.
It cannot consume target coordinates or target-derived initializations.

`FORWARD_CLOSED_F0_AUDIT_V1` reconstructs inputs and independently replays the
optimizer trace. It recalculates forces and path checks using shared, separately
tested constitutive/contact kernels. Every start and the winning coordinates
must match canonical replay exactly. Comparison tolerances cannot authorize
replacement geometry. Work ceilings and consumed work remain visible on failure.
This is independent optimizer replay, not independent physical identification.

An optional `NUMERICAL_VERIFICATION_CONTEXT_V1` connects fresh F0 and replay,
the full declared sampled metric vector, five finite material endpoint cases,
and source/export consistency to V6/V7/V8/V10. Target data appears only in V0
and post-solve comparison. Analytic targets retain explicit discretization and
rounding limits; admitted mesh targets use their normalized discrete surface.
Hard failures are conjunctive and budgets remain indeterminate. Missing V5
physical selection is not waived. Default `verify_candidate` remains unchanged.

`GEODESIC_DRAFT_SOLVER_V1` admits a closed genus-zero source mesh, binds explicit
pole anchors, computes bounded edge-graph distances and regular closed contours,
then compiles a globally coupled count schedule to complete CrochetIR with the
original DesignSpec and material references. Graph distances are approximations,
not exact surface geodesics. Compiler implementation and target hashes are distinct.

`WAVEFRONT_OBJ_TRIANGLES_V1` is a dependency-free strict triangular source
adapter with explicit units, frame, raw-source identity and decode budgets.
It never repairs topology or substitutes import success for V0 admission.

Calibration registry records are append-only integrity and local review claims.
An allowlisted reviewer string does not authenticate physical measurements.
Reviewed records therefore do not automatically become release-eligible or
change physical status from `UNTESTED`.

## Consequences

API, offline CLI and durable jobs can execute the new profiles. The saved-project
HTTP operations bind stored sources and remain read-only. Source/runtime hashes
are checked against running package bytes; checkout-to-commit authentication and
execution authentication remain explicitly unestablished.

All model coefficients and metric thresholds remain hypotheses until identified
by real fixtures and frozen holdouts. Finite endpoint cases do not prove continuous
uncertainty coverage. Shared kernels and pinned binary64 arithmetic remain
common-mode risks. No numerical PASS establishes calibrated physics or R1-R4
release acceptance. Branch/assembly/M1B, flat, garment and lace scopes remain
separate implementation and acceptance work under the unchanged roadmap.
