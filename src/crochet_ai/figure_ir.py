"""Compile a figure part's round schedule into canonical CrochetIR and validate it.

Each part gets its own DesignSpec (its target profile, gauge and colors) and a
complete CrochetIR: magic ring, every single-crochet application with explicit
bases in the exact order of the printed round, color changes between rounds,
and either CLOSE or a declared opening for parts that are sewn on. The
unchanged :class:`SemanticValidator` then replays the whole construction. This
is the structural trust anchor for figure patterns; geometry and physical
acceptance remain NOT_VERIFIED / UNTESTED.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any

import rfc8785

from .canonical import CanonicalProfile, canonical_hash
from .diagnostics import ArtifactValidationError
from .figure_parts import PART_SOLVER_VERSION, PartSchedule
from .prototype_input import PROTOTYPE_VERSION, assemble_request
from .validation import SemanticValidator

_OPENING_REQ = "opening_req_assembly"
_OPENING = "opening_assembly"


def _gauge_observation(per_100mm: float) -> tuple[int, float]:
    """Integer span count over a length that reproduces the entered gauge exactly."""
    if float(per_100mm).is_integer():
        return int(per_100mm), 100.0
    return round(per_100mm * 10), 1000.0


def part_artifacts(
    schedule: PartSchedule,
    part_id: str,
    colors: dict[str, tuple[str, str]],
    *,
    software_commit: str,
    hook_mm: float = 3.0,
    yarn_label: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """DesignSpec and MaterialProfile for one part, built from the prototype's contract."""
    gauge = schedule.gauge
    design, material, _ = assemble_request(
        {
            "prototype_version": PROTOTYPE_VERSION,
            "shape": "sphere",
            "diameter_mm": 40,
            "height_mm": 40,
            "stitches_per_100mm": 25,
            "courses_per_100mm": 28,
            "hook_diameter_mm": min(max(hook_mm, 0.5), 12),
            "yarn_label": (yarn_label or "Figurengarn")[:120],
            "color_hex": "#808080",
            "uncertainty_percent": 10,
        },
        software_commit=software_commit,
        working_tree_dirty=True,
    )
    response = material["calibration_responses"][0]
    stitch_count, stitch_length = _gauge_observation(gauge.stitches_per_100mm)
    row_count, row_length = _gauge_observation(gauge.rows_per_100mm)
    response["observations"][0].update(
        stitch_span_count=stitch_count,
        stitch_span_length_mm=stitch_length,
        course_span_count=row_count,
        course_span_length_mm=row_length,
    )
    response["effective_gauge"] = {
        "effective_stitch_pitch_mm": stitch_length / stitch_count,
        "effective_course_pitch_mm": row_length / row_count,
    }
    response["uncertainty"]["stitch_pitch_standard_uncertainty_mm"] = (
        stitch_length / stitch_count * 0.1
    )
    response["uncertainty"]["course_pitch_standard_uncertainty_mm"] = row_length / row_count * 0.1
    material["profile_id"] = "mp_figure"
    design["material_profile"] = {"binding_type": "INLINE", "profile": deepcopy(material)}

    open_end = schedule.end != "closed"
    points = list(schedule.profile.points)
    axial_extent = max(y for y, _ in points) - min(y for y, _ in points)
    payload: dict[str, Any] = {
        "canonicalization_profile": CanonicalProfile.SURFACE_OF_REVOLUTION_COORDINATES.value,
        "samples": [
            {"sample_index": i, "radius_mm": radius, "axial_mm": axial}
            for i, (axial, radius) in enumerate(points)
        ],
        "start_boundary": {"boundary_type": "CLOSED_POLE"},
        "end_boundary": {"boundary_type": "INTENTIONAL_OPENING",
                         "opening_requirement_id": _OPENING_REQ}
        if open_end
        else {"boundary_type": "CLOSED_POLE"},
    }
    profile = {
        **payload,
        "sha256": canonical_hash(payload, CanonicalProfile.SURFACE_OF_REVOLUTION_COORDINATES),
    }
    design.update(
        schema_version="1.2.0",
        design_spec_id=f"ds_figure_{part_id}",
        dimensions={
            "length_unit": "MILLIMETER",
            "measurements": [
                {"measurement_id": "dim_axial_length", "semantic": "LENGTH",
                 "label": "Axial extent", "value_mm": axial_extent, "tolerance_mm": 0}
            ],
        },
    )
    target = design["target_geometry"]
    target.update(
        primitive="SURFACE_OF_REVOLUTION",
        parameters=[{"parameter": "AXIAL_LENGTH", "measurement_id": "dim_axial_length"}],
        axis_direction=[0, 1, 0],
        radial_profile=profile,
    )
    used = []
    for r in schedule.rounds:
        if r.color not in used:
            used.append(r.color)
    design["colors"] = [
        {"color_id": f"color_{key}", "label": colors[key][0], "srgb_hex": colors[key][1],
         "roles": ["main" if i == 0 else "accent"]}
        for i, key in enumerate(used)
    ]
    operations = ["MAGIC_RING", "CLOSE"]
    if len(used) > 1:
        operations.append("COLOR_CHANGE")
    if open_end:
        operations.append("DECLARE_OPENING")
        design["domain_constraints"]["surface_mode"] = "DECLARED_OPENINGS"
        design["construction_constraints"]["intentional_openings"] = [
            {"opening_requirement_id": _OPENING_REQ, "purpose": "OTHER",
             "boundary_landmark_ids": [], "closure_expectation": "REMAIN_OPEN"}
        ]
    if schedule.stuffing != "none":
        design["domain_constraints"]["stuffing_level"] = (
            "FIRM" if schedule.stuffing == "full" else "LIGHT"
        )
    design["difficulty_constraints"]["allowed_construction_operations"] = operations
    design["interpretation_provenance"]["producer"] = {
        "name": "figure-part-solver", "version": PART_SOLVER_VERSION
    }
    design["interpretation_provenance"]["assumptions"] = [
        {
            "assumption_id": "assumption_figure_part",
            "statement": (
                f"Figure part '{part_id}' ({schedule.shape}, end {schedule.end}); user-entered "
                "gauge, not a calibration result. Target profile is the versioned figure shape."
            ),
            "disposition": "EXPLICIT_PROFILE_DEFAULT",
        }
    ]
    return design, material


