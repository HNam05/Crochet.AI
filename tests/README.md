# Test architecture

Tests are organized by the kind of defect they are intended to expose:

- `unit/`: local pure-function and exact invariant checks
- `property/`: Hypothesis-generated valid and invalid artifacts
- `stateful/`: frontier, yarn, branch, and course transition state machines
- `metamorphic/`: transformations whose semantics or metric behavior must be preserved
- `integration/`: subsystem boundaries such as schema to semantic validator
- `golden/`: human-approved canonical artifacts and expected evidence
- `physical/`: measured benchmark records and reconstruction comparisons
- `fixtures/`: reusable meshes, DesignSpecs, MaterialProfiles, and invalid cases

Fast completion checks must use bounded examples and deterministic seeds where replay is required. Full property, geometry, collision, robustness, and physical suites run in dedicated CI profiles.

Golden artifacts are immutable during ordinary test execution. A change requires an explicit review record describing why the semantic result changed; no script may overwrite expected outputs automatically.

