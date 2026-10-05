"""Versioned bounded target silhouettes for the local crochet prototype."""

from __future__ import annotations

from fractions import Fraction
from itertools import pairwise
from math import cos, hypot, nextafter, pi, sin
from typing import Any

from .canonical import CanonicalProfile, canonical_hash

SHAPE_CATALOG: tuple[dict[str, object], ...] = (
    {
        "id": "sphere", "label_de": "Kugel",
        "description_de": "Gleichmäßige Kugel mit geschlossener Spitze.",
        "example_diameter_mm": 40, "example_height_mm": 40,
    },
    {
        "id": "ellipsoid", "label_de": "Ellipsoid",
        "description_de": "Abgerundete Form mit getrennt einstellbarer Höhe.",
        "example_diameter_mm": 40, "example_height_mm": 60,
    },
    {
        "id": "cylinder", "label_de": "Zylinder",
        "description_de": "Geschlossener Vollzylinder mit beiden Kreisflächen.",
        "example_diameter_mm": 40, "example_height_mm": 40,
    },
    {
        "id": "cone", "label_de": "Kegel",
        "description_de": "Geschlossener Vollkegel mit Grundfläche und Spitze.",
        "example_diameter_mm": 40, "example_height_mm": 40,
    },
    {
        "id": "capsule", "label_de": "Kapsel",
        "description_de": "Runder Körper mit halbkugelförmigen Enden; Höhe mindestens Durchmesser.",
        "example_diameter_mm": 30, "example_height_mm": 50,
    },
    {
        "id": "pear", "label_de": "Birne",
        "description_de": "Geschlossene, glatt verjüngte Birnenform.",
        "example_diameter_mm": 40, "example_height_mm": 55,
    },
)

SHAPE_IDS = frozenset(item["id"] for item in SHAPE_CATALOG)
_MAX_PROFILE_SAMPLES = 129


def shape_label(shape_id: str) -> str:
    """Return the German display label for a supported shape, failing closed."""
    for shape in SHAPE_CATALOG:
        if shape["id"] == shape_id:
            return str(shape["label_de"])
    raise ValueError("request.shape")


def _silhouette(shape: str, radius: float, height: float) -> list[tuple[float, float]]:
    """Return ordered (radius, axial-height) points for a closed meridian."""
    if shape == "cylinder":
        # The first and last radial segments are the bottom and top disks.
        return [(0.0, 0.0), (radius, 0.0), (radius, height), (0.0, height)]
    if shape == "cone":
        return [(0.0, 0.0), (radius, 0.0), (0.0, height)]
    if shape == "capsule":
        cap_radius = radius
        steps = 32
        lower = [
            (cap_radius * cos(-pi / 2 + (pi / 2) * i / steps),
             cap_radius + cap_radius * sin(-pi / 2 + (pi / 2) * i / steps))
            for i in range(steps + 1)
        ]
        upper_y = height - cap_radius
        upper = [
            (cap_radius * cos((pi / 2) * i / steps),
             upper_y + cap_radius * sin((pi / 2) * i / steps))
            for i in range(steps + 1)
        ]
        lower[0] = (0.0, 0.0)
        upper[-1] = (0.0, height)
        upper_start = 1 if height == 2 * cap_radius else 0
        return [(r, y) for r, y in lower] + [(r, y) for r, y in upper[upper_start:]]
    if shape == "pear":
        count = _MAX_PROFILE_SAMPLES - 1
        raw = [
            sin(pi * i / count) * (0.8 + 0.35 * (1 - i / count))
            for i in range(count + 1)
        ]
        raw[0] = raw[-1] = 0.0
        maximum = max(raw)
        radii = [radius * value / maximum for value in raw]
        return [(r, height * i / count) for i, r in enumerate(radii)]
    raise ValueError("request.shape")


def radial_profile(
    shape: str, diameter: float, height: float
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build a closed, canonical piecewise-linear surface-of-revolution profile.

    Cumulative arc positions use binary64 hypot/add. If that rounded increment is
    one ulp short of |dr|, one nextafter step makes the exact rational slope test
    pass; this bounded construction allowance is <= one ulp per sample and the
    strict schema/decoder predicates remain unchanged.
    """
    if shape not in {"cylinder", "cone", "capsule", "pear"}:
        raise ValueError("request.shape")
    if shape == "capsule" and height < diameter:
        raise ValueError("request.capsule_height")
    radius = diameter / 2
    points = _silhouette(shape, radius, height)
    if len(points) > _MAX_PROFILE_SAMPLES:
        raise ValueError("request.profile_budget")
    samples: list[dict[str, float | int]] = [
        {"sample_index": 0, "s_mm": 0.0, "radius_mm": points[0][0]}
    ]
    s = 0.0
    for index, ((previous_r, previous_y), (current_r, current_y)) in enumerate(
        pairwise(points), 1
    ):
        dr = abs(current_r - previous_r)
        dy = current_y - previous_y
        step = hypot(dr, dy)
        candidate = s + step
        exact_dr = abs(Fraction(current_r) - Fraction(previous_r))
        if Fraction(candidate) - Fraction(s) < exact_dr:
            candidate = nextafter(candidate, float("inf"))
        if candidate <= s or Fraction(candidate) - Fraction(s) < exact_dr:
            raise ValueError("request.profile_arc_rounding")
        s = candidate
        samples.append({"sample_index": index, "s_mm": s, "radius_mm": current_r})
    payload: dict[str, Any] = {
        "canonicalization_profile": CanonicalProfile.SURFACE_OF_REVOLUTION.value,
        "samples": samples,
        "start_boundary": {"boundary_type": "CLOSED_POLE"},
        "end_boundary": {"boundary_type": "CLOSED_POLE"},
    }
    profile = {**payload, "sha256": canonical_hash(payload, CanonicalProfile.SURFACE_OF_REVOLUTION)}
    provenance = {
        "profile_design_id": f"prototype_{shape}_silhouette_v1",
        "profile_resolution_sample_count": len(samples),
        "profile_resolution_error_meaning": (
            "Piecewise-linear samples define target identity exactly; "
            "sample count records resolution, "
            "not a certified Hausdorff error bound."
        ),
        "profile_axial_extent_mm": height,
        "profile_max_radius_mm": radius,
        "profile_arc_rounding_allowance": (
            "At most one binary64 ulp per cumulative sample when needed "
            "for |dr| <= ds."
        ),
    }
    return profile, provenance
