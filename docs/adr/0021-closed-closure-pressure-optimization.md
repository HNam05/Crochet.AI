# 0021: Experimental closed closure, pressure and bounded optimization

Status: Accepted for experimental producer scope only

Closed shaped preparation supplies target-independent cells and explicit rest
parameters, but no ring/CLOSE tension, pressure loading or relaxation. Reusing
the strip-only bending model would invent shaped-cell parameters; treating force
balance as V6 would bypass independent and physical acceptance.

Add a separate versioned recipe for tension-only ring and CLOSE purse strings,
explicit pressure `-pV`, an independently declared operational volume bound and
bounded Armijo descent. Reuse existing elastic preparation and optimizer kernels;
keep existing profiles, canonical schemas, source compilation and verification
unchanged. Expose the experimental bundle through API/CLI/jobs and a read-only,
CSRF-protected saved-project compute endpoint.

This provides a reviewable loaded mechanical prototype with units, provenance,
work accounting and visible failure, without importing target coordinates.
The pressure model can diverge; the volume bound is an operational guard.
Only experimental force-balanced debug coordinates are exposed. Closure yarn/cap,
shaped shear/bending, contact, multistart, calibration and independent V6 remain
open. See [the contract](../FORWARD_CLOSED_MECHANICS_V1.md).
