# ADR-0027: Text input, knitting, flat projects and gauge calibration

- Status: Accepted (experimental)
- Date: 2026-11-02

## Context

After multi-part figures (ADR 0026) the product still required hand-built
specs, crochet only, no flat projects and no way to learn from a test piece.
The user asked for a tool that people who crochet *and* knit can use for
creative projects.

## Decision

- Add a text-to-FigureSpec layer with two interpreters: a deterministic offline
  German keyword interpreter with original builders, and optional Claude via
  the official SDK. Both only propose specs; `parse_figure` and the solver stay
  authoritative (consistent with ADR-0006). Claude requests use
  `claude-opus-5-5` with server-side refusal fallbacks enabled by default.
- Treat the round schedule as technique-neutral and add knitting as an export
  notation plus finishing rules. Do not emit knit parts as CrochetIR; a separate
  knit semantics is future work.
- Add flat `disc` and `rectangle` shapes; rectangles use turned rows. Flat parts
  are root-only.
- Add a one-part gauge calibration (`old · planned / measured`).

## Consequences

- Users can start from a sentence, pick crochet or knitting, and make hats,
  scarves, blankets and coasters as well as figures.
- Structural CrochetIR validation covers crochet round parts only; knit and row
  work rely on the schedule replay until their own IR exists.
- The offline interpreter has a fixed vocabulary; Claude widens it but needs the
  optional package and credentials, and can be refused or fail validation.
- Calibration is a single-sample correction; repeated measurements and a
  persisted per-user material profile remain open.
