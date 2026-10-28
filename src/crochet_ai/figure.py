"""Multi-part amigurumi figures: parts, assembly positions and a schematic 3D layout.

A ``FigureSpec`` lists rotational parts (solved by :mod:`figure_parts`), where
each non-root part is sewn onto an earlier part, plus small features such as
safety eyes. Positions are expressed in crochet terms: a fraction of the host's
rounds (``at``, 0 = magic ring, 1 = last round) and an angle around the host
(0 = front, 90 = viewer's right, 180 = back). The solver turns these into
"round k, stitch j" instructions and places every part in one figure frame.

Everything here is a construction proposal: NOT_VERIFIED / UNTESTED. The 3D
layout is schematic (round radii from stitch counts, rigid parts), not a
physical simulation of stuffing or seams.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from math import cos, floor, isfinite, pi, radians, sin, sqrt
from typing import Any

from .figure_parts import (
    END_MODES,
    PART_SOLVER_VERSION,
    SHAPE_ENDS,
    STUFFING,
    Gauge,
    PartError,
    PartSchedule,
    part_summary,
    round_line,
    solve_part,
)

FIGURE_VERSION = "figure-1"
MAX_PARTS = 24
MAX_INSTANCES = 8
MAX_FEATURES = 16
FEATURE_TYPES = ("eye", "nose")
_ID = re.compile(r"[a-z][a-z0-9_]{0,31}")
_HEX = re.compile(r"#[0-9A-Fa-f]{6}")

Vec = tuple[float, float, float]


class FigureError(ValueError):
    """Invalid figure request; ``message_de`` explains it to the user."""

    def __init__(self, code: str, message_de: str) -> None:
        super().__init__(code)
        self.code = code
        self.message_de = message_de


# ------------------------------------------------------------------ vectors


def _add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _mul(a: Vec, k: float) -> Vec:
    return (a[0] * k, a[1] * k, a[2] * k)


def _dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a: Vec) -> Vec:
    length = sqrt(_dot(a, a))
    return (0.0, 1.0, 0.0) if length < 1e-12 else _mul(a, 1 / length)


@dataclass(frozen=True, slots=True)
class Frame:
    """Part instance frame: ``origin`` is the magic ring, ``axis`` points to the end."""

    origin: Vec
    axis: Vec
    front: Vec

    @property
    def side(self) -> Vec:
        return _cross(self.axis, self.front)

    def radial(self, theta_deg: float) -> Vec:
        t = radians(theta_deg)
        return _add(_mul(self.side, sin(t)), _mul(self.front, cos(t)))

    def tangent(self, theta_deg: float) -> Vec:
        t = radians(theta_deg)
        return _sub(_mul(self.side, cos(t)), _mul(self.front, sin(t)))

    def point(self, axial: float, radius: float, theta_deg: float) -> Vec:
        return _add(_add(self.origin, _mul(self.axis, axial)), _mul(self.radial(theta_deg), radius))


def _frame_angle(frame: Frame, theta_user: float) -> float:
    """User angles increase towards the viewer's right; frames whose side vector
    points left (e.g. a head worked from the crown down) are mirrored."""
    return (360 - theta_user) % 360 if frame.side[0] < -1e-6 else theta_user


def _frame_for_axis(origin: Vec, axis: Vec) -> Frame:
    reference: Vec = (0.0, 0.0, 1.0)
    projected = _sub(reference, _mul(axis, _dot(reference, axis)))
    if _dot(projected, projected) < 0.09:
        reference = (0.0, 1.0, 0.0)
        projected = _sub(reference, _mul(axis, _dot(reference, axis)))
    return Frame(origin, axis, _norm(projected))


# ------------------------------------------------------------------ parsing


def _number(value: object, low: float, high: float, where: str) -> float:
    if type(value) not in {int, float} or not isfinite(float(value)):  # type: ignore[arg-type]
        raise FigureError(f"{where}.type", f"{where}: Zahl erwartet.")
    number = float(value)  # type: ignore[arg-type]
    if not low <= number <= high:
        raise FigureError(
            f"{where}.range", f"{where}: Wert muss zwischen {low:g} und {high:g} liegen."
        )
    return number


def _text(value: object, where: str, maximum: int = 80, *, required: bool = True) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > maximum:
        raise FigureError(f"{where}.text", f"{where}: Text (max. {maximum} Zeichen) erwartet.")
    return value.strip()


def _ident(value: object, where: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise FigureError(
            f"{where}.id", f"{where}: ID aus Kleinbuchstaben, Ziffern und _ erwartet."
        )
    return value


def _fields(value: object, allowed: set[str], required: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FigureError(f"{where}.object", f"{where}: Objekt erwartet.")
    unknown = set(value) - allowed
    missing = required - set(value)
    if unknown:
        raise FigureError(f"{where}.unknown", f"{where}: unbekanntes Feld „{sorted(unknown)[0]}“.")
    if missing:
        raise FigureError(f"{where}.missing", f"{where}: Feld „{sorted(missing)[0]}“ fehlt.")
    return value


def _angles(value: object, where: str) -> tuple[float, ...]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_INSTANCES:
        raise FigureError(
            f"{where}.angles", f"{where}: Liste mit 1 bis {MAX_INSTANCES} Winkeln erwartet."
        )
    return tuple(_number(a, -360, 360, f"{where}.angles") % 360 for a in value)


@dataclass(frozen=True, slots=True)
class Attachment:
    to: str
    at: float
    angles: tuple[float, ...]
    tilt_deg: float


@dataclass(frozen=True, slots=True)
class PartSpec:
    id: str
    label: str
    shape: str
    width_mm: float
    height_mm: float
    end: str
    color: str
    stripes: tuple[tuple[float, float, str], ...]
    stuffing: str | None
    note: str
    attach: Attachment | None
    start_top: bool


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    type: str
    on: str
    at: float
    angles: tuple[float, ...]
    size_mm: float
    color: str
    label: str


@dataclass(frozen=True, slots=True)
class FigureSpec:
    name: str
    gauge: Gauge
    hook_mm: float
    yarn: str
    colors: dict[str, tuple[str, str]]  # id -> (label, hex)
    parts: tuple[PartSpec, ...]
    features: tuple[FeatureSpec, ...]


def parse_figure(value: object) -> FigureSpec:
    """Strict, closed parsing with German error messages; never repairs input."""
    data = _fields(
        value,
        {"name", "gauge", "colors", "parts", "features"},
        {"name", "gauge", "colors", "parts"},
        "Figur",
    )
    name = _text(data["name"], "Figur.name")
    gauge_data = _fields(
        data["gauge"],
        {"stitches_per_100mm", "rows_per_100mm", "hook_mm", "yarn"},
        {"stitches_per_100mm", "rows_per_100mm"},
        "Maschenprobe",
    )
    gauge = Gauge(
        _number(gauge_data["stitches_per_100mm"], 5, 60, "Maschenprobe.Maschen"),
        _number(gauge_data["rows_per_100mm"], 5, 60, "Maschenprobe.Runden"),
    )
    hook = _number(gauge_data.get("hook_mm", 3), 0.5, 15, "Maschenprobe.Nadel")
    yarn = _text(gauge_data.get("yarn"), "Maschenprobe.Garn", 120, required=False)

    if not isinstance(data["colors"], list) or not 1 <= len(data["colors"]) <= 12:
        raise FigureError("colors.list", "Farben: Liste mit 1 bis 12 Farben erwartet.")
    colors: dict[str, tuple[str, str]] = {}
    for item in data["colors"]:
        entry = _fields(item, {"id", "label", "hex"}, {"id", "label", "hex"}, "Farbe")
        color_id = _ident(entry["id"], "Farbe.id")
        if color_id in colors:
            raise FigureError("colors.duplicate", f"Farbe „{color_id}“ ist doppelt.")
        if not isinstance(entry["hex"], str) or _HEX.fullmatch(entry["hex"]) is None:
            raise FigureError("colors.hex", f"Farbe „{color_id}“: Hex-Wert wie #A07850 erwartet.")
        colors[color_id] = (_text(entry["label"], "Farbe.label", 40), entry["hex"].upper())

    def color_ref(ref: object, where: str) -> str:
        if not isinstance(ref, str) or ref not in colors:
            raise FigureError(f"{where}.color", f"{where}: unbekannte Farbe „{ref}“.")
        return ref

    if not isinstance(data["parts"], list) or not 1 <= len(data["parts"]) <= MAX_PARTS:
        raise FigureError("parts.list", f"Teile: Liste mit 1 bis {MAX_PARTS} Teilen erwartet.")
    parts: list[PartSpec] = []
    seen: dict[str, PartSpec] = {}
    for item in data["parts"]:
        entry = _fields(
            item,
            {"id", "label", "shape", "width_mm", "circumference_mm", "height_mm", "end",
             "color", "stripes", "stuffing", "note", "attach", "start"},
            {"id", "label", "shape", "height_mm", "color"},
            "Teil",
        )
        part_id = _ident(entry["id"], "Teil.id")
        where = f"Teil „{part_id}“"
        if part_id in seen:
            raise FigureError("parts.duplicate", f"{where} ist doppelt.")
        shape = entry["shape"]
        if shape not in SHAPE_ENDS:
            raise FigureError("parts.shape", f"{where}: unbekannte Form „{shape}“.")
        if ("width_mm" in entry) == ("circumference_mm" in entry):
            raise FigureError(
                "parts.width", f"{where}: genau eines von width_mm oder circumference_mm angeben."
            )
        width = (
            _number(entry["width_mm"], 4, 300, f"{where}.width_mm")
            if "width_mm" in entry
            else _number(entry["circumference_mm"], 12, 950, f"{where}.circumference_mm") / pi
        )
        height = _number(entry["height_mm"], 3, 400, f"{where}.height_mm")
        end = entry.get("end", SHAPE_ENDS[shape][0])
        if end not in END_MODES or end not in SHAPE_ENDS[shape]:
            raise FigureError(
                "parts.end",
                f"{where}: Ende „{end}“ passt nicht zu {shape} (erlaubt: "
                f"{', '.join(SHAPE_ENDS[shape])}).",
            )
        stuffing = entry.get("stuffing")
        if stuffing is not None and stuffing not in STUFFING:
            raise FigureError("parts.stuffing", f"{where}: Füllung full, light oder none.")
        stripes: list[tuple[float, float, str]] = []
        raw_stripes = entry.get("stripes", [])
        if not isinstance(raw_stripes, list) or len(raw_stripes) > 16:
            raise FigureError("parts.stripes", f"{where}: höchstens 16 Streifen.")
        for stripe in raw_stripes:
            keys = {"from", "to", "color"}
            band = _fields(stripe, keys, keys, f"{where}.Streifen")
            start = _number(band["from"], 0, 1, f"{where}.Streifen.from")
            stop = _number(band["to"], 0, 1, f"{where}.Streifen.to")
            if stop <= start:
                raise FigureError("parts.stripes", f"{where}: Streifen braucht from < to.")
            stripes.append((start, stop, color_ref(band["color"], f"{where}.Streifen")))
        start = entry.get("start", "bottom")
        if start not in {"bottom", "top"} or ("start" in entry and "attach" in entry):
            raise FigureError(
                "parts.start", f"{where}: start (bottom/top) gibt es nur beim Grundkörper."
            )
        start_top = start == "top"
        attach = None
        if "attach" in entry:
            raw = _fields(entry["attach"], {"to", "at", "angles", "tilt"}, {"to", "at", "angles"},
                          f"{where}.attach")
            host = raw["to"]
            if host not in seen:
                raise FigureError(
                    "parts.host",
                    f"{where}: „{host}“ muss ein vorher definiertes Teil sein.",
                )
            if seen[host].attach is not None and len(seen[host].attach.angles) > 1:  # type: ignore[union-attr]
                raise FigureError(
                    "parts.host_instances",
                    f"{where}: An Teile mit mehreren Exemplaren kann noch nichts angenäht werden.",
                )
            attach = Attachment(
                host,
                _number(raw["at"], 0, 1, f"{where}.at"),
                _angles(raw["angles"], where),
                _number(raw.get("tilt", 0), -85, 85, f"{where}.tilt"),
            )
        spec = PartSpec(
            part_id,
            _text(entry["label"], f"{where}.label", 40),
            shape,
            width,
            height,
            end,
            color_ref(entry["color"], where),
            tuple(stripes),
            stuffing,
            _text(entry.get("note"), f"{where}.note", 300, required=False),
            attach,
            start_top,
        )
        parts.append(spec)
        seen[part_id] = spec
    roots = [p for p in parts if p.attach is None]
    if len(roots) != 1 or roots[0] is not parts[0]:
        raise FigureError(
            "parts.root",
            "Genau ein Teil (das erste) darf keine Befestigung haben: der Grundkörper.",
        )
    features: list[FeatureSpec] = []
    raw_features = data.get("features", [])
    if not isinstance(raw_features, list) or len(raw_features) > MAX_FEATURES:
        raise FigureError("features.list", f"Details: höchstens {MAX_FEATURES} Einträge.")
    for item in raw_features:
        entry = _fields(item, {"type", "on", "at", "angles", "size_mm", "color", "label"},
                        {"type", "on", "at", "angles", "size_mm", "color"}, "Detail")
        if entry["type"] not in FEATURE_TYPES:
            raise FigureError(
                "features.type", f"Detail: Typ eye oder nose, nicht „{entry['type']}“."
            )
        host = entry["on"]
        if host not in seen:
            raise FigureError("features.host", f"Detail: unbekanntes Teil „{host}“.")
        if seen[host].attach is not None and len(seen[host].attach.angles) > 1:  # type: ignore[union-attr]
            raise FigureError("features.host_instances",
                              "Detail: Teile mit mehreren Exemplaren werden nicht unterstützt.")
        features.append(
            FeatureSpec(
                entry["type"],
                host,
                _number(entry["at"], 0, 1, "Detail.at"),
                _angles(entry["angles"], "Detail"),
                _number(entry["size_mm"], 2, 40, "Detail.size_mm"),
                color_ref(entry["color"], "Detail"),
                _text(entry.get("label"), "Detail.label", 40, required=False),
            )
        )
    return FigureSpec(name, gauge, hook, yarn, colors, tuple(parts), tuple(features))


# ------------------------------------------------------------------ geometry


@dataclass(frozen=True, slots=True)
class Instance:
    part: PartSpec
    schedule: PartSchedule
    frame: Frame
    label: str
    flatten_across: Vec | None  # direction squashed for flat ends


def _surface(
    schedule: PartSchedule, frame: Frame, at: float, theta: float
) -> tuple[Vec, Vec, float]:
    """Point, outward normal and target radius at an arc fraction and angle."""
    profile = schedule.profile
    s = at * profile.length_mm
    axial, radius = profile.at(s)
    d_axial, d_radius = profile.tangent(s)
    normal = _norm(_sub(_mul(frame.radial(theta), d_axial), _mul(frame.axis, d_radius)))
    return frame.point(axial, radius, theta), normal, radius


def _side_label(theta: float) -> str:
    if theta < 15 or theta > 345:
        return "vorne"
    if 165 < theta < 195:
        return "hinten"
    return "rechts" if theta < 180 else "links"


def _stitch_at(schedule: PartSchedule, round_number: int, theta: float) -> tuple[int, int]:
    """1-based stitch from the round marker (back, 180°), counted in working direction.

    Right-handed crochet viewed from outside runs right to left across the front,
    i.e. towards decreasing angle in this convention.
    """
    n = schedule.rounds[round_number - 1].count
    delta = (180 - theta) % 360
    return min(floor(delta / 360 * n) + 1, n), n


def _end_radius(schedule: PartSchedule) -> float:
    return schedule.rounds[-1].count * schedule.gauge.stitch_pitch_mm / (2 * pi)


# ------------------------------------------------------------------ solving

_FINISH = {
    "closed": (
        "Faden abschneiden, durch die vorderen Maschenglieder der letzten {n} M fädeln, "
        "fest zusammenziehen und vernähen.",
        "Fasten off, weave the tail through the front loops of the last {n} sts, pull tight "
        "and weave in.",
    ),
    "open": (
        "1 Km, Faden ca. 30 cm lang abschneiden (zum Annähen).",
        "Sl st, fasten off leaving a long tail (about 30 cm) for sewing.",
    ),
    "open_final": (
        "1 Km, Faden abschneiden und vernähen.",
        "Sl st, fasten off and weave in the tail.",
    ),
    "flat_even": (
        "Öffnung flach drücken und mit {half} fM durch beide Lagen schließen. "
        "Faden zum Annähen lang lassen.",
        "Flatten the opening and close it with {half} sc through both layers. "
        "Leave a long tail for sewing.",
    ),
    "flat_odd": (
        "Öffnung flach drücken und zusammennähen. Faden zum Annähen lang lassen.",
        "Flatten the opening and sew it shut. Leave a long tail for sewing.",
    ),
}
_STUFF = {
    "full": ("Fest füllen.", "Stuff firmly."),
    "light": ("Nur leicht füllen.", "Stuff lightly."),
    "none": ("Nicht füllen.", "Do not stuff."),
}


def _finish(schedule: PartSchedule, sewn_on: bool) -> tuple[str, str]:
    n = schedule.rounds[-1].count
    if schedule.end == "closed":
        key = "closed"
    elif schedule.end == "open":
        key = "open" if sewn_on else "open_final"
    else:
        key = "flat_even" if n % 2 == 0 else "flat_odd"
    de, en = _FINISH[key]
    stuff_de, stuff_en = _STUFF[schedule.stuffing]
    if schedule.end == "closed" or (key == "open_final" and schedule.stuffing == "none"):
        return de.format(n=n), en.format(n=n)
    return f"{stuff_de} {de.format(half=n // 2)}", f"{stuff_en} {en.format(half=n // 2)}"


def solve_figure(value: object) -> dict[str, Any]:
    """Solve every part, place all instances and derive assembly instructions."""
    spec = parse_figure(value)
    p_s, p_c = spec.gauge.stitch_pitch_mm, spec.gauge.course_pitch_mm
    schedules: dict[str, PartSchedule] = {}
    for part in spec.parts:
        try:
            schedules[part.id] = solve_part(
                part.shape, part.width_mm, part.height_mm, part.end, spec.gauge,
                color=part.color, stripes=part.stripes, stuffing=part.stuffing,
            )
        except PartError as error:
            raise FigureError(error.code, f"Teil „{part.label}“: {error.message_de}") from error

    instances: dict[str, list[Instance]] = {}
    assembly: list[dict[str, Any]] = []
    for part in spec.parts:
        schedule = schedules[part.id]
        if part.attach is None:
            # The root stands on its magic ring, or hangs from it (e.g. a hat crown).
            height = schedule.profile.height_mm
            frame = (
                Frame((0.0, height, 0.0), (0.0, -1.0, 0.0), (0.0, 0.0, 1.0))
                if part.start_top
                else Frame((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
            )
            instances[part.id] = [Instance(part, schedule, frame, part.label, None)]
            continue
        host = instances[part.attach.to][0]
        attached = []
        for index, user_theta in enumerate(part.attach.angles):
            theta = _frame_angle(host.frame, user_theta)
            point, normal, host_radius = _surface(host.schedule, host.frame, part.attach.at, theta)
            outward = normal
            if part.attach.tilt_deg:
                down: Vec = (0.0, -1.0, 0.0)
                perpendicular = _sub(down, _mul(outward, _dot(down, outward)))
                if _dot(perpendicular, perpendicular) > 1e-9:
                    t = radians(part.attach.tilt_deg)
                    outward = _norm(
                        _add(_mul(outward, cos(t)), _mul(_norm(perpendicular), sin(t)))
                    )
            axis = _mul(outward, -1)
            end_axial = schedule.profile.points[-1][0]
            sink = 0.12 * schedule.profile.height_mm if part.end == "closed" else 0.0
            end_center = _sub(point, _mul(outward, sink))
            frame = _frame_for_axis(_sub(end_center, _mul(axis, end_axial)), axis)
            flatten = None
            if part.end == "flat":
                flatten = _norm(_cross(axis, host.frame.tangent(theta)))
            label = part.label
            if len(part.attach.angles) > 1:
                label = f"{part.label} {index + 1} ({_side_label(user_theta)})"
            attached.append(Instance(part, schedule, frame, label, flatten))
            assembly.append(
                _assembly_step(part, schedule, host, theta, host_radius, label, p_s)
            )
        instances[part.id] = attached

    feature_steps, feature_points, round_notes = _features(spec, instances, p_s)
    parts_out = []
    for part in spec.parts:
        schedule = schedules[part.id]
        summary = part_summary(schedule)
        notes: dict[int, list[str]] = {}
        previous = part.color
        if schedule.rounds[0].color != part.color:
            notes.setdefault(1, []).append(
                f"Mit {spec.colors[schedule.rounds[0].color][0]} beginnen."
            )
            previous = schedule.rounds[0].color
        for r in schedule.rounds:
            if r.color != previous:
                label = spec.colors[r.color][0]
                notes.setdefault(r.number, []).append(
                    f"Farbwechsel zu {label}: die letzte Masche von R{r.number - 1} "
                    f"mit {label} abmaschen."
                )
            previous = r.color
        if schedule.end == "closed" and schedule.stuffing != "none":
            peak = max(schedule.counts)
            start = next(
                (r.number for r in schedule.rounds
                 if r.number > schedule.counts.index(peak) + 1 and r.count <= peak * 0.55),
                len(schedule.rounds),
            )
            text = "Jetzt füllen (vorher Augen/Details einsetzen) und beim Weiterhäkeln nachfüllen."
            notes.setdefault(start, []).append(text)
        for number, text in round_notes.get(part.id, []):
            notes.setdefault(number, []).append(text)
        finish_de, finish_en = _finish(schedule, part.attach is not None)
        summary.update(
            {
                "id": part.id,
                "label": part.label,
                "note": part.note,
                "instances": len(instances[part.id]),
                "color": part.color,
                "notes_by_round": {str(k): v for k, v in sorted(notes.items())},
                "rows": _grouped_rows(schedule, notes),
                "finish_de": finish_de,
                "finish_en": finish_en,
                "attach_to": part.attach.to if part.attach else None,
            }
        )
        parts_out.append(summary)

    points, bounds = _layout(spec, instances, p_s)
    points.extend(feature_points)
    total = sum(s["total_stitches"] * s["instances"] for s in parts_out)
    return {
        "figure_version": FIGURE_VERSION,
        "solver_version": PART_SOLVER_VERSION,
        "name": spec.name,
        "verification_state": "NOT_VERIFIED",
        "physical_status": "UNTESTED",
        "gauge": {
            "stitches_per_100mm": spec.gauge.stitches_per_100mm,
            "rows_per_100mm": spec.gauge.rows_per_100mm,
            "stitch_pitch_mm": round(p_s, 3),
            "row_pitch_mm": round(p_c, 3),
            "hook_mm": spec.hook_mm,
            "yarn": spec.yarn,
        },
        "colors": [
            {"id": key, "label": label, "hex": hexcode}
            for key, (label, hexcode) in spec.colors.items()
        ],
        "parts": parts_out,
        "assembly": assembly,
        "features": feature_steps,
        "total_stitches": total,
        "bounds_mm": bounds,
        "preview": {
            "role": "SCHEMATIC_NOT_PHYSICAL",
            "unit": "mm",
            "point_fields": ["x", "y", "z", "color_index", "part_index", "round", "size"],
            "points": points,
        },
    }


def _grouped_rows(schedule: PartSchedule, notes: dict[int, list[str]]) -> list[dict[str, Any]]:
    """Merge runs of identical plain rounds ("R15-R41: 78 fM") for printing."""
    rows: list[dict[str, Any]] = []
    for r in schedule.rounds:
        plain = r.number > 1 and set(r.tokens) == {"sc"}
        last = rows[-1] if rows else None
        if (
            last is not None
            and plain
            and last["plain"]
            and last["count"] == r.count
            and last["color"] == r.color
            and r.number not in notes
        ):
            last["to"] = r.number
            continue
        rows.append(
            {"from": r.number, "to": r.number, "count": r.count, "color": r.color,
             "plain": plain, "notes": notes.get(r.number, []),
             "body_de": round_line(r, "de").split(": ", 1)[1],
             "body_en": round_line(r, "en").split(": ", 1)[1]}
        )
    for row in rows:
        span = row["to"] - row["from"] + 1
        label_de = f"R{row['from']}" if span == 1 else f"R{row['from']}-R{row['to']}"
        label_en = f"Rnd {row['from']}" if span == 1 else f"Rnds {row['from']}-{row['to']}"
        extra_de = f" ({span} Runden)" if span > 1 else ""
        extra_en = f" ({span} rounds)" if span > 1 else ""
        row["text_de"] = f"{label_de}{extra_de}: {row.pop('body_de')}"
        row["text_en"] = f"{label_en}{extra_en}: {row.pop('body_en')}"
    return rows


def _assembly_step(
    part: PartSpec,
    schedule: PartSchedule,
    host: Instance,
    theta: float,
    host_radius: float,
    label: str,
    p_s: float,
) -> dict[str, Any]:
    assert part.attach is not None
    hs = host.schedule
    s = part.attach.at * hs.profile.length_mm
    k = hs.round_at_arc(s)
    j, n = _stitch_at(hs, k, theta)
    at_pole = host_radius < 1.5 * p_s
    where = (
        f"mittig auf das Ende von {host.part.label} (R{k})"
        if at_pole
        else f"mittig auf R{k}, Masche {j} von {n} von {host.part.label}"
    )
    n_end = schedule.rounds[-1].count
    m = len(hs.rounds)
    if part.end == "open":
        diameter = n_end * p_s / pi
        span = max(1, round(diameter / 2 / hs.round_spacing_mm))
        text = (
            f"{label}: offenes Ende (Ø ca. {diameter:.0f} mm) {where} annähen; "
            f"der Rand reicht etwa von R{max(1, k - span)} bis R{min(m, k + span)}."
        )
    elif part.end == "flat":
        width = n_end * p_s / 2
        stitches = max(1, round(width / p_s))
        first = (j - 1 - stitches // 2) % n + 1
        last = (first - 1 + stitches - 1) % n + 1
        text = (
            f"{label}: flaches Ende (ca. {width:.0f} mm breit) entlang R{k} von Masche "
            f"{first} bis {last} (von {n}) an {host.part.label} annähen."
            if not at_pole
            else f"{label}: flaches Ende (ca. {width:.0f} mm breit) {where} annähen."
        )
    else:
        child_width = max(schedule.counts) * p_s / pi
        contact = 0.4 * min(child_width, 2 * host_radius if not at_pole else child_width)
        span = max(1, round(contact / 2 / hs.round_spacing_mm))
        child_rounds = max(1, round(contact / 2 / schedule.round_spacing_mm))
        text = (
            f"{label}: mit den letzten {child_rounds} Runden {where} annähen; "
            f"Kontaktfläche Ø ca. {contact:.0f} mm (R{max(1, k - span)} bis R{min(m, k + span)})."
        )
    return {
        "part": part.id,
        "label": label,
        "host": host.part.id,
        "round": k,
        "stitch": None if at_pole else j,
        "round_stitches": n,
        "text_de": text,
    }


def _features(
    spec: FigureSpec, instances: dict[str, list[Instance]], p_s: float
) -> tuple[list[dict[str, Any]], list[list[float]], dict[str, list[tuple[int, str]]]]:
    steps: list[dict[str, Any]] = []
    points: list[list[float]] = []
    notes: dict[str, list[tuple[int, str]]] = {}
    color_index = {key: i for i, key in enumerate(spec.colors)}
    for feature in spec.features:
        host = instances[feature.on][0]
        hs = host.schedule
        k = hs.round_at_arc(feature.at * hs.profile.length_mm)
        positions = []
        for user_theta in feature.angles:
            theta = _frame_angle(host.frame, user_theta)
            point, normal, _ = _surface(hs, host.frame, feature.at, theta)
            j, n = _stitch_at(hs, k, theta)
            positions.append(j)
            lift = feature.size_mm * 0.25
            points.append(
                [*map(lambda v: round(v, 2), _add(point, _mul(normal, lift))),
                 color_index[feature.color], -1, k, round(feature.size_mm / 2, 2)]
            )
        n = hs.rounds[k - 1].count
        between = f"zwischen R{k} und R{min(k + 1, len(hs.rounds))}"
        stitches = " und ".join(f"Masche {j}" for j in positions)
        name = feature.label or ("Sicherheitsaugen" if feature.type == "eye" else "Nase")
        if feature.type == "eye":
            gap = ""
            if len(positions) == 2:
                d = abs(positions[0] - positions[1])
                gap = f" (Abstand {min(d, n - d)} Maschen)"
            text = (
                f"{name} ({feature.size_mm:g} mm) in {host.part.label} {between} bei "
                f"{stitches} von {n}{gap} einsetzen, bevor das Teil gefüllt und geschlossen wird."
            )
            notes.setdefault(feature.on, []).append(
                (min(k + 1, len(hs.rounds)),
                 f"{name} sind ab hier möglich: {between}, {stitches} (siehe Montage).")
            )
        else:
            text = (
                f"{name} mit {spec.colors[feature.color][0]} {between} über {stitches} "
                f"von {n} sticken (ca. {feature.size_mm:g} mm breit)."
            )
        steps.append({"type": feature.type, "on": feature.on, "round": k, "stitches": positions,
                      "text_de": text})
    return steps, points, notes


def _layout(
    spec: FigureSpec, instances: dict[str, list[Instance]], p_s: float
) -> tuple[list[list[float]], dict[str, list[float]]]:
    """Schematic stitch points: round radii come from the stitch counts, not the target."""
    color_index = {key: i for i, key in enumerate(spec.colors)}
    points: list[list[float]] = []
    low = [float("inf")] * 3
    high = [float("-inf")] * 3
    for part_index, part in enumerate(spec.parts):
        for instance in instances[part.id]:
            schedule = instance.schedule
            length = schedule.profile.length_mm
            for r in schedule.rounds:
                radius = r.count * p_s / (2 * pi)
                if schedule.end == "closed" and r.number == len(schedule.rounds):
                    radius = min(radius, r.radius_mm + p_s / 2)
                squash = 1 - 0.75 * (r.s_mm / length) ** 2
                for j in range(r.count):
                    theta = 180 - (j + 0.5) * 360 / r.count
                    offset = _mul(instance.frame.radial(theta), radius)
                    if instance.flatten_across is not None:
                        across = _dot(offset, instance.flatten_across)
                        offset = _sub(offset, _mul(instance.flatten_across, across * (1 - squash)))
                    xyz = _add(_add(instance.frame.origin, _mul(instance.frame.axis, r.axial_mm)),
                               offset)
                    for i in range(3):
                        low[i], high[i] = min(low[i], xyz[i]), max(high[i], xyz[i])
                    points.append([round(xyz[0], 2), round(xyz[1], 2), round(xyz[2], 2),
                                   color_index[r.color], part_index, r.number, round(p_s / 2, 2)])
    return points, {"min": [round(v, 1) for v in low], "max": [round(v, 1) for v in high]}


def figure_text(result: dict[str, Any], lang: str = "de") -> str:
    """Plain-text pattern of a solved figure (German by default)."""
    lines = [result["name"], "=" * len(result["name"]), ""]
    g = result["gauge"]
    lines.append(
        f"Maschenprobe: {g['stitches_per_100mm']:g} fM x {g['rows_per_100mm']:g} Runden = 10 cm, "
        f"Nadel {g['hook_mm']:g} mm" + (f", Garn: {g['yarn']}" if g["yarn"] else "")
    )
    lines.append("Farben: " + ", ".join(f"{c['label']} ({c['hex']})" for c in result["colors"]))
    lines.append(
        "Status: NOT_VERIFIED / UNTESTED - berechneter Vorschlag, noch nicht nachgehäkelt."
    )
    lines.append("")
    colors = {c["id"]: c["label"] for c in result["colors"]}
    for part in result["parts"]:
        count = f" (x{part['instances']})" if part["instances"] > 1 else ""
        lines.append(f"{part['label']}{count} - in {colors[part['color']]}")
        if part["note"]:
            lines.append(f"  Hinweis: {part['note']}")
        for row in part["rows"]:
            for note in row["notes"]:
                lines.append(f"  * {note}")
            lines.append("  " + (row["text_de"] if lang == "de" else row["text_en"]))
        lines.append("  " + (part["finish_de"] if lang == "de" else part["finish_en"]))
        lines.append("")
    if result["features"] or result["assembly"]:
        lines.append("Montage")
        lines.append("  Positionen: ab Rundenanfang (Markierung = Rückseite), in Häkelrichtung "
                     "(Rechtshänder) gezählt.")
        for step in result["features"]:
            lines.append(f"  - {step['text_de']}")
        for step in result["assembly"]:
            lines.append(f"  - {step['text_de']}")
    return "\n".join(lines) + "\n"


__all__ = [
    "FIGURE_VERSION",
    "FigureError",
    "figure_text",
    "parse_figure",
    "round_line",
    "solve_figure",
]
