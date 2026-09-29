# Pattern Format V1

Pattern V1 is a strict, localized construction language. CrochetIR is canonical,
but its JSON/JCS, hashes, UUIDs, and reversible encodings are forbidden in the
standard human pattern.

## Two-stage parse and link contract

`parse_pattern_text(text)` creates `UnresolvedPatternSemantics` using only
visible Pattern V1 instructions. It determines all stitch, course, attachment,
frontier, branch, operation, and yarn-path semantics. It cannot receive a
`PatternParseContext`.

`bind_pattern_semantics(unresolved, context)` resolves only external DesignSpec
and symbolic Yarn/Color bindings, then creates and validates CrochetIR. Context
cannot contain construction data or an original CrochetIR. Missing, duplicated,
or incompatible bindings fail closed.

`CertificationManifest` is detached evidence created after export. It contains
only compact hashes and versions, and is never consumed by parsing or binding.

## Controlled text form

```text
CROCHET-PATTERN-V1
FORMAT: 1
TERMINOLOGY: US_EN | UK_EN | DE_DE
MATERIAL Yarn A: <human material description>
COURSE Section A: Round 1; cyclic; spiral; clockwise
STEP 0: Start Yarn A with a magic ring; Section A has Marker A.
STEP 1: In Section A, work sc using Marker A; create Marker B. (1)
STEP 2: Close Section A.
END
```

The actual grammar uses deterministic variants of these lines for every V1
stitch and construction operation. `Yarn A`, `Section A`, and `Marker A` are
presentation symbols generated from first semantic use, never CrochetIR IDs.
All counts and marker relationships are explicit text grammar, not inferred
from context or an implicit cursor.

## Context allowlist

`PatternParseContext` contains exactly a validated DesignSpec plus one or more
typed `PatternYarnBinding` values: symbolic yarn name, material profile identity
and content hash, color display value, and optional human material description.
The source IR, PatternDocument, event sequence, frontier state, topology,
attachment incidence, operation counts, and source encodings are prohibited.

## Certification

A `CertificationManifest` records `pattern_format_version`, source IR hash,
semantic-projection hash, pattern-document hash, terminology profile, exporter
version, and validator version. It verifies only a result already reconstructed
from text and context.
