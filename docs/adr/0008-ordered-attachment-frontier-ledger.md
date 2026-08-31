# ADR-0008: Ordered attachment-location frontier ledger

- Status: Accepted
- Date: 2026-08-31

## Context

Branches, reservations, reattachments, joins, garment openings, and lace attachment sites need references that remain unambiguous when one stitch creates multiple usable locations.

## Decision

The semantic unit of frontier ownership is an explicit `attachment_location_id`. An immutable frontier object owns an ordered sequence of those IDs, a `LINEAR` or anchored `CYCLIC` topology, lifecycle, component, and branch. Replay maintains an exact ledger in which each produced location is in exactly one state: active-live, reserved-live, retired, or declared-open-boundary.

Split and reserve outputs are disjoint ordered partitions. V1 permits no live shared-junction location. Reattachment preserves the reserved sequence. Join applies explicit per-input orientation, retires declared join sites, and concatenates the remaining oriented sequences in declared input order. Closed frontiers own no locations; declared openings retain their exact boundary sequence.

Every stitch declares one explicit, yarn-independent frontier edit. `REPLACE_SPAN` targets a frontier and uses the containing stitch's non-empty ordered base/top lists as rewritten and replacement locations. `INSERT_AT_GAP` targets a frontier, names nullable left/right attachment-location neighbors, requires an empty base list, and inserts the containing stitch's ordered tops. Linear end/empty gaps and cyclic oriented adjacency are defined exactly in `CROCHET_IR.md`. `CHAIN` uses `INSERT_AT_GAP` in V1.

## Alternatives

- Direct stitch IDs were rejected because one stitch may produce multiple top locations.
- Numeric ranges were rejected because cyclic wrap, alpha-renaming, insertion, and retessellation make them unstable.
- A separate persistent frontier-segment entity was rejected as redundant in V1; a reserved frontier already is a persistent branch-local segment.
- Implicit branch-local cursors were rejected because they cannot independently prove location conservation.
- Numeric gap indexes, yarn-path position, work direction, and output-array differencing were rejected as insertion anchors because they are unstable or infer intent not present in CrochetIR.
- Duplicating base/top lists inside the edit object was rejected because the containing stitch already provides the authoritative ordered span and replacement/inserted locations.

## Consequences

Solvers may use compressed ranges privately but must compile explicit ordered IDs. V1 materializes an immutable input/output snapshot for each stitch edit so replay can prove ownership after every event. Forward simulation receives exact incidence. Foundation chains, repeated chains, garment armholes, two legs, branch reattachment, and future lace/picot/chain-space locations can reuse explicit gaps and the same ledger without sharing one geometry solver. Future compression is a serialization optimization and cannot change canonical semantics.
