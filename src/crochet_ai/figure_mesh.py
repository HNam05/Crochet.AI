"""Uploaded 3D model (STL or OBJ) to a custom part profile, computed locally.

The model is cut into horizontal slices along the chosen up axis. A stuffed
crochet part is round in cross-section and its fabric spans concave dents, so
each slice contributes the perimeter of its convex hull; the profile radius is
the equivalent ``perimeter / 2 pi``. Stitch counts therefore follow the model's
girth at every height, not its exact silhouette.

Models that branch (separate legs, arms, ears) cannot be one rotational part.
Small branching is reported as a warning; branching over more than a quarter of
the height, gaps or empty files fail closed with a German message. The result
is a ``shape: "custom"`` part proposal; ``parse_figure`` and the solver stay
authoritative. NOT_VERIFIED / UNTESTED like every pattern.
"""

from __future__ import annotations

import re
import struct
from math import atan2, hypot, isfinite, pi
from typing import Any

from .figure import FigureError

MAX_BYTES = 12 * 1024 * 1024
MAX_TRIANGLES = 200_000
SLICES = 64
# Loops smaller than this share of the largest loop in a slice are details
# (a nose tip, a seam artefact) and do not count as branches.
MINOR_LOOP = 0.12
# Branching on more than this share of the slices fails closed.
MAX_BRANCHING = 0.25
AXES = {"x": 0, "y": 1, "z": 2}

_OBJ_INDEX = re.compile(r"^-?\d+")


def _fail(code: str, message: str) -> FigureError:
    return FigureError(f"mesh.{code}", message)


def _read_stl(data: bytes) -> list[tuple[float, ...]]:
    if len(data) >= 84:
        (count,) = struct.unpack_from("<I", data, 80)
        if len(data) == 84 + 50 * count:
            if count > MAX_TRIANGLES:
                raise _fail("too_large", f"Höchstens {MAX_TRIANGLES:,} Dreiecke.".replace(",", "."))
            triangles = []
            for offset in range(84, 84 + 50 * count, 50):
                triangles.append(struct.unpack_from("<9f", data, offset + 12))
            return triangles
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as error:
        raise _fail("format", "Die STL-Datei ist weder binär noch als Text lesbar.") from error
    numbers: list[float] = []
    for line in text.splitlines():
        parts = line.split()
        if parts[:1] == ["vertex"] and len(parts) == 4:
            numbers.extend(float(p) for p in parts[1:])
    if len(numbers) % 9 or not numbers:
        raise _fail("format", "In der STL-Datei wurden keine vollständigen Dreiecke gefunden.")
    return [tuple(numbers[i:i + 9]) for i in range(0, len(numbers), 9)]


def _read_obj(data: bytes) -> list[tuple[float, ...]]:
    vertices: list[tuple[float, float, float]] = []
    triangles: list[tuple[float, ...]] = []
    for line in data.decode("utf-8", errors="replace").splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "v" and len(parts) >= 4:
            vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif parts[0] == "f" and len(parts) >= 4:
            corners = []
            for token in parts[1:]:
                match = _OBJ_INDEX.match(token)
                if match is None:
                    raise _fail("format", "Ungültige Fläche in der OBJ-Datei.")
                index = int(match.group())
                index = index - 1 if index > 0 else len(vertices) + index
                if not 0 <= index < len(vertices):
                    raise _fail("format", "Die OBJ-Datei verweist auf einen fehlenden Punkt.")
                corners.append(vertices[index])
            for i in range(1, len(corners) - 1):  # fan triangulation
                triangles.append((*corners[0], *corners[i], *corners[i + 1]))
            if len(triangles) > MAX_TRIANGLES:
                raise _fail("too_large", "Höchstens 200.000 Dreiecke.")
    if not triangles:
        raise _fail("format", "In der OBJ-Datei wurden keine Flächen gefunden.")
    return triangles


