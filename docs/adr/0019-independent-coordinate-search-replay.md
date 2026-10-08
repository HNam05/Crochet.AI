# 0019: Independent coordinate search replay

Status: accepted implementation decision, 2026-10-08.

## Decision

Extend the existing trace audit to the explicit-coordinate producer scope under
[COORDINATE_MERIDIAN_REPLAY_V1](../ANALYTIC_COORDINATE_REPLAY_V1.md). Keep generation,
canonical schemas and the forward model unchanged. Reuse the independent staged
count/phase replay kernels and existing API/V5/prototype-relation integration.

Implement numerical reconstruction separately: exact represented-coordinate
differences, bit-enumerated floating neighbors, exact enclosure/rounding checks
and independent linear segment lookup. Input-target admission and standard
arithmetic remain documented common dependencies. Charge deterministic numerical
work to the existing trace proof budget; preserve ordinary sphere evidence bytes.

Recognize coordinate proposal parameters only after independently checking their
meaning and authoritative bindings. Unknown and absent evidence remains visible.
Stored projects retain their historical source and complete original artifacts.

## Alternatives and consequences

Calling the generator's sampler would repeat its errors and violate the trust
boundary. Whitelisting coordinate parameters or checking only producer hashes
would accept claims without establishing their semantics. A new API, data-store
migration or numerical framework is unnecessary for this bounded additive scope.

This closes computational coordinate replay only. A search or final-relation
PASS does not establish calibrated physical feasibility, source authentication,
V7 geometry coverage or full backend acceptance. Those gates remain separate.
