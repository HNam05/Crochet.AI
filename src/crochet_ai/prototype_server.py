"""Loopback-only HTTP entry point for the human-test prototype."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import rfc8785

from .backend_api import MAX_REQUEST_BYTES, BackendAPI, bounded_json
from .calibration_pdf import render_calibration_packet
from .prototype_backend import LocalPrototype
from .prototype_input import PROTOTYPE_VERSION, REQUEST_FIELDS
from .prototype_pdf import PrototypePdfError, render_project_pdf
from .prototype_proposals import ProposalBundleIntegrityError, retained_proposals
from .prototype_shapes import SHAPE_CATALOG
from .prototype_storage import PrototypeStore, PrototypeStoreError

MAX_BODY = 65_536
ASSETS = {
    "index.html",
    "styles.css",
    "app.mjs",
    "viewer.mjs",
    "state.mjs",
    "privacy.html",
    "terms.html",
}


class PrototypeHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    prototype_store: PrototypeStore


def _commit(explicit: str) -> str:
    if explicit:
        return explicit
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError("software_commit.required") from error


def make_server(port: int, data_dir: Path, software_commit: str) -> PrototypeHTTPServer:
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("server.port")
    store = PrototypeStore(data_dir)
    service = LocalPrototype(store, _commit(software_commit))
    backend = BackendAPI(service.provenance)
    token = uuid.uuid4().hex
    static_dir = Path(__file__).resolve().parent / "prototype_static"

    class Handler(BaseHTTPRequestHandler):
        server_version = "CrochetAIPrototype/1.0"

        def log_message(self, fmt: str, *args: object) -> None:
            return

        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(10)

        def _send(
            self,
            status: int,
            value: object,
            content_type: str = "application/json; charset=utf-8",
            attachment: str | None = None,
        ) -> None:
            payload = (
                value
                if isinstance(value, bytes)
                else json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
            )
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            if attachment is not None:
                self.send_header("Content-Disposition", f'attachment; filename="{attachment}"')
            self.end_headers()
            self.wfile.write(payload)

        def _error(self, status: int, code: str, reason: str) -> None:
            self._send(status, {"ok": False, "error": {"code": code, "reason": reason}})

        def _host_valid(self) -> bool:
            hosts = self.headers.get_all("Host", [])
            expected_port = bound_port
            return len(hosts) == 1 and hosts[0] in {
                f"127.0.0.1:{expected_port}",
                f"localhost:{expected_port}",
            }

        def _mutation_valid(self) -> bool:
            origins = self.headers.get_all("Origin", [])
            tokens = self.headers.get_all("X-CSRF-Token", [])
            if (
                not self._host_valid()
                or len(origins) != 1
                or len(tokens) != 1
                or tokens[0] != token
            ):
                return False
            try:
                parsed = urlsplit(origins[0])
            except ValueError:
                return False
            return (
                parsed.scheme == "http"
                and parsed.netloc == self.headers.get("Host")
                and parsed.path == ""
                and not parsed.query
                and not parsed.fragment
            )

        def _body(self) -> dict[str, Any]:
            lengths = self.headers.get_all("Content-Length", [])
            if self.headers.get("Transfer-Encoding") is not None:
                raise ValueError("request.transfer_encoding")
            if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdecimal():
                raise ValueError("request.content_length")
            content_types = self.headers.get_all("Content-Type", [])
            if (
                len(content_types) != 1
                or content_types[0].split(";", 1)[0].strip().lower() != "application/json"
            ):
                raise ValueError("request.content_type")
            size = int(lengths[0])
            if size > MAX_BODY:
                raise OverflowError("request.size")
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ValueError("request.truncated")
            return bounded_json(raw)

        def do_GET(self) -> None:
            try:
                self._do_get()
            except sqlite3.Error:
                self._error(507, "E_STORAGE", "storage.database")

        def _do_get(self) -> None:
            if not self._host_valid():
                self._error(403, "E_ORIGIN", "request.host")
                return
            path = urlsplit(self.path).path
            if "%" in path:
                self._error(404, "E_NOT_FOUND", "route.not_found")
                return
            if path == "/api/bootstrap":
                self._send(
                    200,
                    {
                        "ok": True,
                        "data": {
                            "prototype_version": PROTOTYPE_VERSION,
                            "csrf_token": token,
                            "default_request": {
                                "prototype_version": PROTOTYPE_VERSION,
                                "shape": "sphere",
                                "diameter_mm": 40,
                                "height_mm": 40,
                                "stitches_per_100mm": 25,
                                "courses_per_100mm": 28,
                                "hook_diameter_mm": 3,
                                "yarn_label": "Meine Testwolle",
                                "color_hex": "#B88757",
                                "uncertainty_percent": 10,
                            },
                            "shape_catalog": list(SHAPE_CATALOG),
                        },
                    },
                )
            elif path == "/api/capabilities":
                self._send(
                    200, backend.handle({"api_version": "1.0.0", "operation": "capabilities"})
                )
            elif path == "/api/calibration-protocol.pdf":
                self._send(
                    200,
                    render_calibration_packet(),
                    "application/pdf",
                    "crochet-calibration-measurements.pdf",
                )
            elif path == "/api/projects":
                self._send(200, {"ok": True, "data": {"projects": store.list_projects()}})
            elif path.startswith("/api/projects/"):
                parts = path.split("/")
                if (
                    len(parts) == 5
                    and parts[4] == "pattern.pdf"
                    and re.fullmatch(r"[0-9a-f]{64}", parts[3])
                ):
                    project = store.get_project(parts[3])
                    if project is None:
                        self._error(404, "E_NOT_FOUND", "project.not_found")
                        return
                    try:
                        retained_proposals(project)
                    except ProposalBundleIntegrityError as error:
                        self._error(422, "E_PROVENANCE", str(error))
                        return
                    try:
                        pdf = render_project_pdf(project, parts[3])
                    except PrototypePdfError as error:
                        self._error(422, "E_EXPORT", str(error))
                        return
                    self._send(
                        200,
                        pdf,
                        "application/pdf",
                        f"crochet-pattern-{parts[3][:12]}.pdf",
                    )
                elif (
                    len(parts) == 5
                    and parts[4] == "feedback"
                    and re.fullmatch(r"[0-9a-f]{64}", parts[3])
                ):
                    records = store.feedback(parts[3])
                    self._send(
                        200 if store.get_project(parts[3]) else 404,
                        {"ok": True, "data": {"feedback": records}}
                        if store.get_project(parts[3])
                        else {
                            "ok": False,
                            "error": {"code": "E_NOT_FOUND", "reason": "project.not_found"},
                        },
                    )
                elif len(parts) == 4 and re.fullmatch(r"[0-9a-f]{64}", parts[3]):
                    project = store.get_project(parts[3])
                    if project is not None:
                        try:
                            retained_proposals(project)
                        except ProposalBundleIntegrityError as error:
                            self._error(422, "E_PROVENANCE", str(error))
                            return
                    self._send(
                        200 if project else 404,
                        {"ok": True, "data": project}
                        if project
                        else {
                            "ok": False,
                            "error": {"code": "E_NOT_FOUND", "reason": "project.not_found"},
                        },
                    )
                else:
                    self._error(404, "E_NOT_FOUND", "route.not_found")
            elif path == "/" or (path.startswith("/") and path[1:] in ASSETS):
                name = "index.html" if path == "/" else path[1:]
                asset = static_dir / name
                if not asset.is_file():
                    self._error(404, "E_NOT_FOUND", "asset.not_found")
                    return
                content_type = (
                    "text/html; charset=utf-8"
                    if name.endswith(".html")
                    else "text/css; charset=utf-8"
                    if name.endswith(".css")
                    else "text/javascript; charset=utf-8"
                )
                self._send(200, asset.read_bytes(), content_type)
            else:
                self._error(404, "E_NOT_FOUND", "route.not_found")

        def do_POST(self) -> None:
            if not self._host_valid() or not self._mutation_valid():
                self._error(403, "E_CSRF", "request.origin_or_token")
                return
            try:
                body = self._body()
                path = urlsplit(self.path).path
                if path == "/api/generate":
                    if set(body) != REQUEST_FIELDS:
                        raise ValueError("request.fields")
                    project = service.generate(body)
                    self._send(200, {"ok": True, "data": project})
                elif path == "/api/verify":
                    if set(body) != {"project_id"} or not isinstance(body["project_id"], str):
                        raise ValueError("verification.project_id")
                    if re.fullmatch(r"[0-9a-f]{64}", body["project_id"]) is None:
                        raise ValueError("verification.project_id")
                    verification_project = store.get_project(body["project_id"])
                    if verification_project is None:
                        self._error(404, "E_NOT_FOUND", "project.not_found")
                        return
                    candidate_proposals = retained_proposals(verification_project)
                    verification_request = {
                        "api_version": "1.0.0",
                        "operation": "verify_candidate",
                        "design_spec": verification_project["design_spec"],
                        "material_profile": verification_project["material_profile"],
                        "crochet_ir": verification_project["crochet_ir"],
                        "mesh_json": None,
                        "diagnostic_mode": False,
                    }
                    generation = verification_project.get("generation", {})
                    if generation.get("search_trace") is not None:
                        verification_request["search_evidence"] = {
                            "run_config": {
                                key: value
                                for key, value in verification_project["run_config"].items()
                                if key != "phase_policy"
                            },
                            "search_trace": generation["search_trace"],
                            "candidate_proposals": candidate_proposals,
                        }
                    if len(rfc8785.dumps(verification_request)) > MAX_REQUEST_BYTES:
                        raise OverflowError("verification.request_size")
                    response = backend.handle(verification_request)
                    self._send(200 if response["ok"] else 422, response)
                elif path == "/api/session":
                    required = {"prototype_version", "project_id", "expected_revision", "cursor"}
                    if set(body) != required or body["prototype_version"] != PROTOTYPE_VERSION:
                        raise ValueError("session.fields")
                    if not isinstance(body["project_id"], str):
                        raise ValueError("session.project_id")
                    session = store.set_session(
                        body["project_id"], body["expected_revision"], body["cursor"]
                    )
                    self._send(200, {"ok": True, "data": session})
                elif path == "/api/feedback":
                    record = service.feedback_record(body)
                    self._send(200, {"ok": True, "data": record})
                else:
                    self._error(404, "E_NOT_FOUND", "route.not_found")
            except OverflowError as error:
                self._error(413, "E_INPUT", str(error))
            except PrototypeStoreError as error:
                self._error(
                    409 if str(error) == "E_CONFLICT" else 507,
                    "E_CONFLICT" if str(error) == "E_CONFLICT" else "E_STORAGE",
                    str(error),
                )
            except ProposalBundleIntegrityError as error:
                self._error(422, "E_PROVENANCE", str(error))
            except KeyError as error:
                self._error(404, "E_NOT_FOUND", str(error))
            except (ValueError, RuntimeError) as error:
                code = "E_BUSY" if str(error) == "E_BUSY" else "E_INPUT"
                self._error(503 if code == "E_BUSY" else 400, code, str(error))
            except TimeoutError:
                self._error(408, "E_INPUT", "request.timeout")
            except OSError:
                self._error(507, "E_STORAGE", "storage.io")
            except sqlite3.Error:
                self._error(507, "E_STORAGE", "storage.database")

    server = PrototypeHTTPServer(("127.0.0.1", port), Handler)
    bound_port = server.socket.getsockname()[1]
    server.prototype_store = store
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="crochet-ai-prototype")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path, default=Path("artifacts/local-prototype"))
    parser.add_argument("--software-commit", default="")
    args = parser.parse_args(argv)
    try:
        server = make_server(args.port, args.data_dir, args.software_commit)
    except (OSError, ValueError) as error:
        print(f"prototype startup failed: {error}", file=sys.stderr)
        return 2
    print(f"Local crochet prototype listening on http://127.0.0.1:{server.server_address[1]}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.prototype_store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
