# Source layout

Bootstrap reserves package boundaries without choosing an implementation framework prematurely.

- `ir/`: canonical CrochetIR types, canonicalization, and semantic validation
- `parser/`: machine and future human-pattern parsing
- `exporter/`: localized human-readable output
- `geometry/`: geometry preflight, metrics, and shared numeric primitives
- `topology/`: construction-frontier and topology analysis
- `materials/`: MaterialProfile and calibration data handling
- `solvers/`: domain-specific candidate generators
- `forward/`: target-independent physical reconstruction
- `verification/`: gate orchestration and evidence reporting

The next milestone may choose a Python package name and move these boundaries beneath it. No production implementation is part of bootstrap.

