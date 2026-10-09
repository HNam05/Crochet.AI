"""Explicit, bounded compiler for one SC reserve/continuation lifecycle.

This emits structural CrochetIR only. It does not solve target geometry or
establish physical feasibility.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any

import rfc8785

from .analytic_compile import CompileProvenance, _Emitter, balanced_course, compile_closed_schedule
from .canonical import CanonicalProfile, canonical_hash, validate_ijson
from .diagnostics import ArtifactValidationError
from .solver_types import GenerationError, GenerationStatus
from .validation import SemanticValidator

PROFILE = "EXPLICIT_RESERVE_SC_V1"


def compile_reserve_schedule(
    design: dict[str, Any],
    material: dict[str, Any],
    initial_count: int,
    reserved_count: int,
    continuing_counts: tuple[int, ...],
    continuing_phases: tuple[int, ...],
    provenance: CompileProvenance,
    *,
    max_events: int = 8192,
    max_attachment_locations: int = 16384,
    max_frontier_location_references: int = 262144,
) -> dict[str, Any]:
    """Compile a cyclic SC course, reserve its suffix, continue the active prefix,
    then close both obligations.

    Continued courses use deterministic balanced SC shaping. Phase values are
    explicit base-index rotations, one per transition. The initial active
    prefix is ``initial_count - reserved_count`` locations.
    """
    if not isinstance(provenance, CompileProvenance):
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "reserve.provenance")
    provenance.validate()
    if not (
        type(initial_count) is int
        and 2 <= initial_count <= 512
        and type(reserved_count) is int
        and 1 <= reserved_count < initial_count
        and isinstance(continuing_counts, tuple)
        and 1 <= len(continuing_counts) <= 512
        and isinstance(continuing_phases, tuple)
        and len(continuing_phases) == len(continuing_counts)
        and all(type(n) is int and 1 <= n <= 512 for n in continuing_counts)
        and all(type(p) is int and p >= 0 for p in continuing_phases)
        and type(max_events) is int
        and 1 <= max_events <= 8192
        and type(max_attachment_locations) is int
        and 1 <= max_attachment_locations <= 16384
        and type(max_frontier_location_references) is int
        and 1 <= max_frontier_location_references <= 262144
    ):
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "reserve.bounds")
    if not isinstance(design, dict) or not isinstance(material, dict):
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "reserve.artifacts")
    material_report = SemanticValidator().validate_material_profile(material)
    if not material_report.ok:
        raise ArtifactValidationError(material_report)
    if not isinstance(design.get("design_spec_id"), str):
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "reserve.design_identity")
    design_value, material_value = deepcopy(design), deepcopy(material)
    validator = SemanticValidator(
        material_profiles={
            material_value.get("profile_id", ""): material_value,
            (
                material_value.get("profile_id", ""),
                material_value.get("revision", 0),
            ): material_value,
        },
        design_specs={design_value.get("design_spec_id", ""): design_value},
    )
    for report in (
        validator.validate_material_profile(material_value),
        validator.validate_design_spec(design_value),
    ):
        if not report.ok:
            raise ArtifactValidationError(report)
    binding = design_value["material_profile"]
    bound = binding.get("profile", binding)
    material_hash = canonical_hash(material_value, CanonicalProfile.MATERIAL_PROFILE)
    expected_hash = (
        canonical_hash(bound, CanonicalProfile.MATERIAL_PROFILE)
        if binding["binding_type"] == "INLINE"
        else bound["sha256"]
    )
    if material_hash != expected_hash:
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "reserve.material_binding")
    allowed_ops = set(design_value["difficulty_constraints"]["allowed_construction_operations"])
    allowed_stitches = set(design_value["difficulty_constraints"]["allowed_stitch_types"])
    if (
        not {"MAGIC_RING", "RESERVE", "CLOSE"} <= allowed_ops
        or "SINGLE_CROCHET" not in allowed_stitches
    ):
        raise GenerationError(GenerationStatus.NOT_APPLICABLE, "reserve.design_techniques")
    if (
        design_value["project_type"] != "AMIGURUMI_3D"
        or design_value["domain_constraints"]["surface_mode"] != "CLOSED"
        or design_value["construction_constraints"]["intentional_openings"]
        or len(design_value["colors"]) != 1
    ):
        raise GenerationError(GenerationStatus.NOT_APPLICABLE, "reserve.domain")
    solver_options = design_value["solver_options"]
    if "FRONTIER" not in solver_options["allowed_solver_families"]:
        raise GenerationError(GenerationStatus.NOT_APPLICABLE, "reserve.solver_family")
    shaping_needed = {
        "INCREASE" if after > before else "DECREASE"
        for before, after in zip(
            (initial_count - reserved_count, *continuing_counts[:-1]),
            continuing_counts,
            strict=True,
        )
        if after != before
    }
    if not shaping_needed <= set(design_value["difficulty_constraints"]["allowed_shaping"]):
        raise GenerationError(GenerationStatus.NOT_APPLICABLE, "reserve.design_shaping")
    preceding_counts = (initial_count - reserved_count, *continuing_counts[:-1])
    expected_events = (
        initial_count
        + 4
        + sum(
            min(before, after)
            for before, after in zip(preceding_counts, continuing_counts, strict=True)
        )
    )
    expected_locations = 2 * initial_count + sum(continuing_counts)
    if expected_events > max_events or expected_locations > max_attachment_locations:
        raise GenerationError(GenerationStatus.SEARCH_BUDGET_EXHAUSTED, "reserve.budget_preflight")
    expected_frontier_references = initial_count * (initial_count + 2)
    plans = []
    for before, after, phase in zip(
        preceding_counts,
        continuing_counts,
        continuing_phases,
        strict=True,
    ):
        if phase >= before:
            raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "reserve.phase")
        try:
            plan = balanced_course(before, after, phase)
        except GenerationError as error:
            raise GenerationError(error.status, "reserve.no_feasible_course") from error
        plans.append(plan)
        live_count = before
        for stitch in plan:
            live_count += stitch.top_count - len(stitch.base_indices)
            expected_frontier_references += live_count
    if expected_frontier_references > max_frontier_location_references:
        raise GenerationError(
            GenerationStatus.SEARCH_BUDGET_EXHAUSTED, "reserve.frontier_reference_budget"
        )

    source_parameters = dict(provenance.parameters)
    owned_parameters: dict[str, Any] = {
        "compiler_generation_profile": PROFILE,
        "initial_count": initial_count,
        "reserved_count": reserved_count,
        "continuing_counts": list(continuing_counts),
        "continuing_phases": list(continuing_phases),
        "max_events": max_events,
        "max_attachment_locations": max_attachment_locations,
        "max_frontier_location_references": max_frontier_location_references,
        "design_random_seed": solver_options["random_seed"],
        "design_parameter_profile_id": solver_options["parameter_profile_id"],
        "design_max_candidate_evaluations": solver_options["max_candidate_evaluations"],
        "source_snapshot_sha256": provenance.source_snapshot_sha256,
        "design_spec_sha256": canonical_hash(
            design_value, CanonicalProfile.DESIGN_SPEC, validator=validator
        ),
        "material_profile_sha256": material_hash,
    }
    if source_parameters.keys() & owned_parameters.keys():
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "reserve.parameter_collision")
    parameters_map = source_parameters | owned_parameters
    parameters = [{"name": key, "value": parameters_map[key]} for key in sorted(parameters_map)]
    validate_ijson(parameters)
    parameter_hash = sha256(
        b"Crochet.AI\0EXPLICIT_RESERVE_SC_COMPILER_PARAMETERS_V1\0" + rfc8785.dumps(parameters)
    ).hexdigest()

    value = compile_closed_schedule(
        design_value,
        material_value,
        (initial_count,),
        (),
        provenance,
        max_stitches=min(max_attachment_locations, 10_000),
    )
    if "FRONTIER_BRANCHING_V1" not in value["required_capabilities"]:
        value["required_capabilities"].append("FRONTIER_BRANCHING_V1")
    if shaping_needed and "SHAPING_V1" not in value["required_capabilities"]:
        value["required_capabilities"].append("SHAPING_V1")
    # Remove only the temporary terminal close produced by the reusable initial
    # course lowering. All prior events, transitions, frontiers and yarn history remain.
    close_op = next(
        op for op in value["construction_operations"] if op["operation_type"] == "CLOSE"
    )
    close_event = next(
        event
        for event in value["construction_sequence"]
        if event["subject_ref"].get("operation_id") == close_op["operation_id"]
    )
    close_transition = next(
        t
        for t in value["frontier_transitions"]
        if t["frontier_transition_id"] in close_event["frontier_transition_ids"]
    )
    value["construction_operations"].remove(close_op)
    value["construction_sequence"].remove(close_event)
    value["frontier_transitions"].remove(close_transition)
    value["frontiers"] = [
        f
        for f in value["frontiers"]
        if f["frontier_id"] not in close_transition["output_frontier_ids"]
    ]
    value["derivations"] = [
        d for d in value["derivations"] if d["derivation_id"] != close_op["derivation_id"]
    ]
    active_frontier_id = close_transition["input_frontier_ids"][0]
    for branch in value["branches"]:
        branch["terminal_frontier_ids"] = [active_frontier_id]
    for component in value["components"]:
        component["terminal_frontier_ids"] = [active_frontier_id]
    value["yarn_paths"][0]["segments"][0]["event_ids"].remove(close_event["event_id"])

    emitter = _Emitter(value["colors"][0]["color_id"], parameter_hash, "ANALYTIC_CLOSED_SC_V1")
    emitter.attachments = value["attachment_locations"]
    emitter.stitches = value["stitches"]
    emitter.operations = value["construction_operations"]
    emitter.events = value["construction_sequence"]
    emitter.frontiers = value["frontiers"]
    emitter.transitions = value["frontier_transitions"]
    emitter.derivations = value["derivations"]
    emitter.courses = value["courses"]
    emitter.frontier_id = active_frontier_id
    emitter.live = next(
        f["attachment_location_ids"]
        for f in emitter.frontiers
        if f["frontier_id"] == active_frontier_id
    )

    reserve_transition_id = f"ftrans_{len(emitter.events):06d}"
    reserve_event_id = f"ev_{len(emitter.events):06d}"
    active_locations = list(emitter.live[: initial_count - reserved_count])
    reserved_locations = list(emitter.live[initial_count - reserved_count :])
    reserve_subject = {"entity_type": "CONSTRUCTION_OPERATION", "operation_id": "op_reserve"}
    reserve_derivation = emitter.derivation(reserve_subject)
    value["construction_operations"].append(
        {
            "operation_id": "op_reserve",
            "operation_type": "RESERVE",
            "input_frontier_ids": [active_frontier_id],
            "output_frontier_ids": ["frontier_continuing", "frontier_reserved"],
            "attachment_location_ids": [],
            "join_input_mappings": [],
            "input_yarn_ids": [],
            "output_yarn_ids": [],
            "opening_id": None,
            "design_requirement_id": None,
            "join_method": "NONE",
            "derivation_id": reserve_derivation,
        }
    )
    event_index = len(emitter.events)
    value["construction_sequence"].append(
        {
            "event_id": reserve_event_id,
            "sequence_index": event_index,
            "subject_ref": reserve_subject,
            "active_yarn_id_before": "yarn_main",
            "active_yarn_id_after": "yarn_main",
            "active_color_id_before": emitter.color_id,
            "active_color_id_after": emitter.color_id,
            "frontier_transition_ids": [reserve_transition_id],
        }
    )
    value["frontier_transitions"].append(
        {
            "frontier_transition_id": reserve_transition_id,
            "transition_index": event_index,
            "after_event_index": event_index,
            "caused_by_subject_ref": reserve_subject,
            "transition_type": "RESERVE",
            "input_frontier_ids": [active_frontier_id],
            "output_frontier_ids": ["frontier_continuing", "frontier_reserved"],
            "retired_attachment_location_ids": [],
            "created_attachment_location_ids": [],
            "reserved_attachment_location_ids": reserved_locations,
            "opening_id": None,
        }
    )
    for fid, locations, lifecycle in (
        ("frontier_continuing", active_locations, "ACTIVE"),
        ("frontier_reserved", reserved_locations, "RESERVED"),
    ):
        value["frontiers"].append(
            {
                "frontier_id": fid,
                "component_id": "component_main",
                "branch_id": "branch_main",
                "topology": "CYCLIC",
                "lifecycle_state": lifecycle,
                "attachment_location_ids": locations,
                "anchor_attachment_location_id": locations[0],
                "active_yarn_id": "yarn_main",
                "created_by_transition_id": reserve_transition_id,
            }
        )
    value["yarn_paths"][0]["segments"][0]["event_ids"].append(reserve_event_id)
    emitter.frontier_id = "frontier_continuing"
    emitter.live = active_locations

    for course_ordinal, plan in enumerate(plans, start=1):
        course_id = f"course_{course_ordinal:06d}"
        before_frontier = emitter.frontier_id
        before_locations = list(emitter.live)
        member_events = []
        for planned in plan:
            bases = [before_locations[index] for index in planned.base_indices]
            member_events.append(emitter.stitch(course_id, bases, planned.top_count))
        emitter.courses.append(
            {
                "course_id": course_id,
                "ordinal": course_ordinal,
                "component_id": "component_main",
                "branch_id": "branch_main",
                "course_form": "CYCLIC",
                "turn_mode": "CONTINUOUS_SPIRAL",
                "work_direction": "CLOCKWISE",
                "member_event_ids": member_events,
                "input_frontier_ids": [before_frontier],
                "output_frontier_ids": [emitter.frontier_id],
                "derivation_id": emitter.derivation(
                    {"entity_type": "COURSE", "course_id": course_id}
                ),
            }
        )
        value["branches"][0]["course_ids"].append(course_id)
        value["yarn_paths"][0]["segments"][0]["event_ids"].extend(member_events)

    terminal_ids: list[str] = []
    for suffix, input_id, locations in (
        ("active", emitter.frontier_id, list(emitter.live)),
        ("reserved", "frontier_reserved", reserved_locations),
    ):
        index = len(emitter.events)
        operation_id, transition_id, event_id, output_id = (
            f"op_close_{suffix}",
            f"ftrans_{index:06d}",
            f"ev_{index:06d}",
            f"frontier_closed_{suffix}",
        )
        subject = {"entity_type": "CONSTRUCTION_OPERATION", "operation_id": operation_id}
        derivation_id = emitter.derivation(subject)
        value["construction_operations"].append(
            {
                "operation_id": operation_id,
                "operation_type": "CLOSE",
                "input_frontier_ids": [input_id],
                "output_frontier_ids": [output_id],
                "attachment_location_ids": [],
                "join_input_mappings": [],
                "input_yarn_ids": [],
                "output_yarn_ids": [],
                "opening_id": None,
                "design_requirement_id": None,
                "join_method": "NONE",
                "derivation_id": derivation_id,
            }
        )
        value["construction_sequence"].append(
            {
                "event_id": event_id,
                "sequence_index": index,
                "subject_ref": subject,
                "active_yarn_id_before": "yarn_main",
                "active_yarn_id_after": "yarn_main",
                "active_color_id_before": emitter.color_id,
                "active_color_id_after": emitter.color_id,
                "frontier_transition_ids": [transition_id],
            }
        )
        value["frontier_transitions"].append(
            {
                "frontier_transition_id": transition_id,
                "transition_index": index,
                "after_event_index": index,
                "caused_by_subject_ref": subject,
                "transition_type": "CLOSE",
                "input_frontier_ids": [input_id],
                "output_frontier_ids": [output_id],
                "retired_attachment_location_ids": locations,
                "created_attachment_location_ids": [],
                "reserved_attachment_location_ids": [],
                "opening_id": None,
            }
        )
        value["frontiers"].append(
            {
                "frontier_id": output_id,
                "component_id": "component_main",
                "branch_id": "branch_main",
                "topology": "CYCLIC",
                "lifecycle_state": "CLOSED",
                "attachment_location_ids": [],
                "anchor_attachment_location_id": None,
                "active_yarn_id": None,
                "created_by_transition_id": transition_id,
            }
        )
        value["yarn_paths"][0]["segments"][0]["event_ids"].append(event_id)
        terminal_ids.append(output_id)
        if suffix == "active":
            emitter.frontier_id = output_id
            emitter.live = []
    value["branches"][0]["terminal_frontier_ids"] = terminal_ids
    value["components"][0]["terminal_frontier_ids"] = terminal_ids
    value["course_order"] = [course["course_id"] for course in value["courses"]]
    value["attachment_locations"] = emitter.attachments
    value["stitches"] = emitter.stitches
    value["construction_operations"] = emitter.operations
    value["construction_sequence"] = emitter.events
    value["frontiers"] = emitter.frontiers
    value["frontier_transitions"] = emitter.transitions
    value["derivations"] = emitter.derivations
    value["provenance"]["generator"] = {
        "solver_family": "FRONTIER",
        "name": "explicit-reserve-sc",
        "version": "1",
    }
    value["provenance"]["solver_parameters"] = parameters
    value["provenance"]["solver_parameters_sha256"] = parameter_hash
    value["provenance"]["search_budget"] = {
        "budget_type": "CANDIDATE_EVALUATIONS",
        "limit": 1,
        "consumed": 1,
        "exhausted": False,
    }
    if (
        len(value["construction_sequence"]) > max_events
        or len(value["attachment_locations"]) > max_attachment_locations
    ):
        raise GenerationError(GenerationStatus.SEARCH_BUDGET_EXHAUSTED, "reserve.emission_budget")
    for derivation in value["derivations"]:
        derivation["method"] = "FRONTIER_SEARCH"
        derivation["rule_id"] = "frontier.explicit-reserve-sc"
        derivation["rule_version"] = "1"
        derivation["parameter_sha256"] = parameter_hash
    value["provenance"]["software_commit"] = provenance.software_commit
    value["provenance"]["random_seed"] = solver_options["random_seed"]
    value["crochet_ir_id"] = "cir_reserve"
    if (
        len(value["construction_sequence"]) != expected_events
        or len(value["attachment_locations"]) != expected_locations
        or sum(len(f["attachment_location_ids"]) for f in value["frontiers"])
        != expected_frontier_references
    ):
        raise GenerationError(GenerationStatus.INVALID_SOLVER_INPUT, "reserve.accounting_mismatch")
    report = SemanticValidator(
        material_profiles={
            material_value["profile_id"]: material_value,
            (material_value["profile_id"], material_value["revision"]): material_value,
        },
        design_specs={design_value["design_spec_id"]: design_value},
    ).validate_crochet_ir(value)
    if not report.ok:
        raise ArtifactValidationError(report)
    return value
