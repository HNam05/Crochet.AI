# ADR-0029: 3D model upload (STL/OBJ) as a custom part profile

- Status: Accepted (experimental)
- Date: 2026-11-02

## Context

Users should be able to upload something and get a crochet pattern, without
any AI service and entirely on their own device (ADR 0028). A 3D model is the
input that can be converted deterministically.

## Decision

- New part shape `custom` with a normalized meridian `profile`
  (`[[axial 0..1, radius 0..1], ...]`, 3 to 120 points, axial non-decreasing
  from 0 to 1, widest radius 1). `width_mm`/`height_mm` scale it, so size
  controls and calibration work unchanged. Ends: `closed` or `open`.
- `figure_mesh` reads binary/ASCII STL and OBJ (fan-triangulated polygons),
  bounded to 12 MB and 200,000 triangles, and cuts the model into 64 slices
  along the chosen up axis (auto: Z for STL, Y for OBJ; optional flip).
- Each slice contributes the perimeter of its convex hull; the profile radius
  is `perimeter / 2 pi`. HYPOTHESIS: a stuffed single-crochet part is round in
  cross-section and its fabric spans concave dents, so stitch counts should
  follow girth, not the exact silhouette. Light 1-2-1 smoothing keeps slicing
  noise from lengthening the meridian (which sets the round count).
- Cross-section loops are found from shared mesh edges. Loops under 12 % of
  the largest loop's hull perimeter are details. More than one major loop on
  over 25 % of the slices fails closed (`mesh.branches`); less is reported as
  a warning. Empty slices (separate pieces) fail closed (`mesh.gap`).
- The upload reaches Python as raw bytes: `POST /api/figure/mesh` with
  `application/octet-stream` and URL-encoded JSON options in `X-Mesh-Options`
  on the local server, a transferred ArrayBuffer in the browser build. Both go
  through `figure_api.figure_mesh`.

## Consequences

- Rounded single-piece models (eggs, fruit, vases, heads, bodies) become a
  pattern in about 1.5 s for 100,000 triangles in the browser; a sphere model
  reproduces the built-in sphere's counts within the test tolerance.
- Figures with limbs must be uploaded part by part; each upload currently
  replaces the figure (adding uploads as attached parts is future work).
- Non-round cross-sections (flat, wide shapes) are crocheted round with the
  same girth; the preview shows the round result, not the source model.
- Not physically validated; NOT_VERIFIED / UNTESTED like every pattern.
