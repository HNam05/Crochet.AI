# Multi-part figures V1

Status: implemented 2026-10-28, experimental. Every result is
`NOT_VERIFIED` / `UNTESTED` until crocheted and measured.
Decision record: [ADR 0026](adr/0026-multi-part-figures.md).

## Scope

A figure is a list of rotational parts plus assembly positions and small
features. This covers the classic amigurumi construction (head, body, arms,
legs, ears, snout, tail, beak, wings) and simple garments that are one
surface of revolution (a beanie from head circumference).

| Module | Responsibility |
| --- | --- |
| `figure_parts.py` | Part profile, round placement, readable count DP, staggered shaping, notation, structural replay |
| `figure.py` | Strict `FigureSpec` parsing, instance placement, assembly and feature instructions, schematic 3D points, text export |
| `figure_ir.py` | Per-part DesignSpec + CrochetIR emission, validated by the unchanged `SemanticValidator` |
| `figure_pdf.py` | Printable German pattern with front sketch and structure-check summary |
| `figure_templates.py` | Original starter figures: teddy, bunny, chick, beanie |
| `prototype_static/figure.*` | Browser editor with live recompute and orbit preview |

Not covered: crocheting parts together while working (join-as-you-go),
oval/chain starts, colour regions other than horizontal stripes, branching
garments (gloves, sweaters), lace, knitting.

## Part model

Shapes and allowed ends (first is the default):

| Shape | Ends | Typical use |
| --- | --- | --- |
| `sphere`, `ellipsoid`, `egg`, `pear`, `capsule` | closed | head, body, tail |
| `dome` | open, flat | ear, snout, wing, foot pad |
| `tube` | open, flat, closed | arm, leg, long ear |
| `cone` | closed, open | beak, horn, tuft |
| `cylinder` | closed, open | cup, beanie |

Ends: `closed` gathers the last ≤ 6 stitches; `open` leaves a rim for sewing;
`flat` is flattened and closed with n/2 sc through both layers (odd n: sewn).

**HYPOTHESIS (round placement):** a round's stitch count equals the target
circumference at its *upper edge* divided by the stitch pitch. With a
course/stitch pitch ratio of about 0.9 this reproduces the empirical
6/12/18 single-crochet disc. Rounds are spaced uniformly in meridian arc
length: `m = round(L / course_pitch)` for open ends, one fewer for closed ends
(the gathered closure takes one round-height).

**ENGINEERING DECISION (counts):** an exact DP over `(count, previous count)`
minimises squared circumference residual (in stitches²) plus readability
penalties: 0.6 when shaping does not divide the round evenly, 0.15 when the
shaping amount changes between shaping rounds, 0.01 per shaping stitch, 0.5 for
an odd flat-closure count. Windows: ring 6..8 (4..8 for narrow tips), other
rounds `floor(q)-r .. ceil(q)+r` with r = 4, widened to 8 and 16 only if
infeasible; closed final round ≤ 6. Transitions obey `after ≤ 2·before` and
`2·after ≥ before`. The project's bottleneck DP (`analytic_counts`) is still
run as a reference and reported as `reference_bottleneck_mm`. Weights are
uncalibrated; owner: figure solver, calibration path: physical test series.

**ENGINEERING DECISION (stagger):** shaping is spread evenly; every second
shaping round is rotated by half a gap, e.g. `(2 sc, inc) x 6` then
`(1 sc, inc, 1 sc) x 6`, so increases do not stack into a hexagon.

Every schedule is replayed (`check_schedule`): each round must consume exactly
the previous count and produce its own count.

## Figure spec

```json
{"name": "...", "gauge": {"stitches_per_100mm": 25, "rows_per_100mm": 28, "hook_mm": 3},
 "colors": [{"id": "brown", "label": "Braun", "hex": "#9C6B3F"}],
 "parts": [
   {"id": "body", "label": "Körper", "shape": "egg", "width_mm": 55, "height_mm": 62,
    "color": "brown"},
   {"id": "arm", "label": "Arm", "shape": "tube", "width_mm": 16, "height_mm": 36,
    "end": "flat", "color": "brown",
    "attach": {"to": "body", "at": 0.78, "angles": [80, 280], "tilt": 55}}],
 "features": [{"type": "eye", "on": "body", "at": 0.5, "angles": [24, 336],
               "size_mm": 8, "color": "brown"}]}
```

- Closed objects, unknown fields rejected, German error messages, no repair.
- The first part is the root (optionally `"start": "top"`, e.g. a hat crown).
- `attach.to` must name an earlier single-instance part. `at` is the fraction
  of the host's rounds (0 = magic ring, 1 = last round); each angle creates one
  instance (0 = front, 90 = viewer's right, 180 = back). `tilt` rotates the
  part's axis towards world-down.
- Optional per part: `circumference_mm` instead of `width_mm`, `stripes`
  (`from`/`to` round fractions with a colour), `stuffing`, `note`.

## Assembly math

For a host with arc length L, round spacing h and an attachment at fraction a:

- host round `k = ceil(a·L / h)`;
- stitch `j = floor(((180° − θ) mod 360°) / 360° · n_k) + 1`, counted from the
  round marker (defined as the back) in right-handed working direction; frames
  whose side vector points left (parts worked downwards) are mirrored so user
  angles always mean the viewer's side;
- open end: rim diameter `n_end·p_s/π` spans ± that radius in rounds;
- flat end: width `n_end·p_s/2`, i.e. `n_end/2` stitches along round k;
- closed part: estimated contact circle `0.4·min(widths)` (illustrative).

Safety eyes are placed between rounds k and k+1 with their stitch spacing and a
note inserted into the host's rounds before stuffing.

## Trust boundary

- Live solving (`/api/figure/solve`) returns schedules, instructions and the
  schematic layout (round radius from counts, rigid parts, simple flattening).
  It is not a physical prediction of stuffing, seams or fabric.
- `verify_figure` / `/api/figure/verify` builds a DesignSpec 1.2 per part
  (coordinate profile, intentional opening for open/flat ends, colours,
  user gauge as material) and a complete CrochetIR whose stitch order equals the
  printed rounds, including `COLOR_CHANGE` and `DECLARE_OPENING`. The unchanged
  `SemanticValidator` must pass. PASS is structural only (V1–V4 class checks);
  geometry, physics and seams between parts are not verified.
- Assembly sewing is described in text only; it is not yet a CrochetIR
  operation (a `JOIN` connects frontiers, not a frontier to a fabric surface).

Measured: the four templates (18 part types) all pass structural validation;
validation takes ~0.1–13 s per part (larger parts are slower), so it runs on
demand and for PDF export rather than on every edit.
