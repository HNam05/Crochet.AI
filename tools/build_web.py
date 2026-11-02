"""Build the static web version (GitHub Pages) of the figure editor.

The site runs the unchanged ``crochet_ai`` package in the visitor's browser via
Pyodide. Everything it needs is copied into the output folder, so the
published site makes no requests to other services and needs no server.

Usage::

    python tools/build_web.py [--out build/web] [--commit SHA]

Downloads (Pyodide runtime and pure-Python wheels) are cached in
``build/web-cache`` and checked against Pyodide's lock file hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "crochet_ai" / "prototype_static"
PACKAGE = ROOT / "src" / "crochet_ai"
WEB = ROOT / "web"

PYODIDE_VERSION = "0.29.4"
PYODIDE_URL = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/"
PYODIDE_CORE = (
    "pyodide.mjs", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json",
)
# Compiled dependencies come from Pyodide's own build; their versions follow the lock file.
PYODIDE_PACKAGES = ("pillow", "rpds-py")
# Pure-Python runtime dependencies, pinned to the versions the test suite runs against.
PURE_WHEELS = {
    "reportlab": "4.4.9",
    "charset-normalizer": "3.5.2",
    "rfc8785": "0.1.4",
    "jsonschema": "4.26.0",
    "jsonschema-specifications": "2025.9.1",
    "referencing": "0.37.0",
    "attrs": "26.1.0",
}
STATIC_FILES = ("styles.css", "figure.css", "figure.mjs")


def _download(url: str, target: Path, sha256: str | None = None) -> Path:
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=120) as response:
            target.write_bytes(response.read())
    if sha256 is not None and hashlib.sha256(target.read_bytes()).hexdigest() != sha256:
        target.unlink()
        raise SystemExit(f"hash mismatch for {target.name}")
    return target


def _pyodide(cache: Path, out: Path) -> list[str]:
    folder = out / "pyodide"
    folder.mkdir(parents=True)
    for name in PYODIDE_CORE:
        shutil.copy2(_download(PYODIDE_URL + name, cache / "pyodide" / name), folder / name)
    lock = json.loads((folder / "pyodide-lock.json").read_text(encoding="utf-8"))
    packages = lock["packages"]
    needed: list[str] = []
    todo = list(PYODIDE_PACKAGES)
    while todo:
        name = todo.pop()
        if name in needed:
            continue
        needed.append(name)
        todo.extend(packages[name].get("depends", []))
    for name in needed:
        entry = packages[name]
        file_name = entry["file_name"].rsplit("/", 1)[-1]
        source = _download(PYODIDE_URL + file_name, cache / "pyodide" / file_name, entry["sha256"])
        shutil.copy2(source, folder / file_name)
    return list(PYODIDE_PACKAGES)


def _wheels(cache: Path, out: Path) -> list[str]:
    wheel_cache = cache / "wheels"
    wheel_cache.mkdir(parents=True, exist_ok=True)
    pins = [f"{name}=={pin}" for name, pin in PURE_WHEELS.items()]
    subprocess.run(
        [sys.executable, "-m", "pip", "download", "--quiet", "--no-deps", "--only-binary=:all:",
         "--platform", "any", "--python-version", "3.13", "--implementation", "py",
         "--abi", "none", "--dest", str(wheel_cache), *pins],
        check=True,
    )
    folder = out / "wheels"
    folder.mkdir(parents=True)
    names = []
    for name, pin in PURE_WHEELS.items():
        prefix = f"{name.replace('-', '_')}-{pin}-"
        matches = [
            w for w in wheel_cache.glob("*.whl") if w.name.lower().startswith(prefix.lower())
        ]
        if len(matches) != 1:
            raise SystemExit(f"expected one wheel for {name}=={pin}, found {len(matches)}")
        shutil.copy2(matches[0], folder / matches[0].name)
        names.append(matches[0].name)
    return names


def _package_zip(out: Path) -> None:
    """crochet_ai sources plus the authoritative schemas, bundled as crochet_ai/schemas."""
    with zipfile.ZipFile(out / "crochet_ai.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(PACKAGE.rglob("*")):
            relative = path.relative_to(PACKAGE)
            skipped = "__pycache__" in relative.parts or relative.parts[0] == "prototype_static"
            if path.is_dir() or skipped:
                continue
            archive.write(path, Path("crochet_ai") / relative)
        for path in sorted((ROOT / "schemas").glob("*.json")):
            archive.write(path, Path("crochet_ai") / "schemas" / path.name)
        profiles = ROOT / "profiles"
        if profiles.is_dir():
            for path in sorted(profiles.glob("*.json")):
                archive.write(path, Path("crochet_ai") / "profiles" / path.name)


def _pages(out: Path) -> None:
    for name in STATIC_FILES:
        shutil.copy2(STATIC / name, out / name)
    for name in ("backend.mjs", "py-worker.mjs", "bridge.py", "datenschutz.html"):
        shutil.copy2(WEB / name, out / name)
    html = (STATIC / "figure.html").read_text(encoding="utf-8")
    replacements = {
        '<a class="wordmark" href="/figure.html">': '<a class="wordmark" href="./">',
        '<nav aria-label="Bereiche"><a href="/figure.html" aria-current="page">Figur entwerfen</a>'
        '<a href="/">Einzelform-Test</a></nav>':
            '<nav aria-label="Bereiche"><a href="./" aria-current="page">Figur entwerfen</a>'
            '<a href="datenschutz.html">Datenschutz</a></nav>',
        "Crochet.AI läuft nur auf deinem Rechner.":
            "Crochet.AI rechnet komplett in deinem Browser.",
        '<a href="/privacy.html">Datenschutz</a> · <a href="/terms.html">Nutzungsinfo</a>':
            '<a href="datenschutz.html">Datenschutz und Nutzung</a>',
    }
    for old, new in replacements.items():
        if html.count(old) != 1:
            raise SystemExit(f"figure.html changed, cannot adapt: {old[:60]}")
        html = html.replace(old, new)
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "build" / "web")
    parser.add_argument("--cache", type=Path, default=ROOT / "build" / "web-cache")
    parser.add_argument("--commit", default=None)
    args = parser.parse_args(argv)
    commit = args.commit or subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    ).stdout.strip() or "unknown"
    if args.out.exists():
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True)
    manifest = {
        "commit": commit,
        "pyodide": PYODIDE_VERSION,
        "pyodide_packages": _pyodide(args.cache, args.out),
        "wheels": _wheels(args.cache, args.out),
    }
    _package_zip(args.out)
    _pages(args.out)
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    size = sum(p.stat().st_size for p in args.out.rglob("*") if p.is_file())
    print(f"web build ready: {args.out} ({size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
