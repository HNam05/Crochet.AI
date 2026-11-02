"""Request dispatcher for the in-browser build (runs inside Pyodide).

Mirrors the local server's figure routes through crochet_ai.figure_api so the
browser and the server answer identically. Claude is never available here.
"""

import json

from crochet_ai.figure import FigureError
from crochet_ai.figure_api import (
    SPEC_PATHS,
    TOOL_PATHS,
    figure_mesh,
    figure_spec_call,
    figure_tool,
    templates_payload,
)

LAST_BYTES = b""
CONTENT_TYPES = {"pdf": "application/pdf", "text": "text/plain; charset=utf-8"}


def _ok(data):
    return json.dumps({"ok": True, "data": data})


def _error(error):
    if isinstance(error, FigureError):
        return json.dumps({"ok": False, "error": {
            "code": "E_INPUT", "reason": error.code, "message_de": error.message_de}})
    return json.dumps({"ok": False, "error": {"code": "E_INPUT", "reason": str(error)}})


def mesh(data, options_json):
    """3D model upload: raw file bytes (from the worker) plus JSON options."""
    try:
        return _ok(figure_mesh(bytes(data), json.loads(options_json)))
    except (FigureError, ValueError, KeyError, TypeError) as error:
        return _error(error)


def handle(path, body_json, commit):
    global LAST_BYTES
    try:
        body = json.loads(body_json) if body_json else None
        if path == "/api/figure/templates":
            return _ok(templates_payload(allow_claude=False))
        if path in TOOL_PATHS:
            return _ok(figure_tool(path, body, allow_claude=False))
        if path in SPEC_PATHS:
            kind, data = figure_spec_call(path, body, software_commit=commit, verify_pdf=False)
            if kind == "json":
                return _ok(data)
            LAST_BYTES = data
            return json.dumps({"ok": True, "binary": True, "content_type": CONTENT_TYPES[kind]})
        return json.dumps({"ok": False, "error": {"code": "E_NOT_FOUND", "reason": path}})
    except (FigureError, ValueError, KeyError, TypeError) as error:
        return _error(error)
