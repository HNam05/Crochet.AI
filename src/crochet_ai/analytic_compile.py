"""Direct compilation of complete cyclic count schedules, independent of Pattern V1.

Only a single yarn, closed non-branching SC construction is emitted. This is
candidate generation, not geometry or physical acceptance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from itertools import pairwise
from typing import Any

import rfc8785

from .canonical import CanonicalProfile, canonical_hash, validate_ijson
from .diagnostics import ArtifactValidationError
from .solver_types import GenerationError, GenerationStatus
from .validation import SemanticValidator


@dataclass(frozen=True, slots=True)
class PlannedStitch:
    base_indices: tuple[int, ...]
    top_count: int


def balanced_course(before: int, after: int, phase: int) -> tuple[PlannedStitch, ...]:
    """Even cyclic shaping gaps, at an explicit base-index rotation (no search)."""
    if not (
        type(before) is int
        and type(after) is int
        and type(phase) is int
        and 1 <= before <= 512
        and 1 <= after <= 512
        and 0 <= phase < before
    ):
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "placement.bounds")
    delta = after - before
    decreases = max(-delta, 0)
    shaping = abs(delta)
    operations = before - decreases
    if shaping > operations:
        raise GenerationError(GenerationStatus.NO_FEASIBLE_CONSTRUCTION, "placement.arity")
    result = []
    cursor = phase
    for ordinal in range(operations):
        shaped = (ordinal + 1) * shaping // operations > ordinal * shaping // operations
        base_count = 2 if shaped and delta < 0 else 1
        result.append(
            PlannedStitch(
                tuple((cursor + j) % before for j in range(base_count)),
                2 if shaped and delta > 0 else 1,
            )
        )
        cursor += base_count
    return tuple(result)


@dataclass(frozen=True, slots=True)
class CompileProvenance:
    software_commit: str
    source_snapshot_sha256: str
    parameters: tuple[tuple[str, str | int | float | bool], ...]

    def validate(self) -> None:
        if not (
            isinstance(self.software_commit, str)
            and re.fullmatch(r"[a-f0-9]{40,64}", self.software_commit)
            and isinstance(self.source_snapshot_sha256, str)
            and re.fullmatch(r"[a-f0-9]{64}", self.source_snapshot_sha256)
            and set(self.source_snapshot_sha256) != {"0"}
        ):
            raise GenerationError(
                GenerationStatus.INVALID_SOLVER_INPUT, "compiler.source_provenance"
            )
        names = set()
        for name, value in self.parameters:
            if (
                not isinstance(name, str)
                or not name
                or name in names
                or name == "source_snapshot_sha256"
                or type(value) not in {str, int, float, bool}
            ):
                raise GenerationError(
                    GenerationStatus.INVALID_SOLVER_INPUT, "compiler.parameter_names"
                )
            names.add(name)
        validate_ijson([[name, value] for name, value in self.parameters])


def compile_closed_schedule(
    design: dict[str, Any],
    material: dict[str, Any],
    counts: tuple[int, ...],
    phases: tuple[int, ...],
    provenance: CompileProvenance,
    *,
    max_stitches: int,
    generation_profile: str = "ANALYTIC_CLOSED_SC_V1",
) -> dict[str, Any]:
    """Compile all-or-nothing, then check with the unchanged semantic validator."""
    provenance.validate()
    if not isinstance(generation_profile, str) or generation_profile not in {
        "ANALYTIC_CLOSED_SC_V1",
        "GEODESIC_CLOSED_SC_V1",
    }:
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "compiler.generation_profile")
    material_report = SemanticValidator().validate_material_profile(material)
    if not material_report.ok:
        raise ArtifactValidationError(material_report)
    if not isinstance(design.get("design_spec_id"), str):
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "design_spec.identity_invalid")
    validator = SemanticValidator(
        material_profiles={
            material.get("profile_id", ""): material,
            (material.get("profile_id", ""), material.get("revision", 0)): material,
        },
        design_specs={design.get("design_spec_id", ""): design},
    )
    for report in (validator.validate_design_spec(design),):
        if not report.ok:
            raise ArtifactValidationError(report)
    if not (
        isinstance(counts, tuple)
        and isinstance(phases, tuple)
        and 1 <= len(counts) <= 512
        and len(phases) == len(counts) - 1
        and all(type(n) is int and 1 <= n <= 512 for n in counts)
        and counts[0] >= 2
        and type(max_stitches) is int
        and 1 <= max_stitches <= 10_000
    ):
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "compiler.bounds")
    if (
        design["project_type"] != "AMIGURUMI_3D"
        or design["domain_constraints"]["surface_mode"] != "CLOSED"
        or design["construction_constraints"]["intentional_openings"]
        or len(design["colors"]) != 1
    ):
        raise GenerationError(GenerationStatus.NOT_APPLICABLE, "compiler.closed_single_color_only")
    expected_material = design["material_profile"]
    bound_material = expected_material.get("profile", expected_material)
    digest = canonical_hash(material, CanonicalProfile.MATERIAL_PROFILE)
    expected_digest = (
        canonical_hash(bound_material, CanonicalProfile.MATERIAL_PROFILE)
        if expected_material["binding_type"] == "INLINE"
        else bound_material["sha256"]
    )
    if digest != expected_digest:
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "compiler.material_binding")
    difficulty = design["difficulty_constraints"]
    shaping_needed = {"INCREASE" for a, b in pairwise(counts) if b > a}
    shaping_needed |= {"DECREASE" for a, b in pairwise(counts) if b < a}
    if (
        "SINGLE_CROCHET" not in difficulty["allowed_stitch_types"]
        or not {"MAGIC_RING", "CLOSE"} <= set(difficulty["allowed_construction_operations"])
        or not shaping_needed <= set(difficulty["allowed_shaping"])
    ):
        raise GenerationError(GenerationStatus.NOT_APPLICABLE, "compiler.design_techniques")
    parameter_map = dict(provenance.parameters)
    if generation_profile == "GEODESIC_CLOSED_SC_V1":
        if "compiler_generation_profile" in parameter_map:
            raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "compiler.parameter_names")
        parameter_map["compiler_generation_profile"] = generation_profile
    parameter_map["source_snapshot_sha256"] = provenance.source_snapshot_sha256
    parameters = [{"name": name, "value": val} for name, val in sorted(parameter_map.items())]
    validate_ijson(parameters)
    parameter_hash = sha256(
        (
            b"Crochet.AI\0GEODESIC_CLOSED_SC_COMPILER_PARAMETERS_V1\0"
            if generation_profile == "GEODESIC_CLOSED_SC_V1"
            else b"Crochet.AI\0ANALYTIC_COMPILER_PARAMETERS_V1\0"
        )
        + rfc8785.dumps(parameters)
    ).hexdigest()
    if counts[0] + sum(min(a, b) for a, b in pairwise(counts)) > max_stitches:
        raise GenerationError(GenerationStatus.SEARCH_BUDGET_EXHAUSTED, "compiler.stitches")
    plans = [tuple(PlannedStitch((i,), 1) for i in range(counts[0]))]
    for before, after, phase in zip(counts, counts[1:], phases, strict=False):
        plans.append(balanced_course(before, after, phase))
    color = {key: design["colors"][0][key] for key in ("color_id", "label", "srgb_hex")}
    emitter = _Emitter(color["color_id"], parameter_hash, generation_profile)
    ring_subject = {"entity_type": "CONSTRUCTION_OPERATION", "operation_id": "op_ring"}
    sites = emitter.locations(ring_subject, counts[0], "MAGIC_RING_ANCHOR")
    emitter.operation("op_ring", "MAGIC_RING", [], sites, [], sites)
    initial = emitter.frontier_id
    for ordinal, plan in enumerate(plans):
        course_id = f"course_{ordinal:06d}"
        before_frontier = emitter.frontier_id
        before_locations = list(emitter.live)
        members = []
        for planned in plan:
            bases = [before_locations[index] for index in planned.base_indices]
            members.append(emitter.stitch(course_id, bases, planned.top_count))
        emitter.courses.append(
            {
                "course_id": course_id,
                "ordinal": ordinal,
                "component_id": "component_main",
                "branch_id": "branch_main",
                "course_form": "CYCLIC",
                "turn_mode": "CONTINUOUS_SPIRAL",
                "work_direction": "CLOCKWISE",
                "member_event_ids": members,
                "input_frontier_ids": [before_frontier],
                "output_frontier_ids": [emitter.frontier_id],
                "derivation_id": emitter.derivation(
                    {"entity_type": "COURSE", "course_id": course_id}
                ),
            }
        )
    emitter.operation("op_close", "CLOSE", [emitter.frontier_id], [], list(emitter.live), [])
    caps = ["CORE_STITCHES_V1", "MAGIC_RING_V1", "MULTI_STITCH_RING_V1"]
    if shaping_needed:
        caps.append("SHAPING_V1")
    value: dict[str, Any] = {
        "schema_version": "1.1.0",
        "semantics_profile": "CROCHET_CORE_1.1.0",
        "crochet_ir_id": "cir_analytic",
        "design_spec_ref": {
            "design_spec_id": design["design_spec_id"],
            "sha256": canonical_hash(design, CanonicalProfile.DESIGN_SPEC, validator=validator),
        },
        "units": {"length": "MILLIMETER", "mass": "GRAM", "angle": "RADIAN"},
        "required_capabilities": caps,
        "colors": [color],
        "yarns": [
            {
                "yarn_id": "yarn_main",
                "label": "Yarn A",
                "color_id": color["color_id"],
                "material_profile_ref": {
                    "profile_id": material["profile_id"],
                    "revision": material["revision"],
                    "sha256": digest,
                },
            }
        ],
        "attachment_locations": emitter.attachments,
        "stitches": emitter.stitches,
        "construction_operations": emitter.operations,
        "construction_sequence": emitter.events,
        "courses": emitter.courses,
        "course_order": [c["course_id"] for c in emitter.courses],
        "frontiers": emitter.frontiers,
        "frontier_transitions": emitter.transitions,
        "branches": [
            {
                "branch_id": "branch_main",
                "component_id": "component_main",
                "parent_branch_ids": [],
                "created_by_transition_id": None,
                "course_ids": [c["course_id"] for c in emitter.courses],
                "entry_frontier_ids": [initial],
                "terminal_frontier_ids": [emitter.frontier_id],
            }
        ],
        "components": [
            {
                "component_id": "component_main",
                "branch_ids": ["branch_main"],
                "initial_frontier_ids": [initial],
                "terminal_frontier_ids": [emitter.frontier_id],
            }
        ],
        "openings": [],
        "yarn_paths": [
            {
                "yarn_path_id": "ypath_main",
                "yarn_id": "yarn_main",
                "segments": [
                    {
                        "yarn_segment_id": "yseg_main",
                        "start_operation_id": "op_ring",
                        "start_operation_type": "MAGIC_RING",
                        "event_ids": [e["event_id"] for e in emitter.events[1:]],
                        "end_operation_id": None,
                        "end_operation_type": None,
                    }
                ],
            }
        ],
        "derivations": emitter.derivations,
        "provenance": {
            "generator": {
                "solver_family": emitter.solver_family,
                "name": emitter.generator_name,
                "version": "1",
            },
            "solver_parameters": parameters,
            "solver_parameters_sha256": parameter_hash,
            "random_seed": None
            if emitter.solver_family == "ANALYTIC"
            else design["solver_options"]["random_seed"],
            "search_budget": {
                "budget_type": "CANDIDATE_EVALUATIONS",
                "limit": 1,
                "consumed": 1,
                "exhausted": False,
            },
            "input_artifacts": [],
            "software_commit": provenance.software_commit,
            "canonicalization": {
                "profile": "CROCHET_IR_CANONICAL_JSON_V1",
                "hash_algorithm": "SHA-256",
            },
        },
    }
    report = validator.validate_crochet_ir(value)
    if not report.ok:
        raise ArtifactValidationError(report)
    return value


class _Emitter:
    def __init__(self, color_id: str, parameter_hash: str, generation_profile: str) -> None:
        self.solver_family = (
            "GEODESIC" if generation_profile == "GEODESIC_CLOSED_SC_V1" else "ANALYTIC"
        )
        self.generator_name = (
            "geodesic-graph-distance-closed-sc"
            if self.solver_family == "GEODESIC"
            else "analytic-closed-sc"
        )
        self.color_id = color_id
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
        self.frontier_id = ""

    def derivation(self, subject: dict[str, str]) -> str:
        identifier = f"deriv_{len(self.derivations):06d}"
        self.derivations.append(
            {
                "derivation_id": identifier,
                "method": "GEODESIC_COUPLING"
                if self.solver_family == "GEODESIC"
                else "ANALYTIC_RULE",
                "rule_id": "geodesic.graph-distance.closed-sc"
                if self.solver_family == "GEODESIC"
                else "analytic.closed-sc",
                "rule_version": "1",
                "parameter_sha256": self.parameter_hash,
                "subject_refs": [subject],
            }
        )
        return identifier

    def locations(self, subject: dict[str, str], count: int, kind: str) -> list[str]:
        identifiers = []
        for ordinal in range(count):
            identifier = f"loc_{len(self.attachments):06d}"
            self.attachments.append(
                {
                    "attachment_location_id": identifier,
                    "location_type": kind,
                    "producer_ref": subject,
                    "ordinal_within_producer": ordinal,
                }
            )
            identifiers.append(identifier)
        return identifiers

    def advance(
        self,
        subject: dict[str, str],
        kind: str,
        inputs: list[str],
        retired: list[str],
        created: list[str],
        after: list[str],
    ) -> str:
        index = len(self.events)
        tid, fid, eid = f"ftrans_{index:06d}", f"frontier_{index:06d}", f"ev_{index:06d}"
        self.transitions.append(
            {
                "frontier_transition_id": tid,
                "transition_index": index,
                "after_event_index": index,
                "caused_by_subject_ref": subject,
                "transition_type": kind,
                "input_frontier_ids": inputs,
                "output_frontier_ids": [fid],
                "retired_attachment_location_ids": retired,
                "created_attachment_location_ids": created,
                "reserved_attachment_location_ids": [],
                "opening_id": None,
            }
        )
        self.frontiers.append(
            {
                "frontier_id": fid,
                "component_id": "component_main",
                "branch_id": "branch_main",
                "topology": "CYCLIC",
                "lifecycle_state": "CLOSED" if kind == "CLOSE" else "ACTIVE",
                "attachment_location_ids": list(after),
                "anchor_attachment_location_id": after[0] if after else None,
                "active_yarn_id": None if kind == "CLOSE" else "yarn_main",
                "created_by_transition_id": tid,
            }
        )
        self.events.append(
            {
                "event_id": eid,
                "sequence_index": index,
                "subject_ref": subject,
                "active_yarn_id_before": "yarn_main" if index else None,
                "active_yarn_id_after": "yarn_main",
                "active_color_id_before": self.color_id if index else None,
                "active_color_id_after": self.color_id,
                "frontier_transition_ids": [tid],
            }
        )
        self.frontier_id, self.live = fid, list(after)
        return eid

    def operation(
        self,
        identifier: str,
        kind: str,
        inputs: list[str],
        sites: list[str],
        retired: list[str],
        after: list[str],
    ) -> None:
        subject = {"entity_type": "CONSTRUCTION_OPERATION", "operation_id": identifier}
        self.advance(
            subject, "CREATE" if kind == "MAGIC_RING" else "CLOSE", inputs, retired, sites, after
        )
        self.operations.append(
            {
                "operation_id": identifier,
                "operation_type": kind,
                "input_frontier_ids": inputs,
                "output_frontier_ids": [self.frontier_id],
                "attachment_location_ids": sites,
                "join_input_mappings": [],
                "input_yarn_ids": [],
                "output_yarn_ids": ["yarn_main"] if kind == "MAGIC_RING" else [],
                "opening_id": None,
                "design_requirement_id": None,
                "join_method": "NONE",
                "derivation_id": self.derivation(subject),
            }
        )

    def stitch(self, course_id: str, bases: list[str], top_count: int) -> str:
        identifier = f"st_{len(self.stitches):06d}"
        subject = {"entity_type": "STITCH", "stitch_id": identifier}
        tops = self.locations(subject, top_count, "TOP_LOOP")
        start = self.live.index(bases[0])
        # Rotate to the explicit span, replace it, then restore the surviving
        # origin (or first new top when that origin was retired).
        rotated = self.live[start:] + self.live[:start]
        if rotated[: len(bases)] != bases:
            raise GenerationError(
                GenerationStatus.INVALID_SOLVER_INPUT, "compiler.nonconsecutive_bases"
            )
        anchor = self.live[0] if self.live[0] not in bases else tops[0]
        after = tops + rotated[len(bases) :]
        offset = after.index(anchor)
        after = after[offset:] + after[:offset]
        self.stitches.append(
            {
                "stitch_id": identifier,
                "stitch_type": "SINGLE_CROCHET",
                "shaping": "INCREASE"
                if top_count == 2
                else "DECREASE"
                if len(bases) == 2
                else "PLAIN",
                "base_arity": len(bases),
                "top_arity": top_count,
                "base_attachment_location_ids": bases,
                "top_attachment_location_ids": tops,
                "frontier_edit": {"edit_type": "REPLACE_SPAN", "frontier_id": self.frontier_id},
                "yarn_id": "yarn_main",
                "color_id": self.color_id,
                "course_id": course_id,
                "derivation_id": self.derivation(subject),
            }
        )
        return self.advance(subject, "ADVANCE", [self.frontier_id], bases, tops, after)
