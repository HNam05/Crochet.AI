# ADR-0007: V1 executable stitch and operation semantics

- Status: Accepted
- Date: 2026-08-31

## Context

The schema exposed six ordinary stitch families, shaping labels, and construction operations without fixing which combinations the first semantic validator must execute. Treating every syntactically representable combination as supported would create ambiguous decrease and export semantics.

## Decision

`CROCHET_CORE_1.0.0` executes:

- `CHAIN + PLAIN` as `(base_arity, top_arity) = (0, 1)`;
- `PLAIN` `SLIP_STITCH`, `SINGLE_CROCHET`, `HALF_DOUBLE_CROCHET`, `DOUBLE_CROCHET`, and `TREBLE_CROCHET` as `(1, 1)`;
- binary `SINGLE_CROCHET + INCREASE` as `(1, 2)`;
- binary `SINGLE_CROCHET + DECREASE` as `(2, 1)`;
- `MAGIC_RING`, `JOIN`, `SPLIT`, `RESERVE`, `ATTACH`, `COLOR_CHANGE`, `CUT_YARN`, `CLOSE`, and `DECLARE_OPENING` under their frontier/yarn contracts.

`INCREASE` and `DECREASE` are derived shaping classifications on one canonical stitch-application node. They are neither stitch families, construction operations, nor free-form text macros. V1 rejects non-SC shaping and n-ary shaping with `E_UNSUPPORTED_FEATURE`.

Every positive-base stitch uses the explicit `REPLACE_SPAN` frontier edit. Zero-base `CHAIN` uses `INSERT_AT_GAP` with the attachment-location neighbor rules fixed by ADR-0008. Yarn traversal never supplies the insertion position.

## Alternatives

- Standalone increase/decrease primitives were rejected because they duplicate the underlying stitch family and complicate material response.
- Repeated ordinary nodes sharing one base were rejected because they cannot symmetrically represent decreases and make export regrouping ambiguous.
- Generic shaping over all families was deferred because the project has not fixed independent yarn-loop/export semantics for every taller-stitch decrease.

## Consequences

CrochetIR's family plus ordered base/top lists and explicit edit class remain stable. A later semantic profile may enable taller-stitch or n-ary shaping without replacing the graph model. The first analytic solver can remain SC-only while garments and flat work may already validate plain taller stitches. Lace clusters and chain spaces still require their own capabilities, but may reuse explicit gap anchoring once their typed semantics are defined.

Two plain SC nodes sharing one base are not semantically equivalent to one SC increase node in V1. A parser must reconstruct the explicit shaping node or fail V9.
