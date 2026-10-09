"""Local command line interface for prototype SQLite backups."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from crochet_ai.prototype_backup import BackupError, backup, restore


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create or restore a local prototype SQLite backup"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("backup", help="snapshot a prototype.sqlite3 database")
    create.add_argument("source", type=Path)
    create.add_argument("bundle", type=Path)
    recover = commands.add_parser("restore", help="verify and restore a backup bundle")
    recover.add_argument("bundle", type=Path)
    recover.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        manifest = (
            backup(args.source, args.bundle)
            if args.command == "backup"
            else restore(args.bundle, args.destination)
        )
    except (BackupError, OSError) as error:
        print(f"backup error: {error}", file=sys.stderr)
        return 2
    print(
        f"{manifest['format']} sha256={manifest['database_sha256']} "
        f"bytes={manifest['database_bytes']} rows={manifest['row_counts']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
