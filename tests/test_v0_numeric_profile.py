from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from crochet_ai.v0_numeric_profile import (
    PROFILE_FILENAME,
    PROFILE_ID,
    PROFILE_SHA256,
    NumericalGeometryProfileError,
    resolve_v0_numeric_profile,
)

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "profiles" / PROFILE_FILENAME


def test_resolves_documented_profile_and_thresholds() -> None:
    profile = resolve_v0_numeric_profile(PROFILE_ID)

    assert profile.record_sha256 == PROFILE_SHA256
    assert profile.profile_version == "1.0.0"
    assert profile.thresholds.triangle_area2_normalized_max == 2**-40
    assert profile.thresholds.volume6_normalized_min_exclusive == 2**-36


def test_rejects_mutated_profile_bytes() -> None:
    original = PROFILE_PATH.read_bytes()
    mutated = original.replace(b"Exactly representable", b"Slightly representable", 1)

    with pytest.raises(NumericalGeometryProfileError) as error:
        resolve_v0_numeric_profile(PROFILE_ID, mutated)

    assert error.value.code == "E_INPUT"
    assert str(error.value) == "E_INPUT: unresolved V0 numerical geometry profile"


def test_rejects_unknown_profile_id() -> None:
    with pytest.raises(NumericalGeometryProfileError):
        resolve_v0_numeric_profile("v0_num_mesh_binary64_v2")


def test_rejects_mutable_profile_bytes() -> None:
    with pytest.raises(NumericalGeometryProfileError):
        resolve_v0_numeric_profile(PROFILE_ID, bytearray(PROFILE_PATH.read_bytes()))


@pytest.mark.parametrize(
    "profile_bytes",
    [
        b'{"schema_version":"1.0.0","schema_version":"1.0.0"}',
        b'{"threshold":NaN}',
    ],
)
def test_rejects_duplicate_keys_and_nonfinite_values(profile_bytes: bytes) -> None:
    with pytest.raises(NumericalGeometryProfileError):
        resolve_v0_numeric_profile(PROFILE_ID, profile_bytes)


def test_rejects_missing_builtin_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing() -> bytes:
        raise FileNotFoundError(PROFILE_FILENAME)

    monkeypatch.setattr("crochet_ai.v0_numeric_profile._load_builtin_bytes", missing)

    with pytest.raises(NumericalGeometryProfileError) as error:
        resolve_v0_numeric_profile(PROFILE_ID)

    assert error.value.code == "E_INPUT"


def test_build_py_copies_builtin_profile_into_package(tmp_path: Path) -> None:
    build_lib = tmp_path / "build"
    subprocess.run(
        [sys.executable, "setup.py", "build_py", "--build-lib", str(build_lib)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    profile_copy = build_lib / "crochet_ai" / "profiles" / PROFILE_FILENAME
    assert profile_copy.read_bytes() == PROFILE_PATH.read_bytes()

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(build_lib)
    subprocess.run(
        [
            sys.executable,
            "-c",
            "from crochet_ai.v0_numeric_profile import resolve_v0_numeric_profile; "
            f"assert resolve_v0_numeric_profile({PROFILE_ID!r}).record_sha256 "
            f"== {PROFILE_SHA256!r}",
        ],
        cwd=tmp_path,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
