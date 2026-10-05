"""Read-only wheel smoke check: run with a clean venv Python using ``-I``.

This checks installation, not full backend or physical acceptance. Run outside
the source checkout; only authoritative schema/profile bytes are read from it.
"""

from __future__ import annotations

import json
import os
import site
import subprocess
import sys
from fractions import Fraction
from importlib import metadata, resources
from pathlib import Path

import attrs
import jsonschema
import referencing
import reportlab
import rfc8785
import rpds

import crochet_ai
from crochet_ai.adjacent_triangle_residual import adjacent_triangle_residual_squared
from crochet_ai.analytic_target import VERSION as ANALYTIC_TARGET_VERSION
from crochet_ai.calibration_campaign import PROTOCOL_ID, calibration_protocol
from crochet_ai.calibration_pdf import render_calibration_packet
from crochet_ai.certified_orientation import orientation2d, orientation3d
from crochet_ai.forward_closed_cells import PROFILE as CLOSED_CELLS_PROFILE
from crochet_ai.forward_pipeline import PROFILE as FORWARD_PIPELINE_PROFILE
from crochet_ai.schema import SCHEMA_FILENAMES, schema_documents
from crochet_ai.target_mesh_adjacent_residual import (
    diagnose_indexed_triangle_mesh_adjacent_residual,
)
from crochet_ai.target_mesh_decode import MESH_MEDIA_TYPE
from crochet_ai.v0_adjacent_profile import (
    PROFILE_ID as ADJACENT_PROFILE_ID,
)
from crochet_ai.v0_adjacent_profile import (
    parse_adjacent_exclusion_zone,
    resolve_v0_adjacent_numeric_profile,
)
from crochet_ai.v0_numeric_profile import PROFILE_ID, resolve_v0_numeric_profile


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise RuntimeError(reason)


