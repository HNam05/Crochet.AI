"""Turn a free-text wish ("ein kleiner grauer Hase, 12 cm") into a FigureSpec proposal.

Two interpreters share one trust boundary:

* an offline German keyword interpreter with original builders for common
  subjects, colours, sizes and techniques (always available, deterministic);
* optionally Claude via the official ``anthropic`` SDK, when the package is
  installed and credentials are configured.

Either way the result is only a *proposal*: it must pass :func:`parse_figure`
and is then solved by the deterministic part solver. Neither interpreter ever
supplies stitch counts (ADR-0006). Licensed characters are approximated as
generic shapes; the user owns what they make.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import re
from copy import deepcopy
from typing import Any

from .figure import FigureError, parse_figure, solve_figure
from .figure_templates import TEMPLATES

MAX_TEXT = 2000
CLAUDE_MODEL = "claude-opus-5-5"

COLOR_WORDS: dict[str, tuple[str, str]] = {
    "rot": ("Rot", "#B33A3A"),
    "dunkelrot": ("Dunkelrot", "#7E2A2A"),
    "bordeaux": ("Bordeaux", "#6D2131"),
    "rosa": ("Rosa", "#E9A3B0"),
    "pink": ("Pink", "#D9578A"),
    "orange": ("Orange", "#E2793A"),
    "gelb": ("Gelb", "#F2C94C"),
    "senf": ("Senfgelb", "#C9A227"),
    "grün": ("Grün", "#5E9B4E"),
    "dunkelgrün": ("Dunkelgrün", "#2F5D3A"),
    "mint": ("Mint", "#A8D8C0"),
    "türkis": ("Türkis", "#2FA3A0"),
    "petrol": ("Petrol", "#2F6F73"),
    "blau": ("Blau", "#3C6EB4"),
    "hellblau": ("Hellblau", "#9CC3E6"),
    "dunkelblau": ("Dunkelblau", "#23395B"),
    "lila": ("Lila", "#8E6BB0"),
    "violett": ("Violett", "#6E4A9E"),
    "braun": ("Braun", "#9C6B3F"),
    "hellbraun": ("Hellbraun", "#C49A6C"),
    "dunkelbraun": ("Dunkelbraun", "#5A3B22"),
    "beige": ("Beige", "#E7CFA8"),
    "creme": ("Creme", "#EFE6D2"),
    "weiß": ("Weiß", "#F4F1EA"),
    "weiss": ("Weiß", "#F4F1EA"),
    "grau": ("Grau", "#9A9590"),
    "hellgrau": ("Hellgrau", "#C9C4BE"),
    "dunkelgrau": ("Dunkelgrau", "#4A4A4A"),
    "schwarz": ("Schwarz", "#1E1C1A"),
    "gold": ("Gold", "#C8A04A"),
    "silber": ("Silber", "#B8B8B8"),
}
_COLOR_RE = re.compile(
    r"\b(" + "|".join(sorted(map(re.escape, COLOR_WORDS), key=len, reverse=True))
    + r")(e|er|es|en|em)?\b"
)
_SIZE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(cm|mm|zentimeter|millimeter)\b")
_AREA_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*[x\u00d7]\s*(\d+(?:[.,]\d+)?)\s*(cm|mm)\b")


def _mm(value: str, unit: str) -> float:
    number = float(value.replace(",", "."))
    return number if unit.startswith("m") else number * 10


# ------------------------------------------------------------------ builders
# Original, generic designs. Every builder returns a complete FigureSpec dict.

_BASE_GAUGE = {"stitches_per_100mm": 25, "rows_per_100mm": 28, "hook_mm": 3,
               "yarn": "Baumwolle DK"}


def _animal(
    name: str,
    main: tuple[str, str],
    accent: tuple[str, str],
    *,
    ears: dict[str, Any],
    snout: dict[str, Any] | None = None,
    tail: dict[str, Any] | None = None,
    nose: tuple[str, str] = ("Dunkelbraun", "#2B2118"),
    head_shape: str = "sphere",
    head_size: tuple[float, float] = (54, 54),
    body: tuple[str, float, float] = ("egg", 50, 58),
    paws_accent: bool = False,
) -> dict[str, Any]:
    colors = [
        {"id": "main", "label": main[0], "hex": main[1]},
        {"id": "accent", "label": accent[0], "hex": accent[1]},
        {"id": "dark", "label": nose[0], "hex": nose[1]},
    ]
    paw = [{"from": 0, "to": 0.2, "color": "accent"}] if paws_accent else []
    parts: list[dict[str, Any]] = [
        {"id": "body", "label": "Körper", "shape": body[0], "width_mm": body[1],
         "height_mm": body[2], "color": "main"},
        {"id": "head", "label": "Kopf", "shape": head_shape, "width_mm": head_size[0],
         "height_mm": head_size[1], "color": "main",
         "note": "Beginnt am Scheitel; die letzte Runde ist der Hals.",
         "attach": {"to": "body", "at": 1.0, "angles": [0]}},
    ]
    if snout:
        snout = dict(snout)
        snout_at = snout.pop("at", 0.64)
        parts.append({"id": "snout", "label": "Schnauze", "color": "accent",
                      "stuffing": "light", **snout,
                      "attach": {"to": "head", "at": snout_at, "angles": [0]}})
    parts.append({"id": "ear", "label": "Ohr", "color": "main", "stuffing": "none",
                  **{k: v for k, v in ears.items() if k not in {"at", "angles", "tilt"}},
                  "attach": {"to": "head", "at": ears.get("at", 0.22),
                             "angles": ears.get("angles", [62, 298]),
                             "tilt": ears.get("tilt", 0)}})
    parts.append({"id": "arm", "label": "Arm", "shape": "tube", "width_mm": 14,
                  "height_mm": 30, "end": "flat", "color": "main", "stripes": paw,
                  "attach": {"to": "body", "at": 0.78, "angles": [80, 280], "tilt": 55}})
    parts.append({"id": "leg", "label": "Bein", "shape": "tube", "width_mm": 18,
                  "height_mm": 22, "end": "open", "color": "main", "stripes": paw,
                  "attach": {"to": "body", "at": 0.2, "angles": [40, 320], "tilt": -15}})
    if tail:
        tail = dict(tail)
        tail_tilt = tail.pop("tilt", -35)
        parts.append({"id": "tail", "label": "Schwanz", "color": "main", **tail,
                      "attach": {"to": "body", "at": 0.3, "angles": [180],
                                 "tilt": tail_tilt}})
    features: list[dict[str, Any]] = [
        {"type": "eye", "on": "head", "at": 0.5, "angles": [26, 334], "size_mm": 7,
         "color": "dark"},
        {"type": "nose", "on": "snout" if snout else "head",
         "at": 0.05 if snout else 0.62, "angles": [0], "size_mm": 6, "color": "dark"},
    ]
    return {"name": name, "gauge": dict(_BASE_GAUGE), "colors": colors, "parts": parts,
            "features": features}


def _cat(main: tuple[str, str] = ("Grau", "#9A9590")) -> dict[str, Any]:
    return _animal(
        "Katze", main, ("Weiß", "#F4F1EA"),
        ears={"shape": "cone", "width_mm": 18, "height_mm": 15, "end": "open",
              "at": 0.2, "angles": [50, 310]},
        snout={"shape": "dome", "width_mm": 20, "height_mm": 8, "end": "open", "at": 0.64},
        tail={"shape": "tube", "width_mm": 12, "height_mm": 60, "end": "closed", "tilt": -50},
        nose=("Rosa", "#E9A3B0"), paws_accent=True,
    )


def _fox(main: tuple[str, str] = ("Orange", "#E2793A")) -> dict[str, Any]:
    spec = _animal(
        "Fuchs", main, ("Weiß", "#F4F1EA"),
        ears={"shape": "cone", "width_mm": 20, "height_mm": 20, "end": "open",
              "at": 0.2, "angles": [48, 312]},
        snout={"shape": "cone", "width_mm": 26, "height_mm": 20, "end": "open", "at": 0.62},
        tail={"shape": "tube", "width_mm": 24, "height_mm": 62, "end": "closed", "tilt": -20,
              "stripes": [{"from": 0, "to": 0.25, "color": "accent"}]},
        nose=("Schwarz", "#1E1C1A"),
    )
    for part in spec["parts"]:
        if part["id"] in {"arm", "leg"}:
            part["stripes"] = [{"from": 0, "to": 0.3, "color": "dark"}]
    return spec


def _mouse(main: tuple[str, str] = ("Hellgrau", "#C9C4BE")) -> dict[str, Any]:
    spec = _animal(
        "Maus", main, ("Rosa", "#E9A3B0"),
        ears={"shape": "dome", "width_mm": 28, "height_mm": 8, "end": "flat",
              "at": 0.3, "angles": [60, 300]},
        tail={"shape": "tube", "width_mm": 7, "height_mm": 70, "end": "closed", "tilt": -10},
        nose=("Rosa", "#E9A3B0"), head_shape="ellipsoid", head_size=(46, 42),
        body=("pear", 46, 56),
    )
    spec["parts"][-1]["color"] = "accent"
    return spec


def _pig(main: tuple[str, str] = ("Rosa", "#E9A3B0")) -> dict[str, Any]:
    spec = _animal(
        "Schwein", main, ("Altrosa", "#D98896"),
        ears={"shape": "cone", "width_mm": 18, "height_mm": 14, "end": "open",
              "at": 0.2, "angles": [55, 305], "tilt": -20},
        snout={"shape": "cylinder", "width_mm": 24, "height_mm": 9, "end": "open", "at": 0.62},
        nose=("Dunkelrosa", "#A65466"), body=("sphere", 58, 58),
    )
    spec["features"][1] = {"type": "nose", "on": "snout", "at": 0.3, "angles": [90, 270],
                           "size_mm": 4, "color": "dark", "label": "Nasenlöcher"}
    return spec


def _frog(main: tuple[str, str] = ("Grün", "#5E9B4E")) -> dict[str, Any]:
    spec = _animal(
        "Frosch", main, ("Hellgrün", "#B7D99A"),
        ears={"shape": "dome", "width_mm": 8, "height_mm": 4, "end": "flat",
              "at": 0.95, "angles": [180]},
        nose=("Schwarz", "#1E1C1A"), head_shape="ellipsoid", head_size=(62, 44),
        body=("egg", 54, 50),
    )
    # Frogs have no ears: replace them with two eye bulbs, each with a safety eye.
    spec["parts"] = [p for p in spec["parts"] if p["id"] != "ear"]
    for side, angle in (("l", 32), ("r", 328)):
        spec["parts"].append(
            {"id": f"eye_{side}", "label": f"Augenwulst {'links' if side == 'l' else 'rechts'}",
             "shape": "sphere", "width_mm": 18, "height_mm": 18, "color": "main",
             "attach": {"to": "head", "at": 0.22, "angles": [angle]}})
    spec["features"] = [
        {"type": "eye", "on": "eye_l", "at": 0.35, "angles": [0], "size_mm": 7, "color": "dark"},
        {"type": "eye", "on": "eye_r", "at": 0.35, "angles": [0], "size_mm": 7, "color": "dark"},
    ]
    return spec


def _snowman(main: tuple[str, str] = ("Weiß", "#F4F1EA")) -> dict[str, Any]:
    return {
        "name": "Schneemann",
        "gauge": dict(_BASE_GAUGE),
        "colors": [
            {"id": "main", "label": main[0], "hex": main[1]},
            {"id": "carrot", "label": "Orange", "hex": "#E2793A"},
            {"id": "dark", "label": "Schwarz", "hex": "#1E1C1A"},
        ],
        "parts": [
            {"id": "base", "label": "Unterteil", "shape": "sphere", "width_mm": 70,
             "height_mm": 70, "color": "main"},
            {"id": "middle", "label": "Mittelteil", "shape": "sphere", "width_mm": 54,
             "height_mm": 54, "color": "main",
             "attach": {"to": "base", "at": 1.0, "angles": [0]}},
            {"id": "head", "label": "Kopf", "shape": "sphere", "width_mm": 42,
             "height_mm": 42, "color": "main",
             "attach": {"to": "middle", "at": 0.0, "angles": [0]}},
            {"id": "nose", "label": "Karottennase", "shape": "cone", "width_mm": 9,
             "height_mm": 18, "end": "open", "color": "carrot", "stuffing": "light",
             "attach": {"to": "head", "at": 0.62, "angles": [0]}},
            {"id": "hat", "label": "Hut", "shape": "cylinder", "width_mm": 30,
             "height_mm": 24, "end": "closed", "color": "dark",
             "attach": {"to": "head", "at": 0.0, "angles": [0]}},
        ],
        "features": [
            {"type": "eye", "on": "head", "at": 0.5, "angles": [30, 330], "size_mm": 6,
             "color": "dark"},
            {"type": "nose", "on": "middle", "at": 0.5, "angles": [0], "size_mm": 6,
             "color": "dark", "label": "Knopf"},
        ],
    }


def _mushroom(main: tuple[str, str] = ("Rot", "#B33A3A")) -> dict[str, Any]:
    return {
        "name": "Pilz",
        "gauge": dict(_BASE_GAUGE),
        "colors": [
            {"id": "stalk", "label": "Creme", "hex": "#EFE6D2"},
            {"id": "cap", "label": main[0], "hex": main[1]},
            {"id": "dark", "label": "Schwarz", "hex": "#1E1C1A"},
        ],
        "parts": [
            {"id": "stalk", "label": "Stiel", "shape": "cylinder", "width_mm": 34,
             "height_mm": 40, "end": "closed", "color": "stalk"},
            {"id": "cap", "label": "Hut", "shape": "dome", "width_mm": 72, "height_mm": 34,
             "end": "open", "color": "cap", "stuffing": "light",
             "note": "Die Hutunterseite bleibt offen; Stiel mittig hineinsetzen und annähen.",
             "attach": {"to": "stalk", "at": 1.0, "angles": [0]}},
        ],
        "features": [
            {"type": "eye", "on": "stalk", "at": 0.6, "angles": [18, 342], "size_mm": 6,
             "color": "dark"},
        ],
    }


def _ball(main: tuple[str, str] = ("Blau", "#3C6EB4")) -> dict[str, Any]:
    return {
        "name": "Kugel",
        "gauge": dict(_BASE_GAUGE),
        "colors": [{"id": "main", "label": main[0], "hex": main[1]}],
        "parts": [{"id": "ball", "label": "Kugel", "shape": "sphere", "width_mm": 60,
                   "height_mm": 60, "color": "main"}],
    }


def _template(key: str) -> Any:
    def build(main: tuple[str, str] | None = None) -> dict[str, Any]:
        spec = deepcopy(TEMPLATES[key])
        if main is not None:
            first = spec["colors"][0]
            first["label"], first["hex"] = main
        return spec
    return build


# (keywords, builder, label); first match in the text wins.
SUBJECTS: tuple[tuple[tuple[str, ...], Any, str], ...] = (
    (("schneemann",), _snowman, "Schneemann"),
    (("teddy", "bär", "baer", "bärchen"), _template("teddy"), "Teddybär"),
    (("hase", "häschen", "kaninchen", "hasen"), _template("bunny"), "Hase"),
    (("katze", "kater", "kätzchen", "mieze"), _cat, "Katze"),
    (("fuchs", "füchschen"), _fox, "Fuchs"),
    (("maus", "mäuschen", "mäuse"), _mouse, "Maus"),
    (("schwein", "ferkel", "schweinchen"), _pig, "Schwein"),
    (("frosch", "kröte"), _frog, "Frosch"),
    (("küken", "kueken", "vogel", "ente", "huhn", "hähnchen", "spatz"),
     _template("chick"), "Küken/Vogel"),
    (("pilz", "fliegenpilz"), _mushroom, "Pilz"),
    (("strickmütze",), _template("beanie_knit"), "Strickmütze"),
    (("mütze", "muetze", "beanie", "haube"), _template("beanie"), "Mütze"),
    (("schal", "loop"), _template("scarf"), "Schal"),
    (("decke", "babydecke", "plaid"), _template("blanket"), "Decke"),
    (("untersetzer", "topflappen", "teppich", "deckchen"), _template("coaster"), "Untersetzer"),
    (("kugel", "ball", "bommel"), _ball, "Kugel"),
)


def _scale_spec(spec: dict[str, Any], factor: float) -> None:
    for part in spec["parts"]:
        for key in ("width_mm", "height_mm", "circumference_mm"):
            if key in part:
                part[key] = round(part[key] * factor, 1)
    for feature in spec.get("features", []):
        feature["size_mm"] = round(min(40, max(2, feature["size_mm"] * factor)), 1)


def compose_offline(text: str) -> dict[str, Any]:
    """Deterministic German keyword interpretation into a validated FigureSpec."""
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
        raise FigureError("compose.text", f"Beschreibung mit 1 bis {MAX_TEXT} Zeichen erwartet.")
    lowered = text.lower()
    notes: list[str] = []
    builder, label = None, ""
    for keywords, candidate, candidate_label in SUBJECTS:
        if any(re.search(rf"\b{re.escape(k)}", lowered) for k in keywords):
            builder, label = candidate, candidate_label
            break
    if builder is None:
        builder, label = _ball, "Kugel"
        notes.append(
            "Kein bekanntes Motiv erkannt - Start mit einer einfachen Kugel. Bekannt sind: "
            + ", ".join(s[2] for s in SUBJECTS) + "."
        )
    else:
        notes.append(f"Motiv: {label}.")
    color_match = _COLOR_RE.search(lowered)
    main = COLOR_WORDS[color_match.group(1)] if color_match else None
    spec = builder(main) if main else builder()
    if main:
        notes.append(f"Hauptfarbe: {main[0]}.")
    if "strick" in lowered and spec.get("technique") != "knit":
        spec["technique"] = "knit"
        spec["gauge"] = {"stitches_per_100mm": 22, "rows_per_100mm": 30, "hook_mm": 3,
                         "yarn": spec["gauge"].get("yarn", "")}
        notes.append("Technik: Stricken (Maschenprobe 22 M x 30 R als Startwert).")
    if re.search(r"\b(dick|chunky|grob)", lowered):
        spec["gauge"].update(stitches_per_100mm=14, rows_per_100mm=16, hook_mm=6)
        notes.append("Dickes Garn: Maschenprobe 14 x 16 als Startwert.")
    elif re.search(r"\b(dünn|fein)", lowered):
        spec["gauge"].update(stitches_per_100mm=30, rows_per_100mm=34, hook_mm=2.5)
        notes.append("Dünnes Garn: Maschenprobe 30 x 34 als Startwert.")

    root = spec["parts"][0]
    flat = root["shape"] in {"rectangle", "disc"}
    head = re.search(r"kopfumfang\D{0,12}(\d+(?:[.,]\d+)?)\s*(cm|mm)", lowered)
    area = _AREA_RE.search(lowered)
    if head and "circumference_mm" in root:
        circumference = _mm(head.group(1), head.group(2))
        knit = spec.get("technique") == "knit"
        root["circumference_mm"] = round(circumference * (0.9 if knit else 0.93), 1)
        root["height_mm"] = round(circumference * 0.37, 1)
        root["note"] = (f"Kopfumfang {circumference / 10:g} cm, Mützenumfang "
                        f"{root['circumference_mm'] / 10:g} cm (leicht gedehnt).")
        spec["name"] = re.sub(r"\(Kopfumfang [^)]*\)",
                              f"(Kopfumfang {circumference / 10:g} cm)", spec["name"])
        notes.append(f"Kopfumfang {circumference / 10:g} cm übernommen.")
    elif area and flat:
        root["width_mm"] = _mm(area.group(1), area.group(3))
        root["height_mm"] = _mm(area.group(2), area.group(3))
        notes.append(f"Maße {root['width_mm'] / 10:g} x {root['height_mm'] / 10:g} cm.")
    else:
        size = _SIZE_RE.search(lowered)
        factor = None
        if size:
            target = _mm(size.group(1), size.group(2))
            if flat and root["shape"] == "disc":
                root["width_mm"] = target
                notes.append(f"Durchmesser {target / 10:g} cm.")
            elif flat:
                root["height_mm"] = target
                notes.append(f"Länge {target / 10:g} cm.")
            else:
                bounds = solve_figure(spec)["bounds_mm"]
                height = bounds["max"][1] - bounds["min"][1]
                factor = target / height
                notes.append(f"Auf ca. {target / 10:g} cm Höhe skaliert.")
        elif re.search(r"\b(winzig|mini)", lowered):
            factor = 0.6
        elif re.search(r"\bklein", lowered):
            factor = 0.75
        elif re.search(r"\b(riesig|sehr groß)", lowered):
            factor = 1.8
        elif re.search(r"\bgroß", lowered):
            factor = 1.35
        if factor is not None:
            factor = min(3.0, max(0.4, factor))
            if not flat:
                _scale_spec(spec, factor)
            if not size:
                notes.append(f"Größe: Faktor {factor:g} gegenüber der Vorlage.")
    if main and not label.startswith(("Mütze", "Strick", "Schal", "Decke", "Unters", "Kugel")):
        spec["name"] = f"{spec['name']} in {main[0]}"
    parse_figure(spec)  # proposals must be valid FigureSpecs
    return {"spec": spec, "source": "offline", "notes_de": notes}


# ------------------------------------------------------------------ Claude

_SYSTEM = """You design amigurumi and simple crochet/knit projects as a strict JSON \
"FigureSpec". A deterministic solver computes all stitch counts; you never output \
stitch counts or rounds. Reply with exactly one JSON object and nothing else.