class _Ir:
    """Minimal sequential emitter for one cyclic single-crochet component."""

    def __init__(self, parameter_hash: str) -> None:
        self.parameter_hash = parameter_hash
        self.locations: list[dict[str, Any]] = []
        self.stitches: list[dict[str, Any]] = []
        self.operations: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.frontiers: list[dict[str, Any]] = []
        self.transitions: list[dict[str, Any]] = []
        self.derivations: list[dict[str, Any]] = []
        self.courses: list[dict[str, Any]] = []
        self.segments: dict[str, list[dict[str, Any]]] = {}
        self.live: list[str] = []
        self.frontier = ""
        self.yarn: str | None = None
        self.color: str | None = None

    def derivation(self, subject: dict[str, str]) -> str:
        identifier = f"deriv_{len(self.derivations):06d}"
        self.derivations.append(
            {"derivation_id": identifier, "method": "ANALYTIC_RULE",
             "rule_id": "figure.part-schedule", "rule_version": "1",
             "parameter_sha256": self.parameter_hash, "subject_refs": [subject]}
        )
        return identifier

    def new_locations(self, subject: dict[str, str], count: int, kind: str) -> list[str]:
        ids = []
        for ordinal in range(count):
            identifier = f"loc_{len(self.locations):06d}"
            self.locations.append({"attachment_location_id": identifier, "location_type": kind,
                                   "producer_ref": subject, "ordinal_within_producer": ordinal})
            ids.append(identifier)
        return ids

    def event(self, subject: dict[str, str], transition: str | None, yarn_after: str,
              color_after: str) -> str:
        identifier = f"ev_{len(self.events):06d}"
        self.events.append(
            {"event_id": identifier, "sequence_index": len(self.events), "subject_ref": subject,
             "active_yarn_id_before": self.yarn, "active_yarn_id_after": yarn_after,
             "active_color_id_before": self.color, "active_color_id_after": color_after,
             "frontier_transition_ids": [] if transition is None else [transition]}
        )
        # Segment boundaries (ring, color change) are not work events of the segment.
        boundary = subject["entity_type"] == "CONSTRUCTION_OPERATION" and self.operations[-1][
            "operation_type"
        ] in {"MAGIC_RING", "COLOR_CHANGE"}
        if self.yarn is not None and not boundary:
            self.segments[self.yarn][-1]["event_ids"].append(identifier)
        return identifier

    def transition(self, subject: dict[str, str], kind: str, retired: list[str],
                   created: list[str], after: list[str], state: str,
                   opening: str | None = None) -> str:
        index = len(self.transitions)
        tid, fid = f"ftrans_{index:06d}", f"frontier_{index:06d}"
        self.transitions.append(
            {"frontier_transition_id": tid, "transition_index": index,
             "after_event_index": len(self.events), "caused_by_subject_ref": subject,
             "transition_type": kind,
             "input_frontier_ids": [self.frontier] if self.frontier else [],
             "output_frontier_ids": [fid], "retired_attachment_location_ids": retired,
             "created_attachment_location_ids": created, "reserved_attachment_location_ids": [],
             "opening_id": opening}
        )
        self.frontiers.append(
            {"frontier_id": fid, "component_id": "component_main", "branch_id": "branch_main",
             "topology": "CYCLIC", "lifecycle_state": state,
             "attachment_location_ids": list(after),
             "anchor_attachment_location_id": after[0] if after else None,
             "active_yarn_id": self.yarn if state == "ACTIVE" else None,
             "created_by_transition_id": tid}
        )
        self.frontier, self.live = fid, list(after)
        return tid

    def operation(self, kind: str, *, sites: list[str] | None = None,
                  input_yarns: list[str] | None = None, output_yarns: list[str] | None = None,
                  opening: str | None = None,
                  requirement: str | None = None) -> tuple[str, dict[str, str]]:
        identifier = f"op_{len(self.operations):06d}"
        subject = {"entity_type": "CONSTRUCTION_OPERATION", "operation_id": identifier}
        self.operations.append(
            {"operation_id": identifier, "operation_type": kind, "input_frontier_ids": [],
             "output_frontier_ids": [], "attachment_location_ids": sites or [],
             "join_input_mappings": [], "input_yarn_ids": input_yarns or [],
             "output_yarn_ids": output_yarns or [], "opening_id": opening,
             "design_requirement_id": requirement, "join_method": "NONE",
             "derivation_id": self.derivation(subject)}
        )
        return identifier, subject

    def begin_segment(self, yarn: str, operation: str, kind: str) -> None:
        self.segments.setdefault(yarn, []).append(
            {"yarn_segment_id": f"yseg_{operation}", "start_operation_id": operation,
             "start_operation_type": kind, "event_ids": [], "end_operation_id": None,
             "end_operation_type": None}
        )


