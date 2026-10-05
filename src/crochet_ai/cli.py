"""Offline command surface for the versioned API and local job store."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any, Never

import rfc8785

from .backend_api import (
    API_VERSION,
    MAX_REQUEST_BYTES,
    ApiInputError,
    BackendAPI,
    bounded_json,
    error_response,
)
from .backend_provenance import runtime_provenance
from .calibration_campaign import (
    CalibrationCampaign,
    CalibrationMeasurement,
    calibration_protocol,
    derive_draft_material,
)
from .calibration_pdf import render_calibration_packet
from .calibration_store import CalibrationStore
from .job_store import JobStore, JobStoreError
from .job_worker import execute_one_isolated
from .schema import schema_documents

_provenance = runtime_provenance


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ApiInputError(message)


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
    calibration = commands.add_parser("calibration", help="Frozen local pilot measurement records")
    calibration_actions = calibration.add_subparsers(dest="calibration_action", required=True)
    calibration_actions.add_parser("protocol", help="Inspect the supported measurement protocol")
    packet = calibration_actions.add_parser(
        "packet", help="Write blank or campaign-bound PDF sheets"
    )
    packet.add_argument("--output", required=True)
    packet.add_argument("--campaign-file")
    for name in ("register", "record", "show", "derive"):
        command = calibration_actions.add_parser(
            name, help=f"{name} append-only calibration records"
        )
        command.add_argument("--db", required=True)
        if name in {"register", "record"}:
            command.add_argument("--record-file", required=True)
        if name != "register":
            command.add_argument("--campaign-sha256", required=True)
        if name == "derive":
            command.add_argument("--profile-id", required=True)
            command.add_argument("--response-id", required=True)
            command.add_argument("--created-at", required=True)
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


def _calibration(args: argparse.Namespace) -> dict[str, Any]:
    if args.calibration_action == "protocol":
        return calibration_protocol()
    if args.calibration_action == "packet":
        campaign = (
            CalibrationCampaign(bounded_json(_read(args.campaign_file)))
            if args.campaign_file
            else None
        )
        payload = render_calibration_packet(campaign)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as stream:
            stream.write(payload)
        return {
            "output": str(output.resolve()),
            "sha256": sha256(payload).hexdigest(),
            "physical_status": "UNTESTED",
            "document_kind": "MEASUREMENT_PROTOCOL",
        }
    path = Path(args.db)
    if args.calibration_action != "register" and not path.is_file():
        raise ValueError("calibration.store_not_found")
    with CalibrationStore(path) as store:
        if args.calibration_action == "register":
            campaign = CalibrationCampaign(bounded_json(_read(args.record_file)))
            return {
                "campaign_sha256": store.register_campaign(campaign),
                "physical_status": "UNTESTED",
            }
        campaign = store.get_campaign(args.campaign_sha256)
        if campaign is None:
            raise ValueError("calibration.campaign_not_found")
        if args.calibration_action == "record":
            record = CalibrationMeasurement(bounded_json(_read(args.record_file)), campaign)
            return {
                "measurement_sha256": store.add_measurement(record),
                "physical_status": "UNTESTED",
            }
        if args.calibration_action == "show":
            return {
                "campaign": campaign.to_dict(),
                "campaign_sha256": campaign.sha256,
                "measurements": [
                    record.to_dict() for record in store.list_measurements(campaign.sha256)
                ],
                "physical_status": "UNTESTED",
            }
        ids = {
            item["specimen_id"]
            for item in campaign.to_dict()["specimens"]
            if item["role"] == "CALIBRATION"
        }
        records = [
            record
            for record in store.active_measurements(campaign.sha256)
            if record.to_dict()["specimen_id"] in ids
        ]
        return derive_draft_material(
            campaign,
            records,
            profile_id=args.profile_id,
            response_id=args.response_id,
            created_at=args.created_at,
        )


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
                    "schema_kinds": sorted(schema_documents(include_additive_versions=True)),
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
        elif args.command == "calibration":
            response = {"api_version": API_VERSION, "ok": True, "data": _calibration(args)}
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
