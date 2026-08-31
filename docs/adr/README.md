# Architecture decision records

Accepted foundational decisions:

1. [`0001-canonical-crochet-ir.md`](0001-canonical-crochet-ir.md): one canonical executable construction representation
2. [`0002-fail-closed-verification.md`](0002-fail-closed-verification.md): mandatory gates and structured rejection
3. [`0003-independent-forward-model.md`](0003-independent-forward-model.md): target-independent reconstruction
4. [`0004-diverse-solver-families.md`](0004-diverse-solver-families.md): algorithmically distinct, domain-specific solvers
5. [`0005-seamless-priority-after-geometry-gate.md`](0005-seamless-priority-after-geometry-gate.md): seamless-first only among geometry-feasible candidates
6. [`0006-llm-limited-to-designspec-interpretation.md`](0006-llm-limited-to-designspec-interpretation.md): LLM authority stops at untrusted DesignSpec proposals
7. [`0007-v1-executable-stitch-and-operation-semantics.md`](0007-v1-executable-stitch-and-operation-semantics.md): executable V1 stitch/shaping/operation scope
8. [`0008-ordered-attachment-frontier-ledger.md`](0008-ordered-attachment-frontier-ledger.md): ordered attachment-location frontiers and exhaustive replay ownership
9. [`0009-execution-normalized-semantic-equivalence.md`](0009-execution-normalized-semantic-equivalence.md): deterministic semantic round-trip equivalence without raw-ID equality
10. [`0010-domain-specific-v0-preflight-profiles.md`](0010-domain-specific-v0-preflight-profiles.md): domain-specific geometry preflight and no implicit repair
11. [`0011-jcs-ijson-domain-separated-hashes.md`](0011-jcs-ijson-domain-separated-hashes.md): language-independent canonical numbers, bytes, and hashes

New decisions that alter public schemas, verification gates, trust boundaries, reproducibility, or physical claims require a new ADR. Accepted ADRs are superseded rather than rewritten to conceal history.
