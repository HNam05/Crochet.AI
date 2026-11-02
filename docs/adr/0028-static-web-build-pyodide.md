# ADR-0028: Free web version on GitHub Pages with Python in the browser

- Status: Accepted (experimental)
- Date: 2026-11-02

## Context

The owner wants the figure editor public on the web at no cost: no paid server,
no third-party service, no AI API. GitHub Pages is free for public
repositories but only serves static files, while the pattern engine is Python.

## Decision

- Build a static site (`tools/build_web.py`) that runs the unchanged
  `crochet_ai` package in the visitor's browser through Pyodide 0.29.4 inside a
  Web Worker (`web/py-worker.mjs`).
- Self-host everything on the Pages site: the Pyodide runtime, its compiled
  Pillow and rpds-py wheels (checked against the lock file hashes) and the
  pure-Python wheels pinned to the versions the tests use. The published site
  makes no requests to other hosts.
- Move the editor operations into `crochet_ai.figure_api`, used by both the
  local server and `web/bridge.py`, so both answer identically. The frontend
  talks to `backend.mjs`, which is the HTTP client locally and the worker client
  in the web build.
- Claude is never available in the web build (`allow_claude=False`).
- The independent CrochetIR check takes about 30 s in the browser (7 s
  natively, dominated by JSON-Schema validation). The web PDF therefore omits
  the check summary (`verify_pdf=False`); "Maschen nachrechnen" still runs the
  full check on request.
- `.github/workflows/pages.yml` runs the figure and bridge tests, builds and
  deploys on every push to `main`.

## Consequences

- Hosting is free and private by construction: designs never leave the device.
- First visit downloads about 16 MB (cached afterwards); startup takes a few
  seconds.
- Pyodide's Python (3.13) differs from the CI interpreter (3.11). The bridge
  test covers the dispatcher natively; the browser path was checked manually.
- The single-shape test page (`index.html`) still needs the local server and is
  not part of the web build.
