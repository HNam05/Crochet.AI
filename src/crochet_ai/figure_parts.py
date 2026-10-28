"""Amigurumi part solver: a rotational part profile becomes a complete round schedule.

Every part starts with a magic ring and is worked in continuous single-crochet
rounds. The integer stitch counts come from the exact two-pass count DP in
``analytic_counts``; this module only builds the target profile, the count
windows and the human-readable rounds. Results are construction proposals:
NOT_VERIFIED / UNTESTED until the shape has been crocheted and measured.

Unlike the six-shape prototype, a part may end open (sewn on later) or flat
(flattened and closed across both layers), and shaping is staggered on
alternating shaping rounds so increases do not stack into a hexagon.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from fractions import Fraction
from itertools import pairwise
from math import ceil, cos, floor, hypot, pi, sin
from typing import Any

from .analytic_counts import (
    CountSearchBudget,
    CountSearchInput,
    CountSearchStatus,
    CountWindow,
    search_counts,
)

PART_SOLVER_VERSION = "figure-part-solver-1"

# Allowed end treatments per shape. The first entry is the default.
SHAPE_ENDS: dict[str, tuple[str, ...]] = {
    "sphere": ("closed",),
    "ellipsoid": ("closed",),
    "capsule": ("closed",),
    "pear": ("closed",),
    "egg": ("closed",),
    "dome": ("open", "flat"),
    "tube": ("open", "flat", "closed"),
    "cone": ("closed", "open"),
    "cylinder": ("closed", "open"),
}
END_MODES = ("closed", "open", "flat")
STUFFING = ("full", "light", "none")
_ARC_STEPS = 48
_RING_WINDOW = (6, 8)
_CLOSED_END_MAX = 6
_WINDOW_RADII = (4, 8, 16)


class PartError(ValueError):
    """A part cannot be built; ``code`` is stable, ``message_de`` is user-facing."""

    def __init__(self, code: str, message_de: str) -> None:
        super().__init__(code)
        self.code = code
        self.message_de = message_de


@dataclass(frozen=True, slots=True)
class Gauge:
    stitches_per_100mm: float
    rows_per_100mm: float

    @property
    def stitch_pitch_mm(self) -> float:
        return 100 / self.stitches_per_100mm

    @property
    def course_pitch_mm(self) -> float:
        return 100 / self.rows_per_100mm


@dataclass(frozen=True, slots=True)
class Profile:
    """Ordered meridian points ``(axial_mm, radius_mm)`` from the magic ring onward."""

    points: tuple[tuple[float, float], ...]
    arc: tuple[float, ...] = field(init=False)

    def __post_init__(self) -> None:
        arc = [0.0]
        for (y0, r0), (y1, r1) in zip(self.points, self.points[1:], strict=False):
            arc.append(arc[-1] + hypot(y1 - y0, r1 - r0))
        object.__setattr__(self, "arc", tuple(arc))

    @property
    def length_mm(self) -> float:
        return self.arc[-1]

    @property
    def height_mm(self) -> float:
        return max(y for y, _ in self.points) - min(y for y, _ in self.points)

    def _segment(self, s: float) -> int:
        s = min(max(s, 0.0), self.length_mm)
        index = bisect_right(self.arc, s) - 1
        return min(max(index, 0), len(self.points) - 2)

    def at(self, s: float) -> tuple[float, float]:
        """Axial position and radius at arc length ``s``."""
        i = self._segment(s)
        span = self.arc[i + 1] - self.arc[i]
        t = 0.0 if span == 0 else (min(max(s, 0.0), self.length_mm) - self.arc[i]) / span
        (y0, r0), (y1, r1) = self.points[i], self.points[i + 1]
        return y0 + t * (y1 - y0), r0 + t * (r1 - r0)

    def tangent(self, s: float) -> tuple[float, float]:
        """Unit ``(d_axial, d_radius)`` direction of the meridian at ``s``."""
        i = self._segment(s)
        (y0, r0), (y1, r1) = self.points[i], self.points[i + 1]
        length = hypot(y1 - y0, r1 - r0) or 1.0
        return (y1 - y0) / length, (r1 - r0) / length


def _arc(cy: float, ry: float, rr: float, start: float, stop: float) -> list[tuple[float, float]]:
    """Elliptic arc ``y = cy - ry cos t``, ``r = rr sin t`` for t in [start, stop]."""
    return [
        (cy - ry * cos(start + (stop - start) * i / _ARC_STEPS),
         rr * sin(start + (stop - start) * i / _ARC_STEPS))
        for i in range(_ARC_STEPS + 1)
    ]


def build_profile(shape: str, width_mm: float, height_mm: float, end: str) -> Profile:
    """Target meridian for a part. ``width`` is the widest diameter."""
    if shape not in SHAPE_ENDS:
        raise PartError("part.shape", f"Unbekannte Form „{shape}“.")
    if end not in SHAPE_ENDS[shape]:
        allowed = ", ".join(SHAPE_ENDS[shape])
        raise PartError("part.end", f"Form „{shape}“ erlaubt als Ende nur: {allowed}.")
    r, h = width_mm / 2, height_mm
    points: list[tuple[float, float]]
    if shape == "sphere":
        points = _arc(r, r, r, 0, pi)
    elif shape == "ellipsoid":
        points = _arc(h / 2, h / 2, r, 0, pi)
    elif shape == "capsule" or (shape == "tube" and end == "closed"):
        # Rounded caps joined by a straight side (absent when h == 2 * cap).
        cap = min(r, h / 2)
        points = _arc(cap, cap, r, 0, pi / 2) + _arc(h - cap, cap, r, pi / 2, pi)[1:]
    elif shape == "tube":
        # Rounded start, straight side up to the open or flattened end.
        cap = min(r, h)
        points = _arc(cap, cap, r, 0, pi / 2) + ([(h, r)] if h > cap else [])
    elif shape == "egg":
        # Lower 45 % of the height is a wider half-ellipsoid, the rest a narrower one.
        low = 0.45 * h
        points = _arc(low, low, r, 0, pi / 2) + _arc(low, h - low, r, pi / 2, pi)[1:]
    elif shape == "pear":
        count = 96
        raw = [sin(pi * i / count) * (0.8 + 0.35 * (1 - i / count)) for i in range(count + 1)]
        top = max(raw)
        points = [(h * i / count, r * value / top) for i, value in enumerate(raw)]
        points[0], points[-1] = (0.0, 0.0), (h, 0.0)
    elif shape == "dome":
        points = _arc(h, h, r, 0, pi / 2)
    elif shape == "cone":
        # The midpoint keeps the open profile at the 3-sample minimum of the target schema.
        points = [(0.0, 0.0), (h / 2, r / 2), (h, r)] + ([(h, 0.0)] if end == "closed" else [])
    else:  # cylinder
        points = [(0.0, 0.0), (0.0, r), (h, r)] + ([(h, 0.0)] if end == "closed" else [])
    points[0] = (points[0][0], 0.0)
    if end == "closed":
        points[-1] = (points[-1][0], 0.0)
    return Profile(tuple(points))


@dataclass(frozen=True, slots=True)
class Round:
    number: int
    count: int
    tokens: tuple[str, ...]  # "sc", "inc", "dec"; round 1 is all "sc" into the ring
    color: str
    s_mm: float
    axial_mm: float
    radius_mm: float

    @property
    def increases(self) -> int:
        return self.tokens.count("inc") if self.number > 1 else 0

    @property
    def decreases(self) -> int:
        return self.tokens.count("dec")


@dataclass(frozen=True, slots=True)
class PartSchedule:
    shape: str
    end: str
    width_mm: float
    height_mm: float
    stuffing: str
    gauge: Gauge
    profile: Profile
    rounds: tuple[Round, ...]
    max_residual_mm: float
    reference_bottleneck_mm: float | None
    round_spacing_mm: float

    @property
    def counts(self) -> tuple[int, ...]:
        return tuple(r.count for r in self.rounds)

    @property
    def total_stitches(self) -> int:
        return sum(self.counts)

    def round_at_arc(self, s_mm: float) -> int:
        """1-based round whose height band (below its upper edge) contains ``s_mm``."""
        return min(max(ceil(s_mm / self.round_spacing_mm - 1e-9), 1), len(self.rounds))


def _windows(targets: list[float], radius: int, end: str) -> tuple[CountWindow, ...]:
    windows = []
    last = len(targets) - 1
    for i, q in enumerate(targets):
        low, high = max(3, floor(q) - radius), max(3, ceil(q) + radius)
        if i == 0:
            # Conventional 6..8 ring; only narrow tips (cones, horns) start with 4.
            low, high = (_RING_WINDOW[0] if q >= 4 else 4), _RING_WINDOW[1]
        elif i == last and end == "closed":
            low, high = min(low, _CLOSED_END_MAX), min(high, _CLOSED_END_MAX)
        windows.append(CountWindow(low, high))
    return tuple(windows)


def _transition_ok(before: int, after: int) -> bool:
    # Each base takes at most one increase; a decrease consumes two bases.
    return after <= 2 * before and 2 * after >= before


def _edge_cost(before: int, after: int, previous_delta: int | None, end_flat: bool) -> float:
    delta = after - before
    cost = 0.0
    if delta:
        operations = before - max(-delta, 0)
        if operations % abs(delta):
            cost += _IRREGULAR_PENALTY
        cost += _SHAPING_PENALTY * abs(delta)
    if previous_delta is not None and delta and previous_delta and delta != previous_delta:
        cost += _RHYTHM_PENALTY
    return cost


# Readability weights, in units of (stitch residual)^2. ENGINEERING DECISION: a
# round whose shaping divides evenly prints as "(2 fM, zun) x 6"; designers
# trade up to ~0.8 stitch of circumference error for that. Uncalibrated.
_IRREGULAR_PENALTY = 0.6
_RHYTHM_PENALTY = 0.15
_SHAPING_PENALTY = 0.01
_ODD_FLAT_PENALTY = 0.5


def readable_counts(targets: list[float], end: str) -> tuple[int, ...] | None:
    """Exact DP over integer counts: squared residual plus readability penalties.

    State is (count, previous count) so the shaping rhythm can be scored.
    Returns ``None`` when no feasible sequence exists inside the windows.
    """
    for radius in _WINDOW_RADII:
        windows = _windows(targets, radius, end)
        layer: dict[tuple[int, int | None], tuple[float, tuple[int, ...]]] = {
            (n, None): ((n - targets[0]) ** 2, (n,))
            for n in range(windows[0].minimum, windows[0].maximum + 1)
        }
        for i in range(1, len(targets)):
            nxt: dict[tuple[int, int | None], tuple[float, tuple[int, ...]]] = {}
            last = i == len(targets) - 1
            for n in range(windows[i].minimum, windows[i].maximum + 1):
                node = (n - targets[i]) ** 2
                if last and end == "flat" and n % 2:
                    node += _ODD_FLAT_PENALTY
                for (before, prior), (cost, path) in layer.items():
                    if not _transition_ok(before, n):
                        continue
                    previous_delta = None if prior is None else before - prior
                    total = cost + node + _edge_cost(before, n, previous_delta, end == "flat")
                    key = (n, before)
                    if key not in nxt or (total, path) < nxt[key]:
                        nxt[key] = (total, (*path, n))
            layer = nxt
            if not layer:
                break
        if layer:
            return min(layer.values())[1]
    return None


def shaping_tokens(before: int, after: int, staggered: bool) -> tuple[str, ...]:
    """Evenly spaced shaping for one round; optionally shifted by half a gap."""
    delta = after - before
    shaped = abs(delta)
    operations = before - max(-delta, 0)
    if shaped > operations or operations <= 0:
        raise PartError("part.arity", "Diese Maschenzahl-Änderung ist nicht häkelbar.")
    mark = "inc" if delta > 0 else "dec"
    tokens = [
        mark if shaped and (o + 1) * shaped // operations > o * shaped // operations else "sc"
        for o in range(operations)
    ]
    if staggered and shaped:
        offset = (operations // shaped) // 2
        tokens = tokens[offset:] + tokens[:offset]
    return tuple(tokens)


def consumed_and_produced(tokens: tuple[str, ...]) -> tuple[int, int]:
    """Independent structural accounting of one non-initial round."""
    consumed = sum(2 if t == "dec" else 1 for t in tokens)
    produced = sum(2 if t == "inc" else 1 for t in tokens)
    return consumed, produced


def solve_part(
    shape: str,
    width_mm: float,
    height_mm: float,
    end: str,
    gauge: Gauge,
    *,
    color: str = "main",
    stripes: tuple[tuple[float, float, str], ...] = (),
    stuffing: str | None = None,
) -> PartSchedule:
    """Compute a complete round schedule; raises :class:`PartError` on failure."""
    profile = build_profile(shape, width_mm, height_mm, end)
    p_s, p_c = gauge.stitch_pitch_mm, gauge.course_pitch_mm
    # HYPOTHESIS: a round's stitch count matches the circumference at its upper
    # edge (the loops the next round works into). This reproduces the empirical
    # 6/12/18 single-crochet disc when course/stitch pitch is ~0.9. A closed end
    # keeps one round-height for the gathered closure, open ends end on the rim.
    closed = end == "closed"
    m = max(2, round(profile.length_mm / p_c) - (1 if closed else 0))
    if m > 200:
        raise PartError("part.too_large", "Teil ist zu groß für diese Maschenprobe (>200 Runden).")
    spacing = profile.length_mm / (m + 1 if closed else m)
    tops = [(i + 1) * spacing for i in range(m)]
    samples = [profile.at(s) for s in tops]
    targets = [2 * pi * radius / p_s for _, radius in samples]
    if max(targets) > 600:
        raise PartError("part.too_wide", "Teil ist zu breit für diese Maschenprobe (>600 Maschen).")
    counts = readable_counts(targets, end)
    if counts is None:
        raise PartError(
            "part.no_schedule",
            "Für diese Maße und Maschenprobe gibt es keine häkelbare Rundenfolge.",
        )
    # Reference optimum from the project's exact bottleneck DP, for reporting.
    reference = search_counts(
        CountSearchInput(
            tuple(Fraction(t * p_s) for t in targets),
            Fraction(p_s),
            _windows(targets, _WINDOW_RADII[-1], end),
            100_000,
            100_000,
            CountSearchBudget(512, 64, 64, 2_000_000),
        )
    )
    bottleneck = (
        float(reference.objective.max_residual_mm)
        if reference.status == CountSearchStatus.OPTIMAL_COUNT_PROPOSAL and reference.objective
        else None
    )
    rounds: list[Round] = []
    shaping_rounds = 0
    for i, count in enumerate(counts):
        if i == 0:
            tokens: tuple[str, ...] = ("sc",) * count
        else:
            shaped = counts[i - 1] != count
            tokens = shaping_tokens(
                counts[i - 1], count, staggered=shaped and shaping_rounds % 2 == 1
            )
            shaping_rounds += shaped
        s = tops[i]
        fraction = (s - spacing / 2) / profile.length_mm
        round_color = color
        for start, stop, stripe_color in stripes:
            if start <= fraction < stop or (stop >= 1 and fraction >= start):
                round_color = stripe_color
        axial, radius = samples[i]
        rounds.append(Round(i + 1, count, tokens, round_color, s, axial, radius))
    schedule = PartSchedule(
        shape,
        end,
        width_mm,
        height_mm,
        stuffing or ("light" if end == "flat" else "full"),
        gauge,
        profile,
        tuple(rounds),
        max(abs(n - t) for n, t in zip(counts, targets, strict=True)) * p_s,
        bottleneck,
        spacing,
    )
    check_schedule(schedule)
    return schedule


def check_schedule(schedule: PartSchedule) -> None:
    """Replay every round's stitch accounting independently of the generator."""
    rounds = schedule.rounds
    if not rounds or rounds[0].count != len(rounds[0].tokens) or set(rounds[0].tokens) != {"sc"}:
        raise PartError("check.ring", "Interner Prüffehler: Runde 1 ist ungültig.")
    for previous, current in pairwise(rounds):
        consumed, produced = consumed_and_produced(current.tokens)
        if consumed != previous.count or produced != current.count:
            raise PartError(
                "check.round", f"Interner Prüffehler: Runde {current.number} geht nicht auf."
            )
    if schedule.end == "closed" and rounds[-1].count > _CLOSED_END_MAX:
        raise PartError("check.closure", "Interner Prüffehler: Endrunde zu groß zum Schließen.")


