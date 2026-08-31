# ADR-0009: Execution-normalized semantic graph equivalence

- Status: Accepted
- Date: 2026-08-31

## Context

Localized export and parsing regenerate IDs and non-semantic metadata. Raw JSON or canonical content-hash equality is therefore too strong, while unrestricted graph isomorphism is ambiguous and unnecessarily expensive.

## Decision

V9 uses `CROCHET_SEMANTIC_EQUIVALENCE_V1`. Each valid IR is projected to construction-relevant fields, alpha-renamed from its total execution/creation order, normalized by the canonical collection registry, serialized with the shared JCS/I-JSON contract, and compared byte-for-byte.

The projection preserves stitch/shaping/arity/incidence, frontier-edit class, target frontier, gap-neighbor references, event/course/yarn order, active yarn and color changes, material hashes, frontier rewrites, branch/component topology, join methods/orientations, and opening semantics. It removes artifact IDs, display labels, derivations, solver/search provenance, source URIs, software commit, and DesignSpec identity. V10 separately preserves provenance and lineage.

Global event order remains semantic in V1. Reordering independent components is not treated as an implicit commutation. Exporters that abbreviate repeated components must provide enough anchors for the parser to reconstruct the same order.

## Alternatives

- Exact serialization/content-hash equality was rejected because harmless ID and label regeneration would fail.
- General graph isomorphism was rejected because total execution order already supplies deterministic labels and ambiguity would create common-mode risk.
- Partial-order equivalence was deferred because deciding event independence across yarn, components, joins, and material state adds complexity not needed for V1.

## Consequences

Alpha-renaming and localization can pass without weakening construction semantics. One compound increase is not equivalent to two plain nodes. Mirrored work, reordered courses, reversed joins, changed material binding, or swapped component execution fails. Future partial-order relaxation requires a new ADR and projection profile.
