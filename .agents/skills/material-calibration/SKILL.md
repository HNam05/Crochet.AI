---
name: material-calibration
description: Work on MaterialProfile, gauge, uncertainty, physical calibration fixtures, crocheter tension, stuffing measurements, or empirical threshold updates.
---

# Material calibration

Read [`docs/MATERIAL_MODEL.md`](../../../docs/MATERIAL_MODEL.md), [`docs/PHYSICAL_VALIDATION.md`](../../../docs/PHYSICAL_VALIDATION.md), and [`schemas/material-profile.schema.json`](../../../schemas/material-profile.schema.json).

- Keep effective stitch pitch and course pitch separate, with explicit units and measurement conditions.
- Treat yarn category and hook diameter as priors, not sufficient geometry calibration.
- Add parameters only when a planned fixture can identify them without severe confounding.
- Record specimen, software, DesignSpec, CrochetIR, material, crocheter/tension, stuffing, measurement, and image provenance.
- Label thresholds and parameter ranges as hypotheses until physical evidence supports a versioned calibration profile.
- Never convert sparse measurements into false precision.

State identifiability limits and which benchmark supports each fitted parameter.