# ---------------------------------------------------------------- notation

_WORDS = {
    "de": {"sc": "fM", "inc": "zun", "dec": "abn", "ring": "MR", "round": "R"},
    "en": {"sc": "sc", "inc": "inc", "dec": "dec", "ring": "MR", "round": "Rnd "},
}


def _runs(tokens: list[str], lang: str) -> str:
    words = _WORDS[lang]
    parts: list[str] = []
    i = 0
    while i < len(tokens):
        j = i
        while j < len(tokens) and tokens[j] == tokens[i]:
            j += 1
        n = j - i
        word = words[tokens[i]]
        parts.append(f"{n} {word}" if tokens[i] == "sc" or n > 1 else word)
        i = j
    return ", ".join(parts)


def round_notation(tokens: tuple[str, ...], lang: str = "de") -> str:
    """Shortest ``head, (motif) x n, tail`` form that literally expands to ``tokens``."""
    seq = list(tokens)
    best = _runs(seq, lang)
    if len(set(seq)) == 1:
        return best
    for size in range(2, len(seq) // 2 + 1):
        for start in range(0, size):
            motif = seq[start : start + size]
            reps = 1
            while seq[start + reps * size : start + (reps + 1) * size] == motif:
                reps += 1
            if reps < 2:
                continue
            head, tail = seq[:start], seq[start + reps * size :]
            text = ", ".join(
                item
                for item in (
                    _runs(head, lang), f"({_runs(motif, lang)}) x {reps}", _runs(tail, lang)
                )
                if item
            )
            if len(text) < len(best):
                best = text
    return best


def round_line(r: Round, lang: str = "de") -> str:
    words = _WORDS[lang]
    if r.number == 1:
        body = f"{words['ring']}, {r.count} {words['sc']}"
    else:
        body = round_notation(r.tokens, lang)
    return f"{words['round']}{r.number}: {body} ({r.count})"


def part_summary(schedule: PartSchedule) -> dict[str, Any]:
    """Serializable round table with both notations."""
    p_s = schedule.gauge.stitch_pitch_mm
    return {
        "shape": schedule.shape,
        "end": schedule.end,
        "stuffing": schedule.stuffing,
        "width_mm": schedule.width_mm,
        "height_mm": schedule.height_mm,
        "round_count": len(schedule.rounds),
        "total_stitches": schedule.total_stitches,
        "max_stitches": max(schedule.counts),
        "predicted_width_mm": round(max(schedule.counts) * p_s / pi, 1),
        "max_circumference_residual_mm": round(schedule.max_residual_mm, 2),
        "reference_bottleneck_mm": None
        if schedule.reference_bottleneck_mm is None
        else round(schedule.reference_bottleneck_mm, 2),
        "rounds": [
            {
                "number": r.number,
                "count": r.count,
                "color": r.color,
                "increases": r.increases,
                "decreases": r.decreases,
                "text_de": round_line(r, "de"),
                "text_en": round_line(r, "en"),
            }
            for r in schedule.rounds
        ],
    }
