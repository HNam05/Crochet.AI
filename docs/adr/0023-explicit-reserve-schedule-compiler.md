# ADR 0023: Explicit reserve schedule compiler

Status: implemented structural subset, 2026-10-09. No canonical schema change.

The existing compiler emits one uninterrupted closed SC frontier, while core
semantics already support explicit reservation and independent terminal
obligations. A planning graph or hand-built fixture is insufficient as a producer.

Add `EXPLICIT_RESERVE_SC_V1`: lower a caller-provided initial cyclic SC course
through the approved core 1.1 multi-site ring compiler, remove its private
temporary terminal close, then emit the actual ordered reserve partition,
active-prefix continuation and two explicit closures. Retain complete event,
frontier, course, yarn, branch/component and derivation tables. The final
generator is FRONTIER and all derivations bind the actual composite lowering
through a separate parameter domain. The unchanged semantic validator admits
the result; it also rejects corrupted reservations.

Use exact integer accounting and operational limits on events, unique locations
and cumulative frontier memberships before emission. No random search,
numerical tolerance, target steering, schema migration or golden replacement
is involved. Both terminal obligations belong to the existing single branch;
this does not implement automatic branch DAG or geometry decomposition.

Expose the additive operation through generic API, CLI and durable jobs. Label
outputs structural, NOT_VERIFIED and UNTESTED. Pattern V1A and the closed-cell
forward model do not support this lifecycle and remain fail-closed. Visible M1B
instructions and physical branch/open semantics must be implemented independently
before a generated reserve construction becomes a human-test pattern.

See [compiler contract](../RESERVE_SCHEDULE_COMPILER_V1.md).