Format:
{"name": str, "technique": "crochet"|"knit",
 "gauge": {"stitches_per_100mm": 5-60, "rows_per_100mm": 5-60, "hook_mm": number, "yarn": str},
 "colors": [{"id": "lowercase_id", "label": "German name", "hex": "#RRGGBB"}],
 "parts": [{"id": "lowercase_id", "label": "German name", "shape": SHAPE,
            "width_mm": number (or "circumference_mm"), "height_mm": number,
            "end": END, "color": color_id,
            "stripes": [{"from": 0-1, "to": 0-1, "color": color_id}] (optional),
            "stuffing": "full"|"light"|"none" (optional), "note": str (optional),
            "attach": {"to": earlier_part_id, "at": 0-1, "angles": [deg,...],
                       "tilt": -85..85} (all parts except the first)}],
 "features": [{"type": "eye"|"nose", "on": part_id, "at": 0-1, "angles": [deg],
               "size_mm": 2-40, "color": color_id, "label": str (optional)}]}

Shapes and allowed ends (first is default): sphere/ellipsoid/egg/pear/capsule: closed; \
dome: open|flat; tube: open|flat|closed; cone: closed|open; cylinder: closed|open; \
disc: open; rectangle: open. disc/rectangle are flat projects: only as the single part.
Rules: the first part is the body (no attach). A part may only attach to an earlier \
part that has exactly one angle. "at" is the fraction of the host's rounds (0 = magic \
ring, 1 = last round); angles: 0 front, 90 viewer's right, 180 back, 270 left; several \
angles create several copies (e.g. [80, 280] for two arms). A head attached at the \
body's top (at 1.0) is worked from the crown, so on the head at 0 is the crown. Arms: \
tube with end "flat", tilt about 50. Legs: tube "open". Ears: dome "flat" or cone \
"open". Snouts: dome "open". Sizes in millimetres; a typical amigurumi is 100-200 mm \
tall at 25 stitches x 28 rows per 100 mm. Features on parts with several copies are \
not allowed. Interpret characters as original, generic stylised designs (shapes and \
colours), never copying logos or text. Keep ids unique; labels in German."""


