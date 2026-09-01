"""I-JSON/JCS projections and domain-separated content hashes."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from copy import deepcopy
from enum import StrEnum
from hashlib import sha256
from operator import itemgetter
from typing import TYPE_CHECKING, Any, cast

import rfc8785

from .diagnostics import ArtifactValidationError, Diagnostic, FailureCode, ValidationReport
from .json_types import JSONValue

if TYPE_CHECKING:
    from .validation import SemanticValidator

SAFE_INTEGER = 9_007_199_254_740_991


class CanonicalProfile(StrEnum):
    DESIGN_SPEC = "DESIGN_SPEC_CANONICAL_JSON_V1"
    SURFACE_OF_REVOLUTION = "SURFACE_OF_REVOLUTION_PROFILE_CANONICAL_JSON_V1"
    CROCHET_IR = "CROCHET_IR_CANONICAL_JSON_V1"
    MATERIAL_PROFILE = "MATERIAL_PROFILE_CANONICAL_JSON_V1"
    SEMANTIC_EQUIVALENCE = "CROCHET_SEMANTIC_EQUIVALENCE_V1"
    INDEXED_TRIANGLE_MESH = "INDEXED_TRIANGLE_MESH_CANONICAL_JSON_V1"
    NUMERICAL_GEOMETRY_PROFILE = "V0_NUMERICAL_GEOMETRY_PROFILE_JSON_V1"


class CanonicalizationError(ValueError):
    pass


def _reject_constant(token: str) -> None:
    raise CanonicalizationError(f"non-finite JSON number is forbidden: {token}")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CanonicalizationError(f"duplicate object member: {key}")
        result[key] = value
    return result


def validate_ijson(value: object, path: str = "") -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        if abs(value) > SAFE_INTEGER:
            raise CanonicalizationError(f"unsafe integer at {path or '/'}")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalizationError(f"non-finite number at {path or '/'}")
        return
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise CanonicalizationError(f"invalid Unicode surrogate at {path or '/'}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            validate_ijson(child, f"{path}/{index}")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            validate_ijson(key, f"{path}/<key>")
            validate_ijson(child, f"{path}/{key}")
        return
    raise CanonicalizationError(f"unsupported JSON value at {path or '/'}")


def parse_json(text: str | bytes) -> JSONValue:
    try:
        decoded = text.decode("utf-8", "strict") if isinstance(text, bytes) else text
        value = json.loads(
            decoded,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CanonicalizationError(str(error)) from error
    validate_ijson(value)
    return cast(JSONValue, value)


def _sort_items(items: list[Any], key: Callable[[Any], Any]) -> list[Any]:
    return sorted(items, key=key)


def material_profile_projection(value: dict[str, Any]) -> dict[str, Any]:
    projected = deepcopy(value)
    responses = projected["calibration_responses"]
    response_ids: set[str] = set()
    semantic_keys: set[tuple[str, str, str, str]] = set()
    for response in responses:
        response_id = response["response_id"]
        conditions = response["measurement_conditions"]
        semantic_key = (
            conditions["canonical_stitch_type"],
            conditions["course_mode"],
            conditions["tension_profile_id"],
            conditions["fabric_state"],
        )
        if response_id in response_ids or semantic_key in semantic_keys:
            raise CanonicalizationError("duplicate MaterialProfile response identity")
        response_ids.add(response_id)
        semantic_keys.add(semantic_key)
        keyed_observations = [
            (jcs_bytes(observation), observation) for observation in response["observations"]
        ]
        if len({encoded for encoded, _ in keyed_observations}) != len(keyed_observations):
            raise CanonicalizationError("duplicate MaterialProfile observation")
        response["observations"] = [
            observation for _, observation in sorted(keyed_observations, key=lambda item: item[0])
        ]
    projected["calibration_responses"] = _sort_items(
        responses,
        lambda response: (
            response["measurement_conditions"]["canonical_stitch_type"],
            response["measurement_conditions"]["course_mode"],
            response["measurement_conditions"]["tension_profile_id"],
            response["measurement_conditions"]["fabric_state"],
            response["response_id"],
        ),
    )
    source_ids = projected["provenance"]["source_record_ids"]
    if len(set(source_ids)) != len(source_ids):
        raise CanonicalizationError("duplicate MaterialProfile source record")
    projected["provenance"]["source_record_ids"] = sorted(source_ids)
    return projected


STITCH_ENUM = [
    "CHAIN",
    "SLIP_STITCH",
    "SINGLE_CROCHET",
    "HALF_DOUBLE_CROCHET",
    "DOUBLE_CROCHET",
    "TREBLE_CROCHET",
]
OPERATION_ENUM = [
    "MAGIC_RING",
    "JOIN",
    "SPLIT",
    "RESERVE",
    "ATTACH",
    "COLOR_CHANGE",
    "CUT_YARN",
    "CLOSE",
    "DECLARE_OPENING",
]


def _enum_key(order: list[str]) -> Callable[[str], int]:
    positions = {value: index for index, value in enumerate(order)}
    return lambda value: positions[value]


def design_spec_projection(value: dict[str, Any]) -> dict[str, Any]:
    projected = deepcopy(value)
    binding = projected["material_profile"]
    if binding["binding_type"] == "INLINE":
        binding["profile"] = material_profile_projection(binding["profile"])
    projected["dimensions"]["measurements"] = _sort_items(
        projected["dimensions"]["measurements"], lambda item: item["measurement_id"]
    )
    for field, identifier in (
        ("symmetries", "symmetry_id"),
        ("landmarks", "landmark_id"),
        ("colors", "color_id"),
    ):
        projected[field] = _sort_items(projected[field], itemgetter(identifier))
    target = projected["target_geometry"]
    if "parameters" in target:
        target["parameters"] = _sort_items(target["parameters"], lambda item: item["parameter"])
    constraints = projected["construction_constraints"]
    constraints["allowed_join_methods"] = sorted(
        constraints["allowed_join_methods"], key=_enum_key(["CROCHETED", "SEWN"])
    )
    constraints["intentional_openings"] = _sort_items(
        constraints["intentional_openings"], lambda item: item["opening_requirement_id"]
    )
    for opening in constraints["intentional_openings"]:
        opening["boundary_landmark_ids"] = sorted(opening["boundary_landmark_ids"])
    for color in projected["colors"]:
        color["roles"] = sorted(color["roles"])
    difficulty = projected["difficulty_constraints"]
    difficulty["allowed_stitch_types"] = sorted(
        difficulty["allowed_stitch_types"], key=_enum_key(STITCH_ENUM)
    )
    difficulty["allowed_shaping"] = sorted(
        difficulty["allowed_shaping"], key=_enum_key(["INCREASE", "DECREASE"])
    )
    difficulty["allowed_construction_operations"] = sorted(
        difficulty["allowed_construction_operations"], key=_enum_key(OPERATION_ENUM)
    )
    solver = projected["solver_options"]
    solver_order = ["ANALYTIC", "GEODESIC", "FRONTIER", "GARMENT", "FLAT", "LACE"]
    solver["allowed_solver_families"] = sorted(
        solver["allowed_solver_families"], key=_enum_key(solver_order)
    )
    verification = projected["verification_requirements"]
    verification["required_gates"] = sorted(
        verification["required_gates"], key=lambda gate: int(gate[1:])
    )
    metric_order = [
        "SYMMETRIC_CHAMFER",
        "PERCENTILE_HAUSDORFF",
        "SILHOUETTE_IOU",
        "CROSS_SECTION_ERROR",
        "VOLUME_ERROR",
        "LANDMARK_DEVIATION",
        "NORMAL_DEVIATION",
        "CURVATURE_DIAGNOSTIC",
        "TOPOLOGY",
    ]
    verification["required_geometry_metrics"] = sorted(
        verification["required_geometry_metrics"], key=_enum_key(metric_order)
    )
    domain = projected["domain_constraints"]
    for field in ("body_measurement_ids", "ease_allowances"):
        if field in domain:
            key = "measurement_id"
            domain[field] = _sort_items(domain[field], itemgetter(key))
    for field, order in (
        (
            "allowed_constructions",
            ["PANELS", "RAGLAN", "YOKE", "TOP_DOWN", "BOTTOM_UP", "MOTIF_ASSEMBLY"],
        ),
        (
            "required_primitive_families",
            [
                "BASIC_STITCHES",
                "CHAIN_SPACES",
                "PICOTS",
                "POST_STITCHES",
                "CLUSTERS",
                "PUFFS",
                "BOBBLES",
                "FANS_SHELLS",
                "MOTIF_ATTACHMENTS",
            ],
        ),
    ):
        if field in domain:
            domain[field] = sorted(domain[field], key=_enum_key(order))
    provenance = projected["interpretation_provenance"]
    provenance["source_artifacts"] = _sort_items(
        provenance["source_artifacts"], lambda item: item["artifact_id"]
    )
    provenance["assumptions"] = _sort_items(
        provenance["assumptions"], lambda item: item["assumption_id"]
    )
    return projected


IR_TABLE_IDS = {
    "colors": "color_id",
    "yarns": "yarn_id",
    "attachment_locations": "attachment_location_id",
    "stitches": "stitch_id",
    "construction_operations": "operation_id",
    "courses": "course_id",
    "frontiers": "frontier_id",
    "branches": "branch_id",
    "components": "component_id",
    "openings": "opening_id",
    "yarn_paths": "yarn_path_id",
    "derivations": "derivation_id",
}


def _subject_ref_key(reference: dict[str, Any]) -> tuple[str, str]:
    identifier = next(value for key, value in reference.items() if key.endswith("_id"))
    return reference["entity_type"], identifier


def crochet_ir_projection(value: dict[str, Any]) -> dict[str, Any]:
    projected = deepcopy(value)
    for table, identifier in IR_TABLE_IDS.items():
        projected[table] = _sort_items(projected[table], itemgetter(identifier))
    projected["construction_sequence"] = _sort_items(
        projected["construction_sequence"], lambda item: item["sequence_index"]
    )
    projected["frontier_transitions"] = _sort_items(
        projected["frontier_transitions"], lambda item: item["transition_index"]
    )
    projected["required_capabilities"] = sorted(projected["required_capabilities"])
    for branch in projected["branches"]:
        branch["parent_branch_ids"] = sorted(branch["parent_branch_ids"])
        branch["course_ids"] = sorted(branch["course_ids"])
    for component in projected["components"]:
        component["branch_ids"] = sorted(component["branch_ids"])
    for derivation in projected["derivations"]:
        derivation["subject_refs"] = sorted(derivation["subject_refs"], key=_subject_ref_key)
    provenance = projected["provenance"]
    provenance["input_artifacts"] = _sort_items(
        provenance["input_artifacts"], lambda item: item["artifact_id"]
    )
    provenance["solver_parameters"] = _sort_items(
        provenance["solver_parameters"], lambda item: item["name"]
    )
    return projected


def canonical_projection(
    value: dict[str, Any],
    profile: CanonicalProfile,
    *,
    validator: SemanticValidator | None = None,
) -> dict[str, Any]:
    validate_ijson(value)
    if profile == CanonicalProfile.DESIGN_SPEC:
        if {"schema_version", "design_spec_id"} & value.keys():
            _require_semantic_validity(value, "design_spec", validator)
            return design_spec_projection(value)
        return deepcopy(value)
    if profile == CanonicalProfile.MATERIAL_PROFILE:
        if {"schema_version", "profile_id"} & value.keys():
            _require_semantic_validity(value, "material_profile", validator)
            return material_profile_projection(value)
        return deepcopy(value)
    if profile == CanonicalProfile.CROCHET_IR:
        if {"schema_version", "semantics_profile", "crochet_ir_id"} & value.keys():
            _require_semantic_validity(value, "crochet_ir", validator)
            return crochet_ir_projection(value)
        return deepcopy(value)
    if profile in {CanonicalProfile.SURFACE_OF_REVOLUTION, CanonicalProfile.SEMANTIC_EQUIVALENCE}:
        return deepcopy(value)
    if profile in {
        CanonicalProfile.INDEXED_TRIANGLE_MESH,
        CanonicalProfile.NUMERICAL_GEOMETRY_PROFILE,
    }:
        return deepcopy(value)
    raise CanonicalizationError(f"unsupported profile: {profile}")


def _require_semantic_validity(
    value: dict[str, Any], kind: str, validator: SemanticValidator | None
) -> None:
    from .validation import SemanticValidator

    active_validator = validator or SemanticValidator()
    if kind == "design_spec":
        report = active_validator.validate_design_spec(value)
    elif kind == "material_profile":
        report = active_validator.validate_material_profile(value)
    else:
        report = active_validator.validate_crochet_ir(value)
    if not report.ok:
        raise ArtifactValidationError(report)


def jcs_bytes(value: JSONValue) -> bytes:
    validate_ijson(value)
    try:
        return rfc8785.dumps(value)
    except (rfc8785.CanonicalizationError, UnicodeEncodeError) as error:
        raise CanonicalizationError(str(error)) from error


def canonical_bytes(
    value: dict[str, Any],
    profile: CanonicalProfile,
    *,
    validator: SemanticValidator | None = None,
) -> bytes:
    return jcs_bytes(cast(JSONValue, canonical_projection(value, profile, validator=validator)))


def canonical_hash(
    value: dict[str, Any],
    profile: CanonicalProfile,
    *,
    validator: SemanticValidator | None = None,
) -> str:
    payload = (
        b"Crochet.AI\x00"
        + profile.encode("ascii")
        + b"\x00"
        + canonical_bytes(value, profile, validator=validator)
    )
    return sha256(payload).hexdigest()


def validation_error(message_key: str, summary: str) -> ArtifactValidationError:
    return ArtifactValidationError(
        ValidationReport.from_iterable(
            [
                Diagnostic(
                    code=FailureCode.DETERMINISM,
                    gate="V2",
                    message_key=message_key,
                    summary=summary,
                    artifact_hash="0" * 64,
                )
            ]
        )
    )