def _hull_perimeter(points: list[tuple[float, float]]) -> float:
    """Perimeter of the 2D convex hull (monotone chain)."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return 2 * hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]) if len(pts) == 2 else 0.0

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    upper: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    closed = zip(hull, hull[1:] + hull[:1], strict=True)
    return sum(hypot(b[0] - a[0], b[1] - a[1]) for a, b in closed)


def _weld(
    triangles: list[tuple[float, ...]], axis: int, sign: float
) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    """Shared corners (axial first) so neighbouring STL triangles share their edges."""
    across = [i for i in range(3) if i != axis]
    keys: dict[tuple[float, float, float], int] = {}
    corners: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    for tri in triangles:
        ids: list[int] = []
        for k in range(3):
            raw = tri[3 * k:3 * k + 3]
            corner = (sign * raw[axis], raw[across[0]], raw[across[1]])
            key = (round(corner[0], 6), round(corner[1], 6), round(corner[2], 6))
            if key not in keys:
                keys[key] = len(corners)
                corners.append(corner)
            ids.append(keys[key])
        if len(set(ids)) == 3:
            faces.append((ids[0], ids[1], ids[2]))
    if not faces:
        raise _fail("format", "Das Modell hat keine Fläche.")
    return corners, faces


def _slice_loops(
    corners: list[tuple[float, float, float]],
    faces: list[tuple[int, int, int]],
    level: float,
) -> list[list[tuple[float, float]]]:
    """Cross-section points at ``level``, grouped into connected loops."""
    parent: dict[tuple[int, int], tuple[int, int]] = {}
    cut: dict[tuple[int, int], tuple[float, float]] = {}

    def find(edge: tuple[int, int]) -> tuple[int, int]:
        while parent[edge] != edge:
            parent[edge] = parent[parent[edge]]
            edge = parent[edge]
        return edge

    for face in faces:
        crossing = []
        for a, b in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            za, zb = corners[a][0], corners[b][0]
            if (za > level) != (zb > level):
                edge = (a, b) if a < b else (b, a)
                if edge not in cut:
                    t = (level - za) / (zb - za)
                    pa, pb = corners[a], corners[b]
                    cut[edge] = (pa[1] + t * (pb[1] - pa[1]), pa[2] + t * (pb[2] - pa[2]))
                    parent[edge] = edge
                crossing.append(edge)
        if len(crossing) == 2:
            root_a, root_b = find(crossing[0]), find(crossing[1])
            if root_a != root_b:
                parent[root_a] = root_b
    loops: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for edge, point in cut.items():
        loops.setdefault(find(edge), []).append(point)
    return list(loops.values())


def mesh_profile(
    data: bytes, filename: str, *, up: str = "auto", flip: bool = False
) -> dict[str, Any]:
    """Slice a model into a normalized custom profile; FigureError on unusable input."""
    if not data:
        raise _fail("empty", "Die Datei ist leer.")
    if len(data) > MAX_BYTES:
        raise _fail("too_large", "Die Datei ist größer als 12 MB.")
    name = filename.lower()
    if name.endswith(".stl"):
        triangles, default_up = _read_stl(data), "z"
    elif name.endswith(".obj"):
        triangles, default_up = _read_obj(data), "y"
    else:
        raise _fail("format", "Bitte eine STL- oder OBJ-Datei hochladen.")
    if up == "auto":
        up = default_up
    if up not in AXES:
        raise _fail("axis", "Achse x, y, z oder auto erwartet.")
    if not all(isfinite(v) for tri in triangles for v in tri):
        raise _fail("format", "Die Datei enthält ungültige Koordinaten.")

    corners, faces = _weld(triangles, AXES[up], -1.0 if flip else 1.0)
    low = min(c[0] for c in corners)
    height = max(c[0] for c in corners) - low
    if height <= 0:
        raise _fail("flat", "Das Modell ist entlang der gewählten Achse flach.")
    step = height / SLICES

    buckets: list[list[tuple[int, int, int]]] = [[] for _ in range(SLICES)]
    for face in faces:
        zs = [corners[i][0] for i in face]
        first = max(0, int((min(zs) - low) / step - 0.5))
        last = min(SLICES - 1, int((max(zs) - low) / step - 0.5) + 1)
        for k in range(first, last + 1):
            buckets[k].append(face)

    radii: list[float] = []
    branching: list[int] = []
    for k, bucket in enumerate(buckets):
        loops = _slice_loops(corners, bucket, low + (k + 0.5) * step)
        if not loops:
            raise _fail(
                "gap",
                f"Das Modell hat auf {round(100 * (k + 0.5) / SLICES)} % der Höhe eine Lücke "
                "(mehrere getrennte Stücke). Bitte jedes Stück einzeln hochladen.",
            )
        sizes = sorted((_hull_perimeter(points), index) for index, points in enumerate(loops))
        largest = sizes[-1][0]
        major = [index for size, index in sizes if size >= MINOR_LOOP * largest]
        branching.append(len(major))
        radii.append(_hull_perimeter([p for index in major for p in loops[index]]) / (2 * pi))
    branched = [k for k, n in enumerate(branching) if n > 1]
    share = len(branched) / SLICES
    if share > MAX_BRANCHING:
        raise _fail(
            "branches",
            f"Das Modell verzweigt sich auf {round(100 * share)} % der Höhe (z. B. Beine oder "
            "Arme). Ein Teil muss rundum geschlossen sein: lade Körper, Arme und Beine einzeln "
            "hoch oder wähle eine andere Achse.",
        )
    warnings = []
    if branched:
        warnings.append(
            f"Zwischen {round(100 * branched[0] / SLICES)} % und "
            f"{round(100 * (branched[-1] + 1) / SLICES)} % der Höhe hat das Modell mehrere "
            "Stränge; dort zählt die gemeinsame Hülle."
        )
    # Light smoothing: slicing noise would otherwise lengthen the meridian.
    smooth = [
        (radii[max(0, k - 1)] + 2 * radii[k] + radii[min(SLICES - 1, k + 1)]) / 4
        for k in range(SLICES)
    ]
    widest = max(smooth)
    profile = [[0.0, 0.0]] + [
        [round((k + 0.5) / SLICES, 4), round(r / widest, 4)] for k, r in enumerate(smooth)
    ] + [[1.0, 0.0]]
    profile[1 + smooth.index(widest)][1] = 1.0
    top_open = smooth[-1] / widest > 0.35
    return {
        "profile": profile,
        "aspect": round(2 * widest / height, 4),
        "up": up,
        "flip": flip,
        "triangles": len(faces),
        "top_is_wide": top_open,
        "warnings": warnings,
        "lean_deg": round(_lean(corners, low, height), 1),
    }


def _lean(corners: list[tuple[float, float, float]], low: float, height: float) -> float:
    """Angle between the up axis and the line joining bottom and top centroids."""
    def centroid(lo: float, hi: float) -> tuple[float, float]:
        chosen = [c for c in corners if lo <= c[0] <= hi] or corners
        return (sum(c[1] for c in chosen) / len(chosen), sum(c[2] for c in chosen) / len(chosen))

    bottom = centroid(low, low + 0.2 * height)
    top = centroid(low + 0.8 * height, low + height)
    return abs(atan2(hypot(top[0] - bottom[0], top[1] - bottom[1]), 0.6 * height)) * 180 / pi


def mesh_part(
    data: bytes,
    filename: str,
    *,
    height_mm: float,
    up: str = "auto",
    flip: bool = False,
    end: str = "closed",
    color: str = "main",
    label: str = "Modell",
) -> dict[str, Any]:
    """A ready ``shape: "custom"`` part for a FigureSpec plus slicing notes."""
    if not 10 <= height_mm <= 400:
        raise _fail("height", "Höhe zwischen 1 und 40 cm wählen.")
    if end not in {"closed", "open"}:
        raise _fail("end", "Ende closed oder open erwartet.")
    sliced = mesh_profile(data, filename, up=up, flip=flip)
    width = round(height_mm * sliced["aspect"], 1)
    if not 4 <= width <= 400:
        raise _fail(
            "proportion",
            f"Bei {height_mm / 10:g} cm Höhe wäre das Teil {width / 10:g} cm breit. Bitte eine "
            "andere Achse oder Höhe wählen.",
        )
    profile = sliced["profile"]
    if end == "open":
        profile = profile[:-1]
        profile[-1][0] = 1.0
    notes = list(sliced["warnings"])
    if sliced["lean_deg"] > 20:
        notes.append(
            f"Das Modell steht um etwa {sliced['lean_deg']:.0f}° schräg; gehäkelt wird es gerade."
        )
    part = {"id": "modell", "label": label[:40] or "Modell", "shape": "custom", "profile": profile,
            "width_mm": width, "height_mm": round(height_mm, 1), "end": end, "color": color}
    return {"part": part, "notes_de": notes, "slicing": {k: sliced[k] for k in
            ("up", "flip", "triangles", "aspect", "top_is_wide", "lean_deg")}}