def compile_part_ir(
    schedule: PartSchedule,
    design: dict[str, Any],
    material: dict[str, Any],
    *,
    software_commit: str,
) -> dict[str, Any]:
    """Emit the exact printed construction; raises on any semantic validation failure."""
    validator = SemanticValidator(
        material_profiles={material["profile_id"]: material,
                           (material["profile_id"], material["revision"]): material},
        design_specs={design["design_spec_id"]: design},
    )
    report = validator.validate_design_spec(design)
    if not report.ok:
        raise ArtifactValidationError(report)
    parameters = sorted(
        [
            ("figure.solver_version", PART_SOLVER_VERSION),
            ("figure.shape", schedule.shape),
            ("figure.end", schedule.end),
            ("figure.counts", ",".join(map(str, schedule.counts))),
            ("figure.stitch_pitch_mm", schedule.gauge.stitch_pitch_mm),
            ("figure.course_pitch_mm", schedule.gauge.course_pitch_mm),
        ]
    )
    parameter_list: list[Any] = [{"name": name, "value": value} for name, value in parameters]
    parameter_hash = sha256(
        b"Crochet.AI\0FIGURE_PART_PARAMETERS_V1\0" + rfc8785.dumps(parameter_list)
    ).hexdigest()
    color_ids = {c["color_id"].removeprefix("color_"): c["color_id"] for c in design["colors"]}
    yarn_of = {key: f"yarn_{key}" for key in color_ids}
    ir = _Ir(parameter_hash)

    first = schedule.rounds[0]
    op, subject = ir.operation("MAGIC_RING", output_yarns=[yarn_of[first.color]])
    sites = ir.new_locations(subject, first.count, "MAGIC_RING_ANCHOR")
    ir.operations[-1]["attachment_location_ids"] = sites
    tid = ir.transition(subject, "CREATE", [], sites, sites, "ACTIVE")
    ir.yarn, ir.color = None, None
    ir.event(subject, tid, yarn_of[first.color], color_ids[first.color])
    ir.yarn, ir.color = yarn_of[first.color], color_ids[first.color]
    ir.frontiers[-1]["active_yarn_id"] = ir.yarn
    ir.operations[-1]["output_frontier_ids"] = [ir.frontier]
    ir.begin_segment(ir.yarn, op, "MAGIC_RING")
    initial = ir.frontier

    for r in schedule.rounds:
        if yarn_of[r.color] != ir.yarn:
            new_yarn, new_color = yarn_of[r.color], color_ids[r.color]
            op, subject = ir.operation("COLOR_CHANGE", input_yarns=[ir.yarn],
                                       output_yarns=[new_yarn])
            ir.segments[ir.yarn][-1].update(end_operation_id=op, end_operation_type="COLOR_CHANGE")
            ir.event(subject, None, new_yarn, new_color)
            ir.yarn, ir.color = new_yarn, new_color
            ir.begin_segment(new_yarn, op, "COLOR_CHANGE")
        course_id = f"course_{r.number:06d}"
        before_frontier = ir.frontier
        bases_available = list(ir.live)
        cursor = 0
        members = []
        for token in r.tokens:
            take = 2 if token == "dec" else 1
            if r.number == 1:
                bases = [bases_available[cursor]]
            else:
                bases = bases_available[cursor : cursor + take]
            cursor += take
            identifier = f"st_{len(ir.stitches):06d}"
            subject = {"entity_type": "STITCH", "stitch_id": identifier}
            tops = ir.new_locations(subject, 2 if token == "inc" else 1, "TOP_LOOP")
            start = ir.live.index(bases[0])
            rotated = ir.live[start:] + ir.live[:start]
            anchor = ir.live[0] if ir.live[0] not in bases else tops[0]
            after = tops + rotated[len(bases):]
            offset = after.index(anchor)
            after = after[offset:] + after[:offset]
            ir.stitches.append(
                {"stitch_id": identifier, "stitch_type": "SINGLE_CROCHET",
                 "shaping": {"inc": "INCREASE", "dec": "DECREASE"}.get(token, "PLAIN"),
                 "base_arity": len(bases), "top_arity": len(tops),
                 "base_attachment_location_ids": bases, "top_attachment_location_ids": tops,
                 "frontier_edit": {"edit_type": "REPLACE_SPAN", "frontier_id": ir.frontier},
                 "yarn_id": ir.yarn, "color_id": ir.color, "course_id": course_id,
                 "derivation_id": ir.derivation(subject)}
            )
            tid = ir.transition(subject, "ADVANCE", bases, tops, after, "ACTIVE")
            members.append(ir.event(subject, tid, ir.yarn, ir.color))
        ir.courses.append(
            {"course_id": course_id, "ordinal": r.number - 1, "component_id": "component_main",
             "branch_id": "branch_main", "course_form": "CYCLIC",
             "turn_mode": "CONTINUOUS_SPIRAL", "work_direction": "CLOCKWISE",
             "member_event_ids": members, "input_frontier_ids": [before_frontier],
             "output_frontier_ids": [ir.frontier],
             "derivation_id": ir.derivation({"entity_type": "COURSE", "course_id": course_id})}
        )

    openings = []
    if schedule.end == "closed":
        op, subject = ir.operation("CLOSE")
        ir.operations[-1]["input_frontier_ids"] = [ir.frontier]
        live = list(ir.live)
        tid = ir.transition(subject, "CLOSE", live, [], [], "CLOSED")
    else:
        op, subject = ir.operation("DECLARE_OPENING", opening=_OPENING, requirement=_OPENING_REQ)
        ir.operations[-1]["input_frontier_ids"] = [ir.frontier]
        live = list(ir.live)
        tid = ir.transition(subject, "DECLARE_OPENING", [], [], live, "DECLARED_OPEN",
                            opening=_OPENING)
        openings.append(
            {"opening_id": _OPENING, "component_id": "component_main",
             "design_requirement_id": _OPENING_REQ, "declared_by_operation_id": op,
             "boundary_attachment_location_ids": live, "purpose": "OTHER",
             "closure_expectation": "REMAIN_OPEN",
             "derivation_id": ir.derivation({"entity_type": "OPENING", "opening_id": _OPENING})}
        )
    ir.operations[-1]["output_frontier_ids"] = [ir.frontier]
    assert ir.yarn is not None and ir.color is not None
    ir.event(subject, tid, ir.yarn, ir.color)

    capabilities = ["CORE_STITCHES_V1", "MAGIC_RING_V1", "MULTI_STITCH_RING_V1"]
    if any(s["shaping"] != "PLAIN" for s in ir.stitches):
        capabilities.append("SHAPING_V1")
    if len(design["colors"]) > 1:
        capabilities.append("COLOR_CHANGES_V1")
    digest = canonical_hash(material, CanonicalProfile.MATERIAL_PROFILE)
    value: dict[str, Any] = {
        "schema_version": "1.1.0",
        "semantics_profile": "CROCHET_CORE_1.1.0",
        "crochet_ir_id": f"cir_figure_{design['design_spec_id'].removeprefix('ds_figure_')}",
        "design_spec_ref": {
            "design_spec_id": design["design_spec_id"],
            "sha256": canonical_hash(design, CanonicalProfile.DESIGN_SPEC, validator=validator),
        },
        "units": {"length": "MILLIMETER", "mass": "GRAM", "angle": "RADIAN"},
        "required_capabilities": capabilities,
        "colors": [{k: c[k] for k in ("color_id", "label", "srgb_hex")} for c in design["colors"]],
        "yarns": [
            {"yarn_id": yarn_of[key], "label": f"Yarn {chr(65 + i)}", "color_id": color_ids[key],
             "material_profile_ref": {"profile_id": material["profile_id"],
                                      "revision": material["revision"], "sha256": digest}}
            for i, key in enumerate(color_ids)
        ],
        "attachment_locations": ir.locations,
        "stitches": ir.stitches,
        "construction_operations": ir.operations,
        "construction_sequence": ir.events,
        "courses": ir.courses,
        "course_order": [c["course_id"] for c in ir.courses],
        "frontiers": ir.frontiers,
        "frontier_transitions": ir.transitions,
        "branches": [
            {"branch_id": "branch_main", "component_id": "component_main",
             "parent_branch_ids": [], "created_by_transition_id": None,
             "course_ids": [c["course_id"] for c in ir.courses],
             "entry_frontier_ids": [initial], "terminal_frontier_ids": [ir.frontier]}
        ],
        "components": [
            {"component_id": "component_main", "branch_ids": ["branch_main"],
             "initial_frontier_ids": [initial], "terminal_frontier_ids": [ir.frontier]}
        ],
        "openings": openings,
        "yarn_paths": [
            {"yarn_path_id": f"ypath_{key}", "yarn_id": yarn_of[key],
             "segments": ir.segments[yarn_of[key]]}
            for key in color_ids
        ],
        "derivations": ir.derivations,
        "provenance": {
            "generator": {"solver_family": "ANALYTIC", "name": "figure-part-solver",
                          "version": "1"},
            "solver_parameters": parameter_list,
            "solver_parameters_sha256": parameter_hash,
            "random_seed": None,
            "search_budget": {"budget_type": "CANDIDATE_EVALUATIONS", "limit": 1,
                              "consumed": 1, "exhausted": False},
            "input_artifacts": [],
            "software_commit": software_commit,
            "canonicalization": {"profile": "CROCHET_IR_CANONICAL_JSON_V1",
                                 "hash_algorithm": "SHA-256"},
        },
    }
    report = validator.validate_crochet_ir(value)
    if not report.ok:
        raise ArtifactValidationError(report)
    return value


