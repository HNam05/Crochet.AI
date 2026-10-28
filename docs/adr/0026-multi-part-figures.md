# ADR-0026: Multi-part figures from rotational parts and sewn assembly

- Status: Accepted (experimental)
- Date: 2026-10-28

## Context

The product goal is "describe a figure, get a pattern". The analytic solver
handled six closed single-colour shapes. Free-form mesh solving (geodesic,
frontier) is far from production, while hand-designed amigurumi are almost
always assembled from surfaces of revolution: closed bodies and heads plus
open or flattened limbs, ears and snouts, sewn on at named rounds.

## Decision

Model a figure as a strict `FigureSpec` of rotational parts with open, flat
or closed ends, colour stripes, sewn attachments given as (round fraction,
angle, tilt) and features such as safety eyes. Solve each part with a
readability-weighted exact count DP that reuses the project's count model and
reports the bottleneck DP as a reference. Emit per part a DesignSpec 1.2 and
complete CrochetIR and require the unchanged semantic validator to pass.
Assembly stays a documented text layer outside CrochetIR for now.

The browser editor solves live; structural validation runs on demand and for
PDF export because it costs seconds per part.

## Consequences

- Figures, simple hats and colour-striped parts become usable now, built on
  the existing IR and validator rather than a parallel format.
- Readability weights and the upper-edge round hypothesis are uncalibrated;
  physical test series must confirm or adjust them.
- Sewing onto a surface needs a future IR operation before assembly can be
  verified. Join-as-you-go, branching garments and free meshes remain open.
- Text input (LLM → FigureSpec) can now target a concrete, validated format
  without ever supplying stitch counts (consistent with ADR-0006).
