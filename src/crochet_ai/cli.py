"""Offline command surface for the versioned API and local job store."""

from __future__ import annotations

import argparse
import json
import platform
import sqlite3
import sys
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from typing import Any, Never

import rfc8785

from .analytic_compile import CompileProvenance
from .backend_api import (
    API_VERSION,
    MAX_REQUEST_BYTES,
    ApiInputError,
    BackendAPI,
    bounded_json,
    error_response,
)
from .job_store import JobStore, JobStoreError
from .job_worker import execute_one_isolated
from .schema import schema_documents


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ApiInputError(message)


def _provenance(commit: str) -> CompileProvenance:
    source_hashes = {
        p.name: sha256(p.read_bytes()).hexdigest()
        for p in sorted(Path(__file__).parent.glob("*.py"))
    }
    schema_hashes = {
        name: sha256(rfc8785.dumps(doc)).hexdigest() for name, doc in schema_documents().items()
    }
    snapshot = sha256(
        b"Crochet.AI\0BACKEND_SOURCE_SNAPSHOT_V1\0"
        + rfc8785.dumps({"sources": source_hashes, "schemas": schema_hashes})
    ).hexdigest()
    return CompileProvenance(
        commit,
        snapshot,
        (
            ("runtime.python", platform.python_version()),
            ("runtime.platform", platform.system()),
            ("runtime.jsonschema", version("jsonschema")),
            ("runtime.rfc8785", version("rfc8785")),
            ("source.checkout_status", "UNCONFIRMED"),
        ),
    )


def _read(path: str) -> bytes:
    with Path(path).open("rb") as stream:
        payload = stream.read(MAX_REQUEST_BYTES + 1)
    if len(payload) > MAX_REQUEST_BYTES:
        raise ApiInputError("request.size")
    return payload


def _parser() -> _Parser:
    parser = _Parser(
        prog="crochet-ai",
        description="Offline crochet backend. Generated candidates are NOT_VERIFIED.",
    )
    parser.add_argument("--json", action="store_true", help="Compact stable JSON on stdout")
    parser.add_argument(
        "--software-commit",
        default="",
        help="Actual source commit for generation; source snapshot is hashed independently",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Inspect offline runtime and schema availability")
    commands.add_parser("capabilities", help="List implemented operations and verification limits")
    for name in ("request", "generate", "validate", "export"):
        command = commands.add_parser(
            name, help=f"Execute {name} from a versioned JSON request file"
        )
        command.add_argument("--request-file", required=True)
    jobs = commands.add_parser("jobs", help="Durable local job operations")
    actions = jobs.add_subparsers(dest="action", required=True)
    for name in ("submit", "get", "cancel", "run-next", "list"):
        command = actions.add_parser(name, help=f"{name} local jobs")
        command.add_argument("--db", required=True, help="Explicit local SQLite database path")
        if name == "submit":
            command.add_argument("--request-file", required=True)
            command.add_argument("--idempotency-key", required=True)
            command.add_argument("--dry-run", action="store_true")
        elif name in {"get", "cancel"}:
            command.add_argument("job_id")
        elif name == "run-next":
            command.add_argument("--watchdog-seconds", type=float, default=60.0)
        else:
            command.add_argument("--limit", type=int, default=20)
            command.add_argument("--offset", type=int, default=0)
    return parser


def main(argv: list[str] | None = None) -> int:
    compact = False
    try:
        args = _parser().parse_args(argv)
        compact = args.json
        provenance = _provenance(args.software_commit)
        api = BackendAPI(provenance)
        if args.command == "doctor":
            response: dict[str, Any] = {
                "api_version": API_VERSION,
                "ok": True,
                "data": {
                    "mode": "OFFLINE_LOCAL",
                    "auth_required": False,
                    "schema_kinds": sorted(schema_documents()),
                    "source_snapshot_sha256": provenance.source_snapshot_sha256,
                    "generation_commit_supplied": bool(args.software_commit),
                    "physical_verification_available": False,
                },
            }
        elif args.command == "capabilities":
            response = api.handle({"api_version": API_VERSION, "operation": "capabilities"})
        elif args.command in {"request", "generate", "validate", "export"}:
            request = bounded_json(_read(args.request_file))
            expected = {
                "generate": "generate_analytic",
                "validate": "validate_ir",
                "export": "export_ir",
            }
            if args.command in expected and request.get("operation") != expected[args.command]:
                raise ApiInputError("request.command_operation_mismatch")
            response = api.handle(request)
        else:
            if args.action == "submit" and args.dry_run:
                payload = rfc8785.dumps(bounded_json(_read(args.request_file)))
                data: dict[str, Any] = {
                    "dry_run": True,
                    "request_sha256": sha256(payload).hexdigest(),
                    "bytes": len(payload),
                }
            else:
                path = Path(args.db)
                if args.action != "submit" and not path.is_file():
                    raise JobStoreError("store.not_found")
                store = JobStore(path)
                if args.action == "submit":
                    data = {
                        "job_id": store.submit(_read(args.request_file), args.idempotency_key),
                        "status": "QUEUED_OR_EXISTING",
                    }
                elif args.action == "get":
                    data = store.get(args.job_id)
                elif args.action == "cancel":
                    data = {"job_id": args.job_id, "status": store.cancel(args.job_id)}
                elif args.action == "list":
                    data = store.list_jobs(limit=args.limit, offset=args.offset)
                else:
                    data = {
                        "processed": execute_one_isolated(
                            store, api, max_wall_seconds=args.watchdog_seconds
                        )
                    }
            response = {"api_version": API_VERSION, "ok": True, "data": data}
    except (ApiInputError, JobStoreError, ValueError) as error:
        response = error_response("E_INPUT", str(error))
    except (OSError, sqlite3.Error) as error:
        response = error_response("E_STORAGE", type(error).__name__)
    print(
        json.dumps(
            response,
            ensure_ascii=True,
            separators=(",", ":") if compact else None,
            indent=None if compact else 2,
        )
    )
    if not response["ok"]:
        return 2
    generation = response.get("data", {}).get("generation_status")
    return 0 if generation in {None, "CANDIDATES_EMITTED"} else 3


if __name__ == "__main__":
    sys.exit(main())