def claude_available() -> bool:
    return importlib.util.find_spec("anthropic") is not None


def _extract_json(text: str) -> Any:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object")
    return json.loads(text[start : end + 1])


def compose_with_claude(text: str, *, client: Any = None) -> dict[str, Any]:
    """Ask Claude for a FigureSpec; validate it and allow one repair round."""
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
        raise FigureError("compose.text", f"Beschreibung mit 1 bis {MAX_TEXT} Zeichen erwartet.")
    if client is None:
        if not claude_available():
            raise FigureError("compose.unavailable",
                              "Claude ist nicht eingerichtet (Paket anthropic fehlt).")
        anthropic = importlib.import_module("anthropic")
        client = anthropic.Anthropic()
    else:
        anthropic = None
    messages: list[dict[str, Any]] = [{"role": "user", "content": text}]
    last_error = ""
    for _attempt in range(2):
        try:
            response = client.beta.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=16000,
                output_config={"effort": "medium"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=_SYSTEM,
                messages=messages,
            )
        except Exception as error:  # SDK error classes are only known at runtime
            raise FigureError("compose.api", _api_error_message(error, anthropic)) from error
        if response.stop_reason == "refusal":
            raise FigureError("compose.refusal", "Claude hat diese Anfrage abgelehnt.")
        reply = "".join(block.text for block in response.content if block.type == "text")
        try:
            spec = _extract_json(reply)
            parse_figure(spec)
            return {"spec": spec, "source": "claude",
                    "notes_de": [f"Von Claude ({response.model}) entworfen und geprüft."]}
        except (ValueError, FigureError) as error:
            last_error = getattr(error, "message_de", str(error))
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content":
                             f"The JSON was rejected: {last_error}. Reply with a corrected "
                             "complete JSON object only."})
    raise FigureError("compose.invalid", f"Claude-Entwurf ungültig: {last_error}")


def _api_error_message(error: Exception, anthropic: Any) -> str:
    if anthropic is not None:
        if isinstance(error, anthropic.AuthenticationError):
            return "Kein gültiger Anthropic-Zugang (API-Schlüssel oder ant auth login)."
        if isinstance(error, anthropic.RateLimitError):
            return "Claude ist gerade ausgelastet, bitte später erneut versuchen."
        if isinstance(error, anthropic.APIConnectionError):
            return "Keine Verbindung zu Claude."
        if isinstance(error, anthropic.APIStatusError):
            return f"Claude-Fehler (HTTP {error.status_code})."
    return f"Claude-Anfrage fehlgeschlagen: {type(error).__name__}."


def compose(text: str, *, use_claude: bool = False) -> dict[str, Any]:
    """Claude when requested and available, otherwise the offline interpreter."""
    if use_claude:
        return compose_with_claude(text)
    return compose_offline(text)
