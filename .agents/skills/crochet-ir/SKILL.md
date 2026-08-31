---
name: crochet-ir
description: Design, implement, review, or migrate canonical CrochetIR, its schema, graph references, frontier state, canonicalization, parser, or semantic export round trips.
---

# CrochetIR

Read [`docs/CROCHET_IR.md`](../../../docs/CROCHET_IR.md), [`docs/DOMAIN_MODEL.md`](../../../docs/DOMAIN_MODEL.md), and [`schemas/crochet-ir.schema.json`](../../../schemas/crochet-ir.schema.json).

- CrochetIR is canonical; neither DesignSpec, prose, nor a solver Construction Graph may replace it.
- Preserve explicit IDs, ordered courses, attachment references, yarn path, active yarn, branches, openings, and frontier transitions.
- Treat JSON Schema validation as necessary but insufficient. Independent semantic validation must check graph-wide invariants.
- Canonicalization must be deterministic and independent of map iteration, locale, or incidental input order.
- Parser/export changes require semantic round-trip tests; text equality is not the oracle.

State any changed invariant, migration impact, and known invalid case.

