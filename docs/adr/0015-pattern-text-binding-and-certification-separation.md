# ADR-0015: Pattern text, external binding, and certification separation

## Status

Accepted for Milestone 1.

## Decision

Pattern V1 is a controlled, human-readable construction language. It contains no
canonical CrochetIR serialization, hash, UUID, or reversible source-artifact
encoding. Its textual parser produces `UnresolvedPatternSemantics`, which is
complete for stitch, course, frontier, branch, operation, attachment, and
yarn-path structure.

`PatternParseContext` is a typed linker environment. It may resolve only the
validated DesignSpec and symbolic Yarn/Color bindings to immutable external
artifacts needed by CrochetIR validation and V9 material equivalence. It must
not contain a CrochetIR, semantic projection, PatternDocument, graph, event
sequence, frontier snapshot, count, or reconstruction hint.

`CertificationManifest` is a detached, post-parse evidence record. It may
compare compact hashes and versions after binding, but is never an input to the
text parser or binder.

## Consequences

Deleting or corrupting structural text cannot be repaired by context or a
manifest. A missing or conflicting symbolic external binding fails closed.
Humans can follow the text without either companion object; certification needs
both the parsed structure and the explicit context.
