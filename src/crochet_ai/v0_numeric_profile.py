"""Resolution of the immutable V0 mesh numerical profile."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import cast

from .canonical import CanonicalizationError, jcs_bytes, parse_json
from .json_types import JSONValue
from .schema import validate_schema

PROFILE_ID = "v0_num_mesh_binary64_v1"
PROFILE_VERSION = "1.0.0"
PROFILE_SHA256 = "6d93723875f28f31dd0c36a4b47d26bf5b22c43e5d863cc51980d6edd2af24fc"
PROFILE_FILENAME = "v0-mesh-numeric-profile-1.json"
PROFILE_DOMAIN = b"V0_NUMERICAL_GEOMETRY_PROFILE_JSON_V1"


class NumericalGeometryProfileError(ValueError):
    """Stable fail-closed error for missing or unsupported V0 profiles."""

    code = "E_INPUT"

    def __init__(self) -> None:
        super().__init__("E_INPUT: unresolved V0 numerical geometry profile")


@dataclass(frozen=True, slots=True)
class V0NumericThresholds:
    triangle_area2_normalized_max: float
    coordinate_distance_normalized_max: float
    near_contact_distance_normalized_max: float
    volume6_normalized_min_exclusive: float
    landmark_numeric_slack_normalized_max: float


@dataclass(frozen=True, slots=True)
class V0NumericProfile:
    profile_id: str
    profile_version: str
    thresholds: V0NumericThresholds
    record_sha256: str


def _load_builtin_bytes() -> bytes:
    package_profiles = Path(__file__).resolve().parent / "profiles"
    if (package_profiles / PROFILE_FILENAME).is_file():
        return (package_profiles / PROFILE_FILENAME).read_bytes()
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "profiles" / PROFILE_FILENAME
        if candidate.is_file():
            return candidate.read_bytes()
    raise NumericalGeometryProfileError


def resolve_v0_numeric_profile(
    profile_id: str,
    profile_bytes: bytes | None = None,
) -> V0NumericProfile:
    """Resolve the single documented profile from its immutable JSON bytes."""
    if profile_id != PROFILE_ID or (
        profile_bytes is not None and not isinstance(profile_bytes, bytes)
    ):
        raise NumericalGeometryProfileError
    try:
        value = parse_json(profile_bytes if profile_bytes is not None else _load_builtin_bytes())
        if not isinstance(value, dict):
            raise NumericalGeometryProfileError
        report = validate_schema("numerical_geometry_profile", cast(JSONValue, value))
        if not report.ok:
            raise NumericalGeometryProfileError
        if value.get("profile_id") != PROFILE_ID or value.get("profile_version") != PROFILE_VERSION:
            raise NumericalGeometryProfileError
        preimage = (
            b"Crochet.AI\x00"
            + PROFILE_DOMAIN
            + b"\x00"
            + jcs_bytes(cast(JSONValue, value))
        )
        record_hash = sha256(preimage).hexdigest()
        if record_hash != PROFILE_SHA256:
            raise NumericalGeometryProfileError
        thresholds = value["thresholds"]
        if not isinstance(thresholds, dict):
            raise NumericalGeometryProfileError
        threshold_values: dict[str, float] = {}
        for name, entry in thresholds.items():
            if not isinstance(entry, dict):
                raise NumericalGeometryProfileError
            raw_value = entry.get("value")
            if not isinstance(raw_value, (int, float)) or isinstance(raw_value, bool):
                raise NumericalGeometryProfileError
            threshold_values[name] = float(raw_value)
        expected_names = {
            "triangle_area2_normalized_max",
            "coordinate_distance_normalized_max",
            "near_contact_distance_normalized_max",
            "volume6_normalized_min_exclusive",
            "landmark_numeric_slack_normalized_max",
        }
        if set(threshold_values) != expected_names:
            raise NumericalGeometryProfileError
        typed_thresholds = V0NumericThresholds(
            **threshold_values
        )
        return V0NumericProfile(PROFILE_ID, PROFILE_VERSION, typed_thresholds, record_hash)
    except (CanonicalizationError, OSError, TypeError, ValueError, KeyError) as error:
        if isinstance(error, NumericalGeometryProfileError):
            raise
        raise NumericalGeometryProfileError from error
