"""Immutable numerical-profile v2 and exact DesignSpec adjacent-zone parsing."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from math import gcd
from pathlib import Path
from typing import cast

from .canonical import CanonicalizationError, jcs_bytes, parse_json
from .json_types import JSONValue
from .schema import validate_schema
from .v0_numeric_profile import V0NumericThresholds

PROFILE_ID = "v0_num_mesh_binary64_adjacent_barycentric_v2"
PROFILE_VERSION = "2.0.0"
PROFILE_SHA256 = "b3f5a562c89d47a8c6a07020f7b7626ef8fea25ea6951a866ffcbe80151de7ae"
PROFILE_FILENAME = "v0-mesh-numeric-profile-2.json"
PROFILE_DOMAIN = b"V0_NUMERICAL_GEOMETRY_PROFILE_JSON_V1"
ZONE_POLICY_ID = "BARYCENTRIC_PAIR_LOCAL_V1"
MAX_RATIONAL_BITS = 512


class AdjacentProfileError(ValueError):
    """Stable fail-closed error for malformed or unsupported v2 inputs."""

    code = "E_INPUT"

    def __init__(self, reason: str = "unresolved V0 adjacent numerical profile") -> None:
        super().__init__(f"E_INPUT: {reason}")


@dataclass(frozen=True, slots=True)
class V0AdjacentNumericProfile:
    profile_id: str
    profile_version: str
    thresholds: V0NumericThresholds
    record_sha256: str
    policy_id: str
    lambda_source: str
    exclusion: str


def _load_builtin_bytes() -> bytes:
    package_profiles = Path(__file__).resolve().parent / "profiles"
    if (package_profiles / PROFILE_FILENAME).is_file():
        return (package_profiles / PROFILE_FILENAME).read_bytes()
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "profiles" / PROFILE_FILENAME
        if candidate.is_file():
            return candidate.read_bytes()
    raise AdjacentProfileError()


def _thresholds(value: dict[str, JSONValue]) -> V0NumericThresholds:
    record = value.get("thresholds")
    if not isinstance(record, dict):
        raise AdjacentProfileError()
    fields = {
        "triangle_area2_normalized_max",
        "coordinate_distance_normalized_max",
        "near_contact_distance_normalized_max",
        "volume6_normalized_min_exclusive",
        "landmark_numeric_slack_normalized_max",
    }
    if set(record) != fields:
        raise AdjacentProfileError()
    numbers: dict[str, float] = {}
    for name, entry in record.items():
        if not isinstance(entry, dict):
            raise AdjacentProfileError()
        raw = entry.get("value")
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            raise AdjacentProfileError()
        numbers[name] = float(raw)
    return V0NumericThresholds(**numbers)


def resolve_v0_adjacent_numeric_profile(
    profile_id: str,
    profile_bytes: bytes | None = None,
) -> V0AdjacentNumericProfile:
    """Resolve the new immutable profile without accepting it as legacy V1."""
    if profile_id != PROFILE_ID or (
        profile_bytes is not None and not isinstance(profile_bytes, bytes)
    ):
        raise AdjacentProfileError()
    try:
        value = parse_json(profile_bytes if profile_bytes is not None else _load_builtin_bytes())
        if not isinstance(value, dict):
            raise AdjacentProfileError()
        if not validate_schema("numerical_geometry_profile", cast(JSONValue, value)).ok:
            raise AdjacentProfileError()
        if value.get("profile_id") != PROFILE_ID or value.get("profile_version") != PROFILE_VERSION:
            raise AdjacentProfileError()
        preimage = b"Crochet.AI\x00" + PROFILE_DOMAIN + b"\x00" + jcs_bytes(cast(JSONValue, value))
        digest = sha256(preimage).hexdigest()
        if digest != PROFILE_SHA256:
            raise AdjacentProfileError("V0 adjacent numerical profile hash mismatch")
        policy = value["adjacent_exclusion_policy"]
        if not isinstance(policy, dict):
            raise AdjacentProfileError()
        return V0AdjacentNumericProfile(
            PROFILE_ID,
            PROFILE_VERSION,
            _thresholds(value),
            digest,
            str(policy["policy_id"]),
            str(policy["lambda_source"]),
            str(policy["exclusion"]),
        )
    except (CanonicalizationError, OSError, TypeError, ValueError, KeyError) as error:
        if isinstance(error, AdjacentProfileError):
            raise
        raise AdjacentProfileError() from error


def parse_adjacent_exclusion_zone(value: object) -> Fraction:
    """Validate the closed exact rational policy object and return its ratio."""
    if not isinstance(value, dict) or set(value) != {"policy_id", "lambda"}:
        raise AdjacentProfileError("invalid adjacent exclusion zone fields")
    if value["policy_id"] != ZONE_POLICY_ID:
        raise AdjacentProfileError("unsupported adjacent exclusion policy")
    ratio = value["lambda"]
    if not isinstance(ratio, dict) or set(ratio) != {"numerator", "denominator"}:
        raise AdjacentProfileError("invalid adjacent exclusion rational fields")
    parsed: list[int] = []
    for name in ("numerator", "denominator"):
        raw = ratio[name]
        if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal():
            raise AdjacentProfileError(f"{name} must be a positive decimal string")
        if raw.startswith("0") or len(raw) > 155:
            raise AdjacentProfileError(f"{name} is not a canonical positive decimal string")
        integer = int(raw)
        if integer.bit_length() > MAX_RATIONAL_BITS:
            raise AdjacentProfileError(f"{name} exceeds the 512-bit limit")
        parsed.append(integer)
    numerator, denominator = parsed
    if numerator >= denominator:
        raise AdjacentProfileError("lambda must be strictly between zero and one")
    if gcd(numerator, denominator) != 1:
        raise AdjacentProfileError("lambda must be reduced")
    return Fraction(numerator, denominator)
