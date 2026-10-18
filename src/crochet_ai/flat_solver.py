"""Bounded rectangular, single-yarn SC rows proposals for FLAT designs.

This producer emits complete CrochetIR candidates. Its pitch-times-count model
is a discretization hypothesis only; independent forward and physical checks
remain separate.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from fractions import Fraction
from hashlib import sha256
from typing import Any, cast

import rfc8785

from .analytic_compile import CompileProvenance
from .canonical import CanonicalProfile, canonical_hash, parse_json
from .diagnostics import ArtifactValidationError
from .solver_types import GenerationError, GenerationStatus
from .validation import SemanticValidator

_TARGET_PROFILE = "FLAT_RECTANGLE_TARGET_V1"
_RUN_PROFILE = "FLAT_SC_ROWS_RUN_CONFIG_V1"
_PARAMETER_PROFILE = "FLAT_SC_ROWS_PARAMETERS_V1"
_TARGET_MAX_BYTES = 65_536
_MAX_COUNT = 512
_MAX_EVENTS = 8_192
_MAX_LOCATIONS = 16_384
_MAX_MEMBERSHIPS = 262_144
_CAPABILITIES = ["CORE_STITCHES_V1", "FRONTIER_BRANCHING_V1"]


@dataclass(frozen=True, slots=True)
class FlatRowsRunConfig:
    """Explicit finite search domain and deterministic resource limits."""

    parameter_profile_id: str
    tension_profile_id: str
    fabric_state: str
    random_seed: int
    max_columns: int
    max_rows: int
    max_candidate_evaluations: int
    max_events: int
    max_attachment_locations: int
    max_memberships: int

    def validate(self) -> None:
        for name in ("parameter_profile_id", "tension_profile_id"):
            value = getattr(self, name)
            if type(value) is not str or not value:
                raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, f"config.{name}")
        if type(self.fabric_state) is not str or self.fabric_state not in {
            "RELAXED_UNSTUFFED",
            "BLOCKED_UNSTUFFED",
            "STUFFED",
        }:
            raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "config.fabric_state")
        bounds = {
            "random_seed": (0, 4_294_967_295),
            "max_columns": (1, _MAX_COUNT),
            "max_rows": (1, _MAX_COUNT),
            "max_candidate_evaluations": (1, _MAX_COUNT * _MAX_COUNT),
            "max_events": (1, _MAX_EVENTS),
            "max_attachment_locations": (1, _MAX_LOCATIONS),
            "max_memberships": (1, _MAX_MEMBERSHIPS),
        }
        for name, (minimum, maximum) in bounds.items():
            value = getattr(self, name)
            if type(value) is not int or not minimum <= value <= maximum:
                raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, f"config.{name}")


def _fraction(value: object, label: str) -> Fraction:
    if type(value) is int:
        return Fraction(value)
    if type(value) is float and math.isfinite(value):
        numerator, denominator = value.as_integer_ratio()
        return Fraction(numerator, denominator)
    raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, label)


def _target_record(raw: bytes, design: dict[str, Any]) -> tuple[dict[str, str], str]:
    if type(raw) is not bytes or len(raw) > _TARGET_MAX_BYTES:
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "target.bytes_or_size")
    try:
        record = parse_json(raw)
    except (ValueError, UnicodeError) as exc:
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "target.json") from exc
    keys = {
        "profile",
        "version",
        "coordinate_frame_id",
        "width_measurement_id",
        "height_measurement_id",
    }
    if type(record) is not dict or set(record) != keys:
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "target.closed_record")
    if (
        record["profile"] != _TARGET_PROFILE
        or record["version"] != "1"
        or any(
            type(record[key]) is not str or not record[key] for key in keys - {"profile", "version"}
        )
    ):
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "target.record_fields")
    geometry = design.get("target_geometry")
    if type(geometry) is not dict or geometry.get("geometry_type") != "PLANAR_REGION":
        raise GenerationError(GenerationStatus.NOT_APPLICABLE, "target.not_planar_region")
    artifact = geometry.get("artifact")
    frame = geometry.get("coordinate_frame")
    if (
        type(artifact) is not dict
        or type(frame) is not dict
        or record["coordinate_frame_id"] != frame.get("coordinate_frame_id")
        or sha256(raw).hexdigest() != artifact.get("sha256")
    ):
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "target.design_binding")
    return cast(dict[str, str], record), sha256(raw).hexdigest()


def _material_response(
    design: dict[str, Any], material: dict[str, Any], config: FlatRowsRunConfig
) -> dict[str, Any]:
    binding = design["material_profile"]
    material_digest = canonical_hash(material, CanonicalProfile.MATERIAL_PROFILE)
    if binding["binding_type"] == "INLINE":
        expected = canonical_hash(binding["profile"], CanonicalProfile.MATERIAL_PROFILE)
        if material_digest != expected:
            raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "material.inline_binding")
    elif (
        binding["profile_id"] != material.get("profile_id")
        or binding["revision"] != material.get("revision")
        or binding["sha256"] != material_digest
    ):
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "material.reference_binding")
    conditions = {
        "canonical_stitch_type": "SINGLE_CROCHET",
        "course_mode": "LINEAR",
        "tension_profile_id": config.tension_profile_id,
        "fabric_state": config.fabric_state,
    }
    matches = [
        response
        for response in material["calibration_responses"]
        if response["measurement_conditions"] == conditions
    ]
    if len(matches) != 1:
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "material.linear_sc_response")
    return cast(dict[str, Any], matches[0])


def _resource_counts(columns: int, rows: int) -> tuple[int, int, int]:
    stitches = columns + rows * columns
    events = stitches + 2  # ATTACH and terminal CLOSE.
    locations = 1 + stitches
    snapshot_memberships = (
        1 + sum(1 + index for index in range(1, columns + 1)) + rows * columns * (columns + 1)
    )
    courses = rows + 1
    # Count every emitted JSON array entry that carries an entity ID. This is
    # the guarded repeated-reference budget, independent of table allocation.
    memberships = (
        snapshot_memberships
        + columns + 2 * rows * columns  # stitch base/top attachment locations
        + stitches  # course member event IDs
        + 2 * courses  # course input/output frontier IDs
        + courses  # course order
        + courses + 2  # branch courses and entry/terminal frontiers
        + 3  # component branch and initial/terminal frontiers
        + 2 * events - 1  # transition inputs/outputs; ATTACH has no input
        + events  # event-to-transition references
        + 2 * locations  # all created and retired location IDs
        + events - 1  # yarn segment event IDs after ATTACH
        + 1  # yarn path segment ID
        + 1  # provenance input artifact ID
        + 3  # ATTACH/CLOSE frontier IDs
        + 1  # ATTACH location ID
        + stitches + 2 + courses  # stitch, operation, and course derivation subjects
    )
    return events, locations, memberships


class _FlatEmitter:
    def __init__(self, color: dict[str, str], parameter_hash: str) -> None:
        self.color = color
        self.parameter_hash = parameter_hash
        self.attachments: list[dict[str, Any]] = []
        self.stitches: list[dict[str, Any]] = []
        self.operations: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.frontiers: list[dict[str, Any]] = []
        self.transitions: list[dict[str, Any]] = []
        self.derivations: list[dict[str, Any]] = []
        self.courses: list[dict[str, Any]] = []
        self.live: list[str] = []
        self.frontier = ""

    def derivation(self, subject: dict[str, str]) -> str:
        identifier = f"deriv_{len(self.derivations):06d}"
        self.derivations.append(
            {
                "derivation_id": identifier,
                "method": "FLAT_COMBINATORIC",
                "rule_id": "flat.sc-rows.rectangle",
                "rule_version": "1",
                "parameter_sha256": self.parameter_hash,
                "subject_refs": [subject],
            }
        )
        return identifier

    def _location(self, subject: dict[str, str], kind: str, ordinal: int = 0) -> str:
        identifier = f"loc_{len(self.attachments):06d}"
        self.attachments.append(
            {
                "attachment_location_id": identifier,
                "location_type": kind,
                "producer_ref": subject,
                "ordinal_within_producer": ordinal,
            }
        )
        return identifier

    def _advance(
        self,
        subject: dict[str, str],
        transition_type: str,
        input_ids: list[str],
        retired: list[str],
        created: list[str],
        after: list[str],
        *,
        closed: bool = False,
    ) -> str:
        index = len(self.events)
        transition_id = f"ftrans_{index:06d}"
        frontier_id = f"frontier_{index:06d}"
        event_id = f"ev_{index:06d}"
        self.transitions.append(
            {
                "frontier_transition_id": transition_id,
                "transition_index": index,
                "after_event_index": index,
                "caused_by_subject_ref": subject,
                "transition_type": transition_type,
                "input_frontier_ids": input_ids,
                "output_frontier_ids": [frontier_id],
                "retired_attachment_location_ids": retired,
                "created_attachment_location_ids": created,
                "reserved_attachment_location_ids": [],
                "opening_id": None,
            }
        )
        self.frontiers.append(
            {
                "frontier_id": frontier_id,
                "component_id": "component_flat",
                "branch_id": "branch_flat",
                "topology": "LINEAR",
                "lifecycle_state": "CLOSED" if closed else "ACTIVE",
                "attachment_location_ids": list(after),
                "anchor_attachment_location_id": None,
                "active_yarn_id": None if closed else "yarn_flat",
                "created_by_transition_id": transition_id,
            }
        )
        operation_start = subject["entity_type"] == "CONSTRUCTION_OPERATION" and (
            subject["operation_id"] == "op_attach"
        )
        yarn_before = None if operation_start else "yarn_flat"
        color_before = None if operation_start else self.color["color_id"]
        self.events.append(
            {
                "event_id": event_id,
                "sequence_index": index,
                "subject_ref": subject,
                "active_yarn_id_before": yarn_before,
                "active_yarn_id_after": "yarn_flat",
                "active_color_id_before": color_before,
                "active_color_id_after": self.color["color_id"],
                "frontier_transition_ids": [transition_id],
            }
        )
        self.frontier, self.live = frontier_id, list(after)
        return event_id

    def attach(self) -> tuple[str, str]:
        subject = {"entity_type": "CONSTRUCTION_OPERATION", "operation_id": "op_attach"}
        anchor = self._location(subject, "FABRIC_ATTACHMENT_POINT")
        event = self._advance(subject, "CREATE", [], [], [anchor], [anchor])
        self.operations.append(
            {
                "operation_id": "op_attach",
                "operation_type": "ATTACH",
                "input_frontier_ids": [],
                "output_frontier_ids": [self.frontier],
                "attachment_location_ids": [anchor],
                "join_input_mappings": [],
                "input_yarn_ids": [],
                "output_yarn_ids": ["yarn_flat"],
                "opening_id": None,
                "design_requirement_id": None,
                "join_method": "NONE",
                "derivation_id": self.derivation(subject),
            }
        )
        return event, anchor

    def chain(self, course_id: str) -> str:
        identifier = f"st_{len(self.stitches):06d}"
        subject = {"entity_type": "STITCH", "stitch_id": identifier}
        top = self._location(subject, "TOP_LOOP")
        before = list(self.live)
        left = before[-1]
        after = [*before, top]
        self.stitches.append(
            {
                "stitch_id": identifier,
                "stitch_type": "CHAIN",
                "shaping": "PLAIN",
                "base_arity": 0,
                "top_arity": 1,
                "base_attachment_location_ids": [],
                "top_attachment_location_ids": [top],
                "frontier_edit": {
                    "edit_type": "INSERT_AT_GAP",
                    "frontier_id": self.frontier,
                    "left_location_id": left,
                    "right_location_id": None,
                },
                "yarn_id": "yarn_flat",
                "color_id": self.color["color_id"],
                "course_id": course_id,
                "derivation_id": self.derivation(subject),
            }
        )
        return self._advance(subject, "ADVANCE", [self.frontier], [], [top], after)

    def single_crochet(self, course_id: str, base: str) -> str:
        identifier = f"st_{len(self.stitches):06d}"
        subject = {"entity_type": "STITCH", "stitch_id": identifier}
        top = self._location(subject, "TOP_LOOP")
        index = self.live.index(base)
        before = list(self.live)
        after = [*before[:index], top, *before[index + 1 :]]
        self.stitches.append(
            {
                "stitch_id": identifier,
                "stitch_type": "SINGLE_CROCHET",
                "shaping": "PLAIN",
                "base_arity": 1,
                "top_arity": 1,
                "base_attachment_location_ids": [base],
                "top_attachment_location_ids": [top],
                "frontier_edit": {"edit_type": "REPLACE_SPAN", "frontier_id": self.frontier},
                "yarn_id": "yarn_flat",
                "color_id": self.color["color_id"],
                "course_id": course_id,
                "derivation_id": self.derivation(subject),
            }
        )
        return self._advance(subject, "ADVANCE", [self.frontier], [base], [top], after)

    def close(self) -> str:
        subject = {"entity_type": "CONSTRUCTION_OPERATION", "operation_id": "op_close"}
        event = self._advance(
            subject, "CLOSE", [self.frontier], list(self.live), [], [], closed=True
        )
        self.operations.append(
            {
                "operation_id": "op_close",
                "operation_type": "CLOSE",
                "input_frontier_ids": self.transitions[-1]["input_frontier_ids"],
                "output_frontier_ids": [self.frontier],
                "attachment_location_ids": [],
                "join_input_mappings": [],
                "input_yarn_ids": [],
                "output_yarn_ids": [],
                "opening_id": None,
                "design_requirement_id": None,
                "join_method": "NONE",
                "derivation_id": self.derivation(subject),
            }
        )
        return event


def _emit(
    design: dict[str, Any],
    material: dict[str, Any],
    config: FlatRowsRunConfig,
    provenance: CompileProvenance,
    columns: int,
    rows: int,
    parameter_hash: str,
    response_id: str,
    target_digest: str,
) -> dict[str, Any]:
    color = {key: design["colors"][0][key] for key in ("color_id", "label", "srgb_hex")}
    emitter = _FlatEmitter(color, parameter_hash)
    emitter.attach()
    first_course = "course_000000"
    chain_events = [emitter.chain(first_course) for _ in range(columns)]
    emitter.courses.append(
        {
            "course_id": first_course,
            "ordinal": 0,
            "component_id": "component_flat",
            "branch_id": "branch_flat",
            "course_form": "LINEAR",
            "turn_mode": "NONE",
            "work_direction": "FORWARD",
            "member_event_ids": chain_events,
            "input_frontier_ids": ["frontier_000000"],
            "output_frontier_ids": [emitter.frontier],
            "derivation_id": emitter.derivation(
                {"entity_type": "COURSE", "course_id": first_course}
            ),
        }
    )
    for ordinal in range(1, rows + 1):
        course_id = f"course_{ordinal:06d}"
        input_frontier = emitter.frontier
        bases = list(emitter.live[1:])  # retain the independent fabric anchor
        # The hook ends at the last foundation chain loop. Row 1 returns toward
        # the chain's first loop; subsequent rows alternate from that edge.
        reverse = ordinal % 2 == 1
        work_bases = list(reversed(bases)) if reverse else bases
        members = [emitter.single_crochet(course_id, base) for base in work_bases]
        emitter.courses.append(
            {
                "course_id": course_id,
                "ordinal": ordinal,
                "component_id": "component_flat",
                "branch_id": "branch_flat",
                "course_form": "LINEAR",
                "turn_mode": "TURN",
                "work_direction": "REVERSE" if reverse else "FORWARD",
                "member_event_ids": members,
                "input_frontier_ids": [input_frontier],
                "output_frontier_ids": [emitter.frontier],
                "derivation_id": emitter.derivation(
                    {"entity_type": "COURSE", "course_id": course_id}
                ),
            }
        )
    emitter.close()
    parameter_values: dict[str, Any] = {
        "flat.profile": _PARAMETER_PROFILE,
        "flat.columns": columns,
        "flat.rows": rows,
        "flat.material_response_id": response_id,
        "flat.target_geometry_sha256": target_digest,
        "flat.row_model": "DIMENSION_TIMES_LINEAR_PITCH_V1",
        "flat.anchor_model": "UNBOUND_EXTERNAL_FABRIC_POINT_V1",
        "flat.tie_order": "WIDTH_RESIDUAL,HEIGHT_RESIDUAL,STITCHES,COURSES,ROWS,COLUMNS",
        "flat.run_config_sha256": _run_hash(config),
    }
    parameter_values.update({f"flat.run.{name}": value for name, value in asdict(config).items()})
    for name, parameter_value in provenance.parameters:
        if name.startswith("flat.") or name == "source_snapshot_sha256":
            raise GenerationError(
                GenerationStatus.INVALID_SOLVER_INPUT, "provenance.reserved_flat_parameter"
            )
        parameter_values[name] = parameter_value
    parameter_values["source_snapshot_sha256"] = provenance.source_snapshot_sha256
    parameters = [
        {"name": name, "value": value} for name, value in sorted(parameter_values.items())
    ]
    # The derivations were initialized with this exact solver-parameter hash.
    design_validator = SemanticValidator(
        design_specs={design["design_spec_id"]: design},
        material_profiles={
            material["profile_id"]: material,
            (material["profile_id"], material["revision"]): material,
        },
    )
    design_digest = canonical_hash(design, CanonicalProfile.DESIGN_SPEC, validator=design_validator)
    material_digest = canonical_hash(material, CanonicalProfile.MATERIAL_PROFILE)
    value = {
        "schema_version": "1.0.0",
        "semantics_profile": "CROCHET_CORE_1.0.0",
        "crochet_ir_id": "cir_flat_rows",
        "design_spec_ref": {"design_spec_id": design["design_spec_id"], "sha256": design_digest},
        "units": {"length": "MILLIMETER", "mass": "GRAM", "angle": "RADIAN"},
        "required_capabilities": list(_CAPABILITIES),
        "colors": [color],
        "yarns": [
            {
                "yarn_id": "yarn_flat",
                "label": "Yarn A",
                "color_id": color["color_id"],
                "material_profile_ref": {
                    "profile_id": material["profile_id"],
                    "revision": material["revision"],
                    "sha256": material_digest,
                },
            }
        ],
        "attachment_locations": emitter.attachments,
        "stitches": emitter.stitches,
        "construction_operations": emitter.operations,
        "construction_sequence": emitter.events,
        "courses": emitter.courses,
        "course_order": [course["course_id"] for course in emitter.courses],
        "frontiers": emitter.frontiers,
        "frontier_transitions": emitter.transitions,
        "branches": [
            {
                "branch_id": "branch_flat",
                "component_id": "component_flat",
                "parent_branch_ids": [],
                "created_by_transition_id": None,
                "course_ids": [course["course_id"] for course in emitter.courses],
                "entry_frontier_ids": ["frontier_000000"],
                "terminal_frontier_ids": [emitter.frontier],
            }
        ],
        "components": [
            {
                "component_id": "component_flat",
                "branch_ids": ["branch_flat"],
                "initial_frontier_ids": ["frontier_000000"],
                "terminal_frontier_ids": [emitter.frontier],
            }
        ],
        "openings": [],
        "yarn_paths": [
            {
                "yarn_path_id": "ypath_flat",
                "yarn_id": "yarn_flat",
                "segments": [
                    {
                        "yarn_segment_id": "yseg_flat",
                        "start_operation_id": "op_attach",
                        "start_operation_type": "ATTACH",
                        "event_ids": [event["event_id"] for event in emitter.events[1:]],
                        "end_operation_id": None,
                        "end_operation_type": None,
                    }
                ],
            }
        ],
        "derivations": emitter.derivations,
        "provenance": {
            "generator": {"solver_family": "FLAT", "name": "flat-sc-rows", "version": "1"},
            "solver_parameters": parameters,
            "solver_parameters_sha256": parameter_hash,
            "random_seed": config.random_seed,
            "search_budget": {
                "budget_type": "CANDIDATE_EVALUATIONS",
                "limit": config.max_candidate_evaluations,
                "consumed": 0,
                "exhausted": False,
            },
            "input_artifacts": [
                {
                    "artifact_id": design["target_geometry"]["artifact"]["artifact_id"],
                    "artifact_role": "TARGET_GEOMETRY",
                    "sha256": design["target_geometry"]["artifact"]["sha256"],
                }
            ],
            "software_commit": provenance.software_commit,
            "canonicalization": {
                "profile": "CROCHET_IR_CANONICAL_JSON_V1",
                "hash_algorithm": "SHA-256",
            },
        },
    }
    # Keep all raw source provenance parameters and bind the resolved run values.
    return cast(dict[str, Any], value)


def _run_hash(config: FlatRowsRunConfig) -> str:
    payload = {"profile": _RUN_PROFILE, **asdict(config)}
    return sha256(
        b"Crochet.AI\x00" + _RUN_PROFILE.encode("ascii") + b"\x00" + rfc8785.dumps(payload)
    ).hexdigest()


def _parameter_hash(
    provenance: CompileProvenance,
    config: FlatRowsRunConfig,
    columns: int,
    rows: int,
    response_id: str,
    target_sha256: str,
) -> str:
    names = {name for name, _ in provenance.parameters}
    if any(name.startswith("flat.") or name == "source_snapshot_sha256" for name in names):
        raise GenerationError(
            GenerationStatus.INVALID_SOLVER_INPUT, "provenance.reserved_flat_parameter"
        )
    values: dict[str, str | int | float | bool] = dict(provenance.parameters)
    values.update(
        {
            "flat.profile": _PARAMETER_PROFILE,
            "flat.columns": columns,
            "flat.rows": rows,
            "flat.material_response_id": response_id,
            "flat.target_geometry_sha256": target_sha256,
            "flat.row_model": "DIMENSION_TIMES_LINEAR_PITCH_V1",
            "flat.anchor_model": "UNBOUND_EXTERNAL_FABRIC_POINT_V1",
            "flat.tie_order": "WIDTH_RESIDUAL,HEIGHT_RESIDUAL,STITCHES,COURSES,ROWS,COLUMNS",
            "flat.run_config_sha256": _run_hash(config),
            "source_snapshot_sha256": provenance.source_snapshot_sha256,
        }
    )
    values.update({f"flat.run.{name}": value for name, value in asdict(config).items()})
    parameters = [{"name": name, "value": value} for name, value in sorted(values.items())]
    return sha256(
        b"Crochet.AI\x00" + _PARAMETER_PROFILE.encode("ascii") + b"\x00" + rfc8785.dumps(parameters)
    ).hexdigest()


def _candidate_key(
    columns: int,
    rows: int,
    stitch_pitch: Fraction,
    course_pitch: Fraction,
    width: Fraction,
    height: Fraction,
) -> tuple[Fraction, Fraction, int, int, int, int]:
    return (
        abs(columns * stitch_pitch - width),
        abs(rows * course_pitch - height),
        columns + rows * columns,
        rows + 1,
        rows,
        columns,
    )


def generate_flat_rows(
    design: dict[str, Any],
    material: dict[str, Any],
    target_bytes: bytes,
    run_config: FlatRowsRunConfig,
    provenance: CompileProvenance,
) -> dict[str, Any]:
    """Generate one best-prefix complete FLAT/ROWS SC CrochetIR candidate.

    The exact pitch-times-count rectangle fit is a bounded selection hypothesis,
    not geometry verification or proof of physical dimensions.
    """
    if (
        type(design) is not dict
        or type(material) is not dict
        or type(target_bytes) is not bytes
        or type(run_config) is not FlatRowsRunConfig
        or type(provenance) is not CompileProvenance
    ):
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "input.native_types")
    if (
        type(design.get("design_spec_id")) is not str
        or type(material.get("profile_id")) is not str
        or type(material.get("revision")) is not int
    ):
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "input.identity_native_types")
    run_config.validate()
    if (
        type(provenance.software_commit) is not str
        or type(provenance.source_snapshot_sha256) is not str
        or type(provenance.parameters) is not tuple
        or any(
            type(item) is not tuple
            or len(item) != 2
            or type(item[0]) is not str
            or type(item[1]) not in {str, int, float, bool}
            for item in provenance.parameters
        )
    ):
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "provenance.native_types")
    provenance.validate()
    if any(
        name.startswith(("flat.", "source_snapshot_sha256")) for name, _ in provenance.parameters
    ):
        raise GenerationError(
            GenerationStatus.INVALID_SOLVER_INPUT, "provenance.reserved_flat_parameter"
        )
    target, target_digest = _target_record(target_bytes, design)
    profile_by_id = cast(str, material.get("profile_id"))
    profile_revision = cast(int, material.get("revision"))
    material_profiles: dict[str | tuple[str, int], dict[str, Any]] = {
        profile_by_id: material,
        (profile_by_id, profile_revision): material,
    }
    validator = SemanticValidator(
        design_specs={design.get("design_spec_id", ""): design},
        material_profiles=material_profiles,
    )
    material_report = validator.validate_material_profile(material)
    design_report = validator.validate_design_spec(design)
    if not material_report.ok or not design_report.ok:
        report = material_report if not material_report.ok else design_report
        raise GenerationError(
            GenerationStatus.INVALID_SOLVER_INPUT, report.diagnostics[0].message_key
        )
    if design["project_type"] != "FLAT":
        raise GenerationError(GenerationStatus.NOT_APPLICABLE, "design.project_type")
    constraints = design["domain_constraints"]
    if (
        constraints["domain"] != "FLAT"
        or constraints["work_structure"] != "ROWS"
        or constraints["repeat_policy"] not in {"NONE", "FIT_WITHIN_DIMENSION_TOLERANCE"}
    ):
        raise GenerationError(GenerationStatus.NOT_APPLICABLE, "design.flat_scope")
    solver = design["solver_options"]
    if "FLAT" not in solver["allowed_solver_families"]:
        raise GenerationError(GenerationStatus.NOT_APPLICABLE, "design.flat_solver_disallowed")
    if run_config.parameter_profile_id != solver["parameter_profile_id"]:
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "config.parameter_profile")
    if run_config.random_seed != solver["random_seed"]:
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "config.random_seed")
    if run_config.max_candidate_evaluations > solver["max_candidate_evaluations"]:
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "config.candidate_budget")
    allowed_stitches = set(design["difficulty_constraints"]["allowed_stitch_types"])
    if not {"CHAIN", "SINGLE_CROCHET"} <= allowed_stitches:
        raise GenerationError(GenerationStatus.NOT_APPLICABLE, "design.foundation_or_sc_disallowed")
    operations_allowed = set(design["difficulty_constraints"]["allowed_construction_operations"])
    if not {"ATTACH", "CLOSE"} <= operations_allowed:
        raise GenerationError(GenerationStatus.NOT_APPLICABLE, "design.operations_disallowed")
    if len(design["colors"]) != 1:
        raise GenerationError(GenerationStatus.NOT_APPLICABLE, "design.single_color_only")
    if design["construction_constraints"].get("intentional_openings"):
        raise GenerationError(GenerationStatus.NOT_APPLICABLE, "design.openings_unsupported")
    measurements = {
        value["measurement_id"]: value for value in design["dimensions"]["measurements"]
    }
    width_measurement = measurements.get(target["width_measurement_id"])
    height_measurement = measurements.get(target["height_measurement_id"])
    if (
        width_measurement is None
        or height_measurement is None
        or width_measurement["semantic"] != "OVERALL_WIDTH"
        or height_measurement["semantic"] != "OVERALL_HEIGHT"
    ):
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "target.dimension_bindings")
    width = _fraction(width_measurement["value_mm"], "design.width")
    width_tolerance = _fraction(width_measurement["tolerance_mm"], "design.width_tolerance")
    height = _fraction(height_measurement["value_mm"], "design.height")
    height_tolerance = _fraction(height_measurement["tolerance_mm"], "design.height_tolerance")
    if min(width, height) <= 0 or min(width_tolerance, height_tolerance) < 0:
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "design.dimension_bounds")
    response = _material_response(design, material, run_config)
    stitch_pitch = _fraction(
        response["effective_gauge"]["effective_stitch_pitch_mm"], "material.stitch_pitch"
    )
    course_pitch = _fraction(
        response["effective_gauge"]["effective_course_pitch_mm"], "material.course_pitch"
    )
    if stitch_pitch <= 0 or course_pitch <= 0:
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "material.pitch")

    bindings = {
        "design_spec_sha256": canonical_hash(
            design, CanonicalProfile.DESIGN_SPEC, validator=validator
        ),
        "material_profile_sha256": canonical_hash(material, CanonicalProfile.MATERIAL_PROFILE),
        "target_geometry_sha256": target_digest,
        "run_config_sha256": _run_hash(run_config),
        "source_snapshot_sha256": provenance.source_snapshot_sha256,
        "software_commit": provenance.software_commit,
    }
    evaluations = feasible = 0
    best: tuple[tuple[Fraction, Fraction, int, int, int, int], int, int] | None = None
    total = run_config.max_columns * run_config.max_rows
    exhausted = False
    for columns in range(1, run_config.max_columns + 1):
        for rows in range(1, run_config.max_rows + 1):
            if evaluations >= run_config.max_candidate_evaluations:
                exhausted = True
                break
            evaluations += 1
            if (
                abs(columns * stitch_pitch - width) > width_tolerance
                or abs(rows * course_pitch - height) > height_tolerance
            ):
                continue
            feasible += 1
            event_count, location_count, membership_count = _resource_counts(columns, rows)
            if (
                event_count > run_config.max_events
                or location_count > run_config.max_attachment_locations
                or membership_count > run_config.max_memberships
            ):
                continue
            key = _candidate_key(columns, rows, stitch_pitch, course_pitch, width, height)
            if best is None or key < best[0]:
                best = key, columns, rows
        if exhausted:
            break
    complete = not exhausted and evaluations == total
    status = (
        GenerationStatus.SEARCH_BUDGET_EXHAUSTED
        if exhausted
        else GenerationStatus.NO_FEASIBLE_CONSTRUCTION
        if best is None
        else GenerationStatus.CANDIDATES_EMITTED
    )
    candidate = None
    candidate_digest = None
    chosen: dict[str, int] | None = None
    selected_resources: dict[str, int] | None = None
    width_residual: Fraction | None = None
    height_residual: Fraction | None = None
    if best is not None:
        _, columns, rows = best
        width_residual, height_residual = best[0][:2]
        chosen = {"columns": columns, "rows": rows}
        selected_events, selected_locations, selected_memberships = _resource_counts(columns, rows)
        selected_resources = {
            "events": selected_events,
            "attachment_locations": selected_locations,
            "reference_list_memberships": selected_memberships,
        }
        parameter_hash = _parameter_hash(
            provenance, run_config, columns, rows, response["response_id"], target_digest
        )
        candidate = _emit(
            design,
            material,
            run_config,
            provenance,
            columns,
            rows,
            parameter_hash,
            response["response_id"],
            target_digest,
        )
        candidate["provenance"]["search_budget"]["consumed"] = evaluations
        candidate["provenance"]["search_budget"]["exhausted"] = exhausted
        report = validator.validate_crochet_ir(candidate)
        if not report.ok:
            raise ArtifactValidationError(report)
        candidate_digest = canonical_hash(
            candidate, CanonicalProfile.CROCHET_IR, validator=validator
        )
    return {
        "profile": _RUN_PROFILE,
        "status": status.value,
        "reason": "budget.candidate_evaluations"
        if exhausted
        else "budget.candidate_structure_limits"
        if best is None and feasible > 0
        else None,
        "candidate": candidate,
        "candidate_sha256": candidate_digest,
        "selected_counts": chosen,
        "candidate_resources": selected_resources,
        "search": {
            "candidate_evaluations": evaluations,
            "candidate_evaluation_limit": run_config.max_candidate_evaluations,
            "search_domain_pairs": total,
            "geometrically_feasible_pairs": feasible,
            "complete": complete,
            "exhausted": exhausted,
        },
        "bindings": bindings,
        "material_response_id": response["response_id"],
        "pitch_mm_binary64_ratios": {
            "stitch": [str(stitch_pitch.numerator), str(stitch_pitch.denominator)],
            "course": [str(course_pitch.numerator), str(course_pitch.denominator)],
        },
        "dimension_residuals_mm": None
        if chosen is None
        else {
            "width": [
                str(cast(Fraction, width_residual).numerator),
                str(cast(Fraction, width_residual).denominator),
            ],
            "height": [
                str(cast(Fraction, height_residual).numerator),
                str(cast(Fraction, height_residual).denominator),
            ],
        },
        "work": {
            "candidate_evaluations": evaluations,
            "pair_predicate_evaluations": evaluations,
        },
        "units_and_bounds": {
            "length": "MILLIMETER",
            "column_count": [1, run_config.max_columns],
            "row_count": [1, run_config.max_rows],
            "hard_count_ceiling": _MAX_COUNT,
            "event_limit": run_config.max_events,
            "attachment_location_limit": run_config.max_attachment_locations,
            "membership_limit": run_config.max_memberships,
        },
        "acceptance": {
            "geometry_verified": False,
            "physical_status": "UNTESTED",
            "model": "count times calibrated pitch is a cell-coverage hypothesis",
        },
    }
