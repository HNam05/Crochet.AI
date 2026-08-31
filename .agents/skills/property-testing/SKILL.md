---
name: property-testing
description: Create or review Hypothesis property tests, state machines, metamorphic tests, shrinking strategies, adversarial generators, or golden-fixture controls.
---

# Property testing

Read [`docs/TEST_STRATEGY.md`](../../../docs/TEST_STRATEGY.md) and the subsystem's invariant contract.

- Use Hypothesis unless a documented technical constraint prevents it.
- Generate both valid and deliberately invalid structures; assert rejection category and minimal diagnostic context.
- Model frontier operations with stateful tests and illegal transitions with negative rules.
- Cover translation and rotation invariance, scale covariance, mirroring, retessellation, winding normalization, gauge monotonicity, and export/parse semantic equivalence as applicable.
- Keep generators independent from the implementation logic they test.
- Never auto-update golden files or reduce search/examples solely to hide a failure.

Report the invariant, oracle independence, and minimized counterexample for every new property.

