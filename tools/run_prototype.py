"""Start the checkout's local human-test prototype without a global install."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Crochet.AI: lokaler Häkeltest-Prototyp")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=repository / "artifacts/local-prototype")
    options = parser.parse_args()
    if not 1024 <= options.port <= 65535:
        parser.error("Der Port muss zwischen 1024 und 65535 liegen.")
    try:
        revision = subprocess.run(
            ["git", "-C", str(repository), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        print(f"Quellversion konnte nicht gelesen werden: {error}", file=sys.stderr)
        return 2
    sys.path.insert(0, str(repository / "src"))
    from crochet_ai.prototype_server import main as serve

    return serve([
        "--port", str(options.port), "--data-dir", str(options.data_dir.resolve()),
        "--software-commit", revision,
    ])


if __name__ == "__main__":
    raise SystemExit(main())
