"""Figure editor operations shared by the local server and the browser build.

The local prototype server and the static GitHub Pages build (Python running in
the visitor's browser through Pyodide) answer the same editor requests with the
same code. Transport, CSRF and storage stay with the caller.
"""

from __future__ import annotations

from typing import Any

from .figure import FigureError, calibrate_gauge, figure_text, solve_figure
from .figure_compose import claude_available, compose
from .figure_ir import verify_figure
from .figure_parts import SHAPE_ENDS
from .figure_pdf import render_figure_pdf
from .figure_templates import template_catalog

FIGURE_SHAPE_LABELS = {
    "sphere": "Kugel",
    "ellipsoid": "Ellipsoid",
    "egg": "Ei",
    "pear": "Birne",
    "capsule": "Kapsel",
    "tube": "Schlauch (Arm/Bein)",
    "dome": "Halbkugel/Kuppel",
    "cone": "Kegel",
    "cylinder": "Zylinder/Becher",
    "disc": "Scheibe (flach)",
    "rectangle": "Rechteck in Reihen (flach)",
}

SPEC_PATHS = frozenset(
    {"/api/figure/solve", "/api/figure/pdf", "/api/figure/text", "/api/figure/verify"}
)
TOOL_PATHS = frozenset({"/api/figure/compose", "/api/figure/calibrate"})


def templates_payload(*, allow_claude: bool = True) -> dict[str, Any]:
    """Editor bootstrap data: templates, shape catalogue, optional Claude support."""
    return {
        "templates": template_catalog(),
        "shapes": [
            {"id": key, "label_de": FIGURE_SHAPE_LABELS[key], "ends": list(ends)}
            for key, ends in SHAPE_ENDS.items()
        ],
        "claude_available": allow_claude and claude_available(),
    }


def figure_tool(path: str, body: dict[str, Any], *, allow_claude: bool = True) -> dict[str, Any]:
    """Text-to-figure proposals and gauge correction; FigureError on bad input."""
    if path == "/api/figure/compose":
        if set(body) != {"text", "use_claude"} or not isinstance(body["use_claude"], bool):
            raise FigureError("compose.fields", "Felder text und use_claude erwartet.")
        if body["use_claude"] and not allow_claude:
            raise FigureError("compose.claude", "Claude ist in dieser Version nicht verfügbar.")
        return compose(body["text"], use_claude=body["use_claude"])
    fields = {"spec", "part", "measured_mm", "measure_mode", "measured_height_mm"}
    if set(body) != fields or not isinstance(body["part"], str):
        raise FigureError("calibrate.fields", "Unvollständige Messangaben.")
    figure = solve_figure(body["spec"])
    part = next((p for p in figure["parts"] if p["id"] == body["part"]), None)
    if part is None:
        raise FigureError("calibrate.part", "Unbekanntes Teil.")
    return calibrate_gauge(
        figure["gauge"],
        planned_width_mm=part["predicted_width_mm"],
        planned_height_mm=part["predicted_height_mm"],
        measured_mm=body["measured_mm"],
        measure_mode=body["measure_mode"],
        measured_height_mm=body["measured_height_mm"],
    )


def figure_spec_call(
    path: str, body: dict[str, Any], *, software_commit: str, verify_pdf: bool = True
) -> tuple[str, Any]:
    """Solve, verify, PDF or text for one spec.

    Returns ``("json", data)``, ``("pdf", bytes)`` or ``("text", bytes)``. Raises
    ValueError for a malformed body and FigureError for an invalid spec. With
    ``verify_pdf=False`` the PDF omits the structural check summary; the browser
    build uses this because the independent check takes about half a minute there.
    """
    if set(body) != {"spec"}:
        raise ValueError("figure.fields")
    figure = solve_figure(body["spec"])
    if path == "/api/figure/solve":
        return "json", figure
    if path == "/api/figure/text":
        return "text", figure_text(figure).encode()
    if path == "/api/figure/pdf" and not verify_pdf:
        return "pdf", render_figure_pdf(figure, None)
    checks = verify_figure(body["spec"], software_commit=software_commit)
    if path == "/api/figure/verify":
        return "json", {"parts": checks}
    if path == "/api/figure/pdf":
        return "pdf", render_figure_pdf(figure, checks)
    raise ValueError("figure.path")
