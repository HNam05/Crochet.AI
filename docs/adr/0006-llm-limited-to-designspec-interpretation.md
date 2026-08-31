# ADR-0006: LLM authority ends at DesignSpec interpretation

- Status: Accepted
- Date: 2026-08-30

## Context

Natural language and images are useful for design intent but cannot provide reproducible construction semantics or trustworthy final stitch counts by themselves.

## Decision

An LLM may propose a DesignSpec from unstructured input. That proposal is untrusted input and must pass strict schema and semantic validation. After DesignSpec, authoritative generation is deterministic or explicitly bounded numerical optimization with complete provenance. LLM-produced final counts cannot bypass solvers and verification.

## Consequences

- The core compiler can operate without an LLM.
- Prompt/model changes cannot silently change a verified artifact with the same canonical DesignSpec and solver provenance.
- Ambiguous interpretation is surfaced for correction instead of silently guessed.
- Future LLM integration belongs outside solver and verifier trust boundaries.