def main() -> int:
    prefix = Path(sys.prefix).resolve()
    _require(sys.prefix != sys.base_prefix, "smoke.clean_venv_required")
    _require(sys.flags.isolated == 1, "smoke.isolated_interpreter_required")
    _require(site.ENABLE_USER_SITE is False, "smoke.user_site_enabled")
    config = {
        key.strip(): value.strip()
        for line in (prefix / "pyvenv.cfg").read_text().splitlines() if "=" in line
        for key, value in [line.split("=", 1)]
    }
    _require(
        config.get("include-system-site-packages") == "false",
        "smoke.system_site_packages_enabled",
    )
    for module in (crochet_ai, attrs, jsonschema, referencing, reportlab, rfc8785, rpds):
        _require(module.__file__ is not None, "smoke.module_location_missing")
        location = Path(str(module.__file__)).resolve()
        _require(location.is_relative_to(prefix), f"smoke.external_import:{module.__name__}")

    repository = Path(__file__).resolve().parents[1]
    _require(not Path.cwd().resolve().is_relative_to(repository), "smoke.external_cwd_required")
    package = resources.files("crochet_ai")
    for filename in SCHEMA_FILENAMES.values():
        _require(
            package.joinpath("schemas", filename).read_bytes()
            == (repository / "schemas" / filename).read_bytes(),
            f"smoke.schema_bytes_mismatch:{filename}",
        )
    for profile_filename in ("v0-mesh-numeric-profile-1.json", "v0-mesh-numeric-profile-2.json"):
        _require(
            package.joinpath("profiles", profile_filename).read_bytes()
            == (repository / "profiles" / profile_filename).read_bytes(),
            "smoke.profile_bytes_mismatch",
        )
    for asset in (
        "index.html", "styles.css", "app.mjs", "viewer.mjs", "state.mjs",
        "privacy.html", "terms.html",
    ):
        _require(
            package.joinpath("prototype_static", asset).read_bytes()
            == (repository / "src/crochet_ai/prototype_static" / asset).read_bytes(),
            f"smoke.prototype_asset_bytes_mismatch:{asset}",
        )
    _require(set(schema_documents(include_additive_versions=True)) == set(SCHEMA_FILENAMES),
             "smoke.schema_registry_mismatch")
    resolve_v0_adjacent_numeric_profile(ADJACENT_PROFILE_ID)
    _require(parse_adjacent_exclusion_zone({
        "policy_id": "BARYCENTRIC_PAIR_LOCAL_V1",
        "lambda": {"numerator": "1", "denominator": "2"},
    }) == Fraction(1, 2), "smoke.adjacent_zone")
    profile = resolve_v0_numeric_profile(PROFILE_ID)
    _require(
        orientation2d((0., 0.), (1., 0.), (0., 1.), max_exact_fallbacks=1).sign == 1,
        "smoke.orientation2d",
    )
    _require(
        orientation3d(
            (0., 0., 0.), (1., 0., 0.), (0., 1., 0.), (0., 0., 1.),
            max_exact_fallbacks=1,
        ).sign == 1,
        "smoke.orientation3d",
    )
    residual = adjacent_triangle_residual_squared(
        ((0., 0., 0.), (2., 0., 0.), (0., 2., 0.)),
        ((0., 0., 0.), (2., 0., 0.), (0., 0., 2.)),
        shared_identity_indices=((0, 0), (1, 1)),
        lambda_value=Fraction(1, 2), max_piece_pairs=2,
    )
    _require(residual.distance_squared == 1, "smoke.adjacent_residual")
    raw_mesh = json.dumps({
        "representation_version": "INDEXED_TRIANGLE_MESH_V1",
        "coordinate_system": {
            "length_unit": "MILLIMETER", "handedness": "RIGHT_HANDED",
            "coordinate_frame_id": "frame_smoke_mesh",
        },
        "vertices": [{"position_mm": position} for position in (
            [0., 0., 0.], [2., 0., 0.], [0., 2., 0.], [0., 0., 2.],
        )],
        "faces": [{"vertex_indices": indices} for indices in ([0, 1, 2], [1, 0, 3])],
    }).encode()
    mesh_report = diagnose_indexed_triangle_mesh_adjacent_residual(
        raw_mesh, media_type=MESH_MEDIA_TYPE,
        expected_coordinate_frame_id="frame_smoke_mesh", lambda_value=Fraction(1, 2),
        max_bytes=10_000, max_vertices=4, max_faces=2, max_face_pairs=1,
        max_distance_piece_pairs=2, max_lambda_bits=2,
    )
    _require(
        (mesh_report.minimum_squared_distance_numerator_mm2,
         mesh_report.minimum_squared_distance_denominator_mm2) == ("1", "1"),
        "smoke.mesh_adjacent_residual",
    )
    console = prefix / "Scripts" / "crochet-ai.exe" if sys.platform == "win32" else (
        prefix / "bin" / "crochet-ai"
    )
    completed = subprocess.run(
        [str(console), "--json", "capabilities"], check=True,
        capture_output=True, text=True, timeout=20,
        env={
            **{name: value for name, value in os.environ.items() if name not in {
                "PYTHONPATH", "PYTHONHOME", "PYTHONUSERBASE",
            }},
            "PYTHONNOUSERSITE": "1",
        },
    )
    capabilities = json.loads(completed.stdout)
    prototype_console = console.with_name("crochet-ai-prototype.exe" if sys.platform == "win32"
                                         else "crochet-ai-prototype")
    prototype_help = subprocess.run(
        [str(prototype_console), "--help"], check=True,
        capture_output=True, text=True, timeout=20,
    )
    _require("--data-dir" in prototype_help.stdout, "smoke.prototype_console_missing")
    _require(capabilities["ok"] is True, "smoke.capabilities_failed")
    _require(
        "inspect_mesh_openings" in capabilities["data"]["operations"],
        "smoke.inspection_operation_missing",
    )
    _require(
        "inspect_v0_mesh_v2" in capabilities["data"]["operations"],
        "smoke.v0_mesh_operation_missing",
    )
    _require(
        "run_forward_prototype" in capabilities["data"]["operations"],
        "smoke.forward_pipeline_operation_missing",
    )
    _require(
        FORWARD_PIPELINE_PROFILE == "FORWARD_STRETCH_SHEAR_BENDING_PIPELINE_V1",
        "smoke.forward_pipeline_profile_mismatch",
    )
    _require(
        capabilities["data"]["physical_verification_available"] is False,
        "smoke.physical_claim",
    )
    _require(
        {"verify_candidate", "calibration_protocol", "inspect_calibration_campaign",
         "derive_calibration_material", "inspect_analytic_target",
         "inspect_closed_surface_cells", "inspect_closed_surface_topology",
         "inspect_closed_cell_conformance",
         "inspect_analytic_candidate_claims"}.issubset(capabilities["data"]["operations"]),
        "smoke.backend_checkpoint_operations_missing",
    )
    _require(
        capabilities["data"]["capability_matrix"]["backend_release_ready"] is False
        and all(not profile["calibrated"] for profile in
                capabilities["data"]["verification_profiles"]),
        "smoke.backend_release_claim",
    )
    _require(calibration_protocol()["protocol_id"] == PROTOCOL_ID,
             "smoke.calibration_protocol_mismatch")
    _require(ANALYTIC_TARGET_VERSION == "ANALYTIC_TARGET_V1"
             and CLOSED_CELLS_PROFILE == "FORWARD_CLOSED_SURFACE_CELLS_V1",
             "smoke.target_cell_profiles_missing")
    packet = render_calibration_packet()
    _require(packet.startswith(b"%PDF-") and packet == render_calibration_packet(),
             "smoke.calibration_packet")
    print(json.dumps({
        "status": "INSTALLATION_SMOKE_PASS", "physical_status": "UNTESTED",
        "package_version": metadata.version("crochet-ai-compiler"),
        "python_version": sys.version.split()[0],
        "schema_count": len(SCHEMA_FILENAMES), "profile_sha256": profile.record_sha256,
        "dependencies": {name: metadata.version(name) for name in (
            "jsonschema", "rfc8785", "attrs", "referencing", "rpds-py",
            "jsonschema-specifications", "typing-extensions", "reportlab", "pillow",
            "charset-normalizer",
        )},
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
