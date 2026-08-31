# ADR-0008: Ordered attachment-location frontier ledger

- Status: Accepted
- Date: 2026-08-31

## Context

Branches, reservations, reattachments, joins, garment openings, and lace attachment sites need references that remain unambiguous when one stitch creates multiple usable locations.

## Decision

The semantic unit of frontier ownership is an explicit `attachment_location_id`. An immutable frontier object owns an ordered sequence of those IDs, a `LINEAR` or anchored `CYCLIC` topology, lifecycle, component, and branch. Replay maintains an exact ledger in which each produced location is in exactly one state: active-live, reserved-live, retired, or declared-open-boundary.

Split and reserve outputs are disjoint ordered partitions. V1 permits no live shared-junction location. Reattachment preserves the reserved sequence. Join applies explicit per-input orientation, retires declared join sites, and concatenates the remaining oriented sequences in declared input order. Closed frontiers own no locations; declared openings retain their exact boundary sequence.

## Alternatives

- Direct stitch IDs were rejected because one stitch may produce multiple top locations.
- Numeric ranges were rejected because cyclic wrap, alpha-renaming, insertion, and retessellation make them unstable.
- A separate persistent frontier-segment entity was rejected as redundant in V1; a reserved frontier already is a persistent branch-local segment.
- Implicit branch-local cursors were rejected because they cannot independently prove location conservation.

## Consequences

Solvers may use compressed ranges privately but must compile explicit ordered IDs. Forward simulation receives exact incidence. Garment armholes, two legs, branch reattachment, and future lace chain-space locations use the same ledger without sharing one geometry solver. Compression, if later needed, is a serialization optimization and cannot change canonical semantics.