def verify_figure(value: object, *, software_commit: str) -> list[dict[str, Any]]:
    """Compile and independently validate every part of a figure spec.

    Returns one record per part; a failure is reported, never repaired.
    """
    from .figure import parse_figure
    from .figure_parts import solve_part

    spec = parse_figure(value)
    records = []
    for part in spec.parts:
        schedule = solve_part(
            part.shape, part.width_mm, part.height_mm, part.end, spec.gauge,
            color=part.color, stripes=part.stripes, stuffing=part.stuffing,
        )
        record: dict[str, Any] = {"part": part.id, "label": part.label,
                                  "stitches": schedule.total_stitches}
        try:
            design, material = part_artifacts(
                schedule, part.id, spec.colors, software_commit=software_commit,
                hook_mm=spec.hook_mm, yarn_label=spec.yarn,
            )
            ir = compile_part_ir(schedule, design, material, software_commit=software_commit)
            validator = SemanticValidator(
                material_profiles={material["profile_id"]: material,
                                   (material["profile_id"], material["revision"]): material},
                design_specs={design["design_spec_id"]: design},
            )
            record.update(
                status="PASS",
                crochet_ir_sha256=canonical_hash(
                    ir, CanonicalProfile.CROCHET_IR, validator=validator
                ),
                operations=sorted({o["operation_type"] for o in ir["construction_operations"]}),
            )
        except ArtifactValidationError as error:
            first = error.report.diagnostics[0] if error.report.diagnostics else None
            record.update(
                status="FAIL",
                reason=None if first is None else f"{first.message_key}: {first.summary}",
            )
        records.append(record)
    return records
