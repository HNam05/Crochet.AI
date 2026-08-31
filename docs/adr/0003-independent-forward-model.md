# ADR-0003: Independent forward model

- Status: Accepted
- Date: 2026-08-30

## Context

Checking a solver against geometry it used during generation risks circular validation. A different reconstruction path is needed to test whether the compiled construction plausibly produces the claimed shape.

## Decision

Verification includes an independent pipeline from a versioned `PhysicalSemanticProjection` of CrochetIR plus resolved MaterialProfile/loading inputs to a crochet graph and predicted physical geometry. The projection removes DesignSpec identity, target-role provenance, solver provenance, solver derivations, and every target-derived seed before initialization, caching, or optimization. The target mesh is unavailable to the simulator as a constraint, repair signal, embedding target, cache discriminator, or convergence aid. Target geometry enters only after simulation, in the comparison stage.

The initial F0 model uses a practical graph/spring formulation. Later F1 shell and F2 yarn/contact models may improve fidelity without changing the trust boundary.

## Consequences

- Forward-model inputs and target-comparison inputs have separate interfaces; cache and initialization keys derive only from the target-free physical-semantic projection and other permitted inputs.
- Solver-specific geometry caches cannot be reused as authoritative simulated geometry.
- Shared low-level libraries require common-mode-risk review.
- Physical accuracy claims remain hypotheses until calibration fixtures support them.
