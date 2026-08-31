---
name: verification
description: Implement or review fail-closed schema, reference, count, frontier, topology, forward-model, geometry, robustness, export, or provenance verification stages.
---

# Verification

Read [`docs/VERIFICATION.md`](../../../docs/VERIFICATION.md), [`docs/FAILURE_POLICY.md`](../../../docs/FAILURE_POLICY.md), and the affected representation contract.

- Preserve the V0-V10 gate order and structured evidence. A mandatory failure cannot be averaged away.
- Keep generation, semantic validation, forward simulation, and target comparison independently implemented where feasible.
- Never pass target geometry into the forward simulator as a constraint, initial embedding oracle, or repair signal.
- Prefer exact checks for references, counts, state transitions, and canonicalization; document units and rationale for numerical tolerances.
- Report metric vectors and threshold profiles, not opaque confidence percentages.
- Fail on missing evidence required by the selected verification profile.

For verifier changes, identify common-mode assumptions and add an adversarial test that would expose them.

