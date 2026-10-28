"""Original starter figures (no licensed characters). Edit freely in the UI."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_GAUGE = {"stitches_per_100mm": 25, "rows_per_100mm": 28, "hook_mm": 3, "yarn": "Baumwolle DK"}

TEMPLATES: dict[str, dict[str, Any]] = {
    "teddy": {
        "name": "Teddybär",
        "gauge": _GAUGE,
        "colors": [
            {"id": "brown", "label": "Braun", "hex": "#9C6B3F"},
            {"id": "beige", "label": "Beige", "hex": "#E7CFA8"},
            {"id": "dark", "label": "Dunkelbraun", "hex": "#2B2118"},
        ],
        "parts": [
            {"id": "body", "label": "Körper", "shape": "egg", "width_mm": 55, "height_mm": 62,
             "color": "brown"},
            {"id": "head", "label": "Kopf", "shape": "sphere", "width_mm": 58, "height_mm": 58,
             "color": "brown", "note": "Beginnt am Scheitel; die letzte Runde ist der Hals.",
             "attach": {"to": "body", "at": 1.0, "angles": [0]}},
            {"id": "snout", "label": "Schnauze", "shape": "dome", "width_mm": 26, "height_mm": 11,
             "end": "open", "color": "beige", "stuffing": "light",
             "attach": {"to": "head", "at": 0.66, "angles": [0]}},
            {"id": "ear", "label": "Ohr", "shape": "dome", "width_mm": 22, "height_mm": 10,
             "end": "flat", "color": "brown", "stuffing": "none",
             "attach": {"to": "head", "at": 0.22, "angles": [72, 288]}},
            {"id": "arm", "label": "Arm", "shape": "tube", "width_mm": 16, "height_mm": 36,
             "end": "flat", "color": "brown",
             "attach": {"to": "body", "at": 0.78, "angles": [80, 280], "tilt": 55}},
            {"id": "leg", "label": "Bein", "shape": "tube", "width_mm": 20, "height_mm": 26,
             "end": "open", "color": "brown",
             "stripes": [{"from": 0, "to": 0.18, "color": "beige"}],
             "attach": {"to": "body", "at": 0.22, "angles": [40, 320], "tilt": -15}},
        ],
        "features": [
            {"type": "eye", "on": "head", "at": 0.47, "angles": [24, 336], "size_mm": 8,
             "color": "dark"},
            {"type": "nose", "on": "snout", "at": 0.04, "angles": [0], "size_mm": 8,
             "color": "dark"},
        ],
    },
    "bunny": {
        "name": "Hase",
        "gauge": _GAUGE,
        "colors": [
            {"id": "grey", "label": "Hellgrau", "hex": "#C9C4BE"},
            {"id": "white", "label": "Weiß", "hex": "#F4F1EA"},
            {"id": "pink", "label": "Rosa", "hex": "#E9A3B0"},
            {"id": "black", "label": "Schwarz", "hex": "#1E1C1A"},
        ],
        "parts": [
            {"id": "body", "label": "Körper", "shape": "egg", "width_mm": 50, "height_mm": 58,
             "color": "grey"},
            {"id": "head", "label": "Kopf", "shape": "ellipsoid", "width_mm": 50,
             "height_mm": 46, "color": "grey",
             "attach": {"to": "body", "at": 1.0, "angles": [0]}},
            {"id": "ear", "label": "Ohr", "shape": "tube", "width_mm": 17, "height_mm": 55,
             "end": "flat", "color": "grey", "stuffing": "none",
             "stripes": [{"from": 0, "to": 0.15, "color": "pink"}],
             "attach": {"to": "head", "at": 0.14, "angles": [55, 305], "tilt": -10}},
            {"id": "arm", "label": "Arm", "shape": "tube", "width_mm": 14, "height_mm": 30,
             "end": "flat", "color": "grey",
             "attach": {"to": "body", "at": 0.78, "angles": [80, 280], "tilt": 50}},
            {"id": "foot", "label": "Fuß", "shape": "tube", "width_mm": 18, "height_mm": 22,
             "end": "open", "color": "white",
             "attach": {"to": "body", "at": 0.16, "angles": [30, 330], "tilt": -20}},
            {"id": "tail", "label": "Schwänzchen", "shape": "sphere", "width_mm": 16,
             "height_mm": 16, "color": "white",
             "attach": {"to": "body", "at": 0.3, "angles": [180]}},
        ],
        "features": [
            {"type": "eye", "on": "head", "at": 0.55, "angles": [28, 332], "size_mm": 6,
             "color": "black"},
            {"type": "nose", "on": "head", "at": 0.66, "angles": [0], "size_mm": 5,
             "color": "pink"},
        ],
    },
    "chick": {
        "name": "Küken",
        "gauge": _GAUGE,
        "colors": [
            {"id": "yellow", "label": "Gelb", "hex": "#F2C94C"},
            {"id": "orange", "label": "Orange", "hex": "#E8833A"},
            {"id": "black", "label": "Schwarz", "hex": "#1E1C1A"},
        ],
        "parts": [
            {"id": "body", "label": "Körper", "shape": "egg", "width_mm": 60, "height_mm": 66,
             "color": "yellow"},
            {"id": "beak", "label": "Schnabel", "shape": "cone", "width_mm": 12, "height_mm": 10,
             "end": "open", "color": "orange", "stuffing": "light",
             "attach": {"to": "body", "at": 0.66, "angles": [0]}},
            {"id": "wing", "label": "Flügel", "shape": "dome", "width_mm": 26, "height_mm": 16,
             "end": "flat", "color": "yellow", "stuffing": "none",
             "attach": {"to": "body", "at": 0.5, "angles": [95, 265], "tilt": 35}},
            {"id": "foot", "label": "Fuß", "shape": "dome", "width_mm": 18, "height_mm": 7,
             "end": "flat", "color": "orange", "stuffing": "none",
             "attach": {"to": "body", "at": 0.08, "angles": [25, 335], "tilt": -30}},
            {"id": "tuft", "label": "Haarbüschel", "shape": "cone", "width_mm": 10,
             "height_mm": 12, "end": "open", "color": "yellow", "stuffing": "light",
             "attach": {"to": "body", "at": 1.0, "angles": [0]}},
        ],
        "features": [
            {"type": "eye", "on": "body", "at": 0.73, "angles": [24, 336], "size_mm": 6,
             "color": "black"},
        ],
    },
    "beanie": {
        "name": "Mütze (Kopfumfang 56 cm)",
        "gauge": {"stitches_per_100mm": 15, "rows_per_100mm": 17, "hook_mm": 6,
                  "yarn": "Wolle, dick"},
        "colors": [
            {"id": "main", "label": "Petrol", "hex": "#2F6F73"},
            {"id": "rim", "label": "Creme", "hex": "#EFE6D2"},
        ],
        "parts": [
            {"id": "hat", "label": "Mütze", "shape": "cylinder", "circumference_mm": 520,
             "start": "top",
             "height_mm": 200, "end": "open", "color": "main", "stuffing": "none",
             "note": "Umfang 52 cm = Kopfumfang 56 cm minus ca. 7 % (sitzt leicht gedehnt). "
                     "Beginnt in der Mitte des Oberkopfs.",
             "stripes": [{"from": 0.86, "to": 1, "color": "rim"}]},
        ],
    },
}


def template_catalog() -> list[dict[str, Any]]:
    return [{"id": key, "name": value["name"], "spec": deepcopy(value)}
            for key, value in TEMPLATES.items()]
