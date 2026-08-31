# Completion checks

No executable Stop hook is enabled during bootstrap. A future lightweight completion hook may run only fast checks:

- formatting and linting;
- static type checks;
- targeted unit tests;
- a bounded quick property-test profile;
- JSON Schema validation;
- parser/export semantic round trips.

Full geometry optimization, Monte Carlo robustness, collision suites, and physical-fixture analysis belong in dedicated CI, nightly, or release jobs. A hook failure must be reported; it must not modify golden files or suppress a failing gate.
