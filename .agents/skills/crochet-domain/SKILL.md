---
name: crochet-domain
description: Apply canonical crochet terminology and domain boundaries when changing stitch semantics, construction operations, localization, garments, flat crochet, lace, or amigurumi behavior.
---

# Crochet domain

Read [`docs/DOMAIN_MODEL.md`](../../../docs/DOMAIN_MODEL.md) before domain changes and [`docs/CROCHET_IR.md`](../../../docs/CROCHET_IR.md) when graph semantics are involved.

- Use unambiguous canonical stitch identifiers. US, UK, and German terms belong only in exporter localization tables.
- Keep `JOIN`, `SPLIT`, `ATTACH`, and `COLOR_CHANGE` as construction operations, not ordinary stitches.
- Describe shaping through explicit base and top arity; existing stitch nodes are never conceptually consumed.
- Keep amigurumi, garment, flat, and lace solvers separate while reusing canonical IR and verification.
- Mark unsupported techniques explicitly. Do not imply full lace or garment support from the basic stitch enum.

Return changed invariants, affected terminology mappings, and unsupported cases.

