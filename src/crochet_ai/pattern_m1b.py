"""Visible M1B construction language, separate from frozen M1A and external binding."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .diagnostics import ArtifactValidationError, ValidationReport
from .equivalence import semantic_bytes, semantic_projection
from .models import DesignSpec
from .pattern import PatternFormatError, TerminologyProfile, _fail, _label, _validator
from .pattern_context import PatternParseContext, PatternYarnBinding
from .validation import SemanticValidator

PROFILE = "PATTERN_M1B_V1"
HEADER = "CROCHET PATTERN M1B V1"
MAX_BYTES, MAX_LINES = 200_000, 8192
CAPABILITIES = (
    "CORE_STITCHES_V1",
    "SHAPING_V1",
    "MAGIC_RING_V1",
    "MULTI_STITCH_RING_V1",
    "FRONTIER_BRANCHING_V1",
    "COLOR_CHANGES_V1",
    "SEWN_JOINS_V1",
)
TERMS = {
    "US_EN": ("ch", "sl st", "sc", "hdc", "dc", "tr"),
    "UK_EN": ("ch", "sl st", "dc", "htr", "tr", "dtr"),
    "DE_DE": ("Lm", "Km", "fM", "hStb", "Stb", "DStb"),
}
FAMILIES = (
    "CHAIN",
    "SLIP_STITCH",
    "SINGLE_CROCHET",
    "HALF_DOUBLE_CROCHET",
    "DOUBLE_CROCHET",
    "TREBLE_CROCHET",
)
LAYOUT = {
    "Yarn": ("color",),
    "Piece": ("branches", "starts", "finishes"),
    "Branch": ("piece", "parents", "created", "courses", "enters", "finishes"),
    "Course": (
        "number",
        "piece",
        "branch",
        "form",
        "turn",
        "direction",
        "starts",
        "finishes",
        "steps",
    ),
    "Make a magic ring": ("yarn", "sites", "output"),
    "Start yarn": ("yarn", "sites", "output"),
    "Reattach yarn": ("yarn", "on", "at", "output"),
    "Change yarn": ("from", "to"),
    "Cut yarn": ("yarn",),
    "Reserve": ("on", "outputs"),
    "Split": ("on", "outputs"),
    "Join": ("inputs", "method", "output"),
    "Close": ("on", "output"),
    "Leave open": ("on", "requirement", "purpose", "expectation", "opening", "output"),
    "Work": ("bases", "tops", "on", "gap", "output", "course", "total"),
}


@dataclass(frozen=True, slots=True)
class Instruction:
    label: str
    action: str
    values: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PatternM1BAst:
    terminology: TerminologyProfile
    core: str
    capabilities: tuple[str, ...]
    instructions: tuple[Instruction, ...]


def fail(key: str, detail: str = "Invalid M1B construction") -> PatternFormatError:
    return _fail("", "m1b." + key, detail)


def symbol(value: str, category: str) -> str:
    prefixes = {
        "Piece": "component",
        "Branch": "branch",
        "Course": "course",
        "Boundary": "frontier",
        "Marker": "loc",
        "Step": "ev",
        "Yarn": "yarn",
        "Color": "color",
        "Opening": "opening",
    }
    if (
        category not in prefixes
        or re.fullmatch(re.escape(category) + r" [A-Z]{1,4}", value) is None
    ):
        raise fail("symbol", f"Expected a visible {category} label")
    return prefixes[category] + "_m1b_" + value.split(" ")[1]


def items(value: str, category: str) -> list[str]:
    parts = [] if value == "none" else value.split(", ")
    if len(parts) != len(set(parts)):
        raise fail("duplicate", "Repeated visible reference")
    return [symbol(part, category) for part in parts]


def boundary(value: str) -> tuple[str, str, str, str, str | None, str | None]:
    match = re.fullmatch(
        r"(Boundary [A-Z]{1,4}) \((Piece [A-Z]{1,4})/(Branch [A-Z]{1,4})/"
        r"(cyclic|linear)/(Marker [A-Z]{1,4}|none)/(Yarn [A-Z]{1,4}|none)\)",
        value,
    )
    if match is None:
        raise fail("boundary", "Boundary needs piece, branch, topology, anchor and yarn")
    fid, piece, branch, topology, anchor, yarn = match.groups()
    return (
        symbol(fid, "Boundary"),
        symbol(piece, "Piece"),
        symbol(branch, "Branch"),
        topology.upper(),
        None if anchor == "none" else symbol(anchor, "Marker"),
        None if yarn == "none" else symbol(yarn, "Yarn"),
    )


def render_ast(ast: PatternM1BAst) -> str:
    if (
        type(ast) is not PatternM1BAst
        or not isinstance(ast.terminology, TerminologyProfile)
        or type(ast.core) is not str
        or ast.core not in {"1.0.0", "1.1.0"}
        or type(ast.capabilities) is not tuple
        or len(ast.capabilities) > len(CAPABILITIES)
        or any(type(value) is not str or value not in CAPABILITIES for value in ast.capabilities)
        or type(ast.instructions) is not tuple
        or len(ast.instructions) > MAX_LINES
    ):
        raise fail("ast_type")
    characters = 0
    for record in ast.instructions:
        if (
            type(record) is not Instruction
            or type(record.label) is not str
            or type(record.action) is not str
            or type(record.values) is not tuple
            or len(record.values) > 10
            or any(type(value) is not str for value in record.values)
        ):
            raise fail("ast_record_type")
        characters += len(record.label) + len(record.action) + sum(map(len, record.values))
        if characters > MAX_BYTES:
            raise fail("ast_size")
    lines = [
        HEADER,
        "Terminology: " + ast.terminology.value,
        "Core: " + ast.core,
        "Skills: "
        + ", ".join(c.replace("_V1", "").lower().replace("_", " ") for c in ast.capabilities),
        "",
        "Instructions",
    ]
    for record in ast.instructions:
        kind = "Work" if record.action.startswith("Work ") else record.action
        if kind not in LAYOUT or len(record.values) != len(LAYOUT[kind]):
            raise fail("record")
        parts = [record.label + ": " + record.action]
        parts.extend(
            name + " " + val for name, val in zip(LAYOUT[kind], record.values, strict=True)
        )
        lines.append("; ".join(parts) + ".")
    return "\n".join([*lines, "", "END", ""])


def parse_pattern_m1b_text(text: str) -> PatternM1BAst:
    if not isinstance(text, str):
        raise fail("text")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise fail("unicode") from error
    if size > MAX_BYTES or text.count("\n") > MAX_LINES:
        raise fail("budget", "M1B exceeds its text budget")
    lines = text.split("\n")
    if (
        len(lines) < 10
        or lines[0] != HEADER
        or lines[4:6] != ["", "Instructions"]
        or lines[-3:] != ["", "END", ""]
        or "\r" in text
    ):
        raise fail("envelope")
    try:
        terminology = TerminologyProfile(lines[1].removeprefix("Terminology: "))
    except ValueError as error:
        raise fail("terminology") from error
    if not lines[1].startswith("Terminology: ") or lines[2] not in {"Core: 1.0.0", "Core: 1.1.0"}:
        raise fail("core")
    cap_map = {c.replace("_V1", "").lower().replace("_", " "): c for c in CAPABILITIES}
    try:
        caps = tuple(cap_map[c] for c in lines[3].removeprefix("Skills: ").split(", "))
    except KeyError as error:
        raise fail("skills") from error
    if not lines[3].startswith("Skills: ") or len(set(caps)) != len(caps):
        raise fail("skills")
    records = []
    seen: set[str] = set()
    for line in lines[6:-3]:
        if not line.endswith("."):
            raise fail("syntax")
        parts = line[:-1].split("; ")
        head = parts[0].split(": ")
        if len(head) != 2 or head[0] in seen:
            raise fail("label")
        label, action = head
        category = label.split(" ")[0]
        symbol(label, category if category in {"Yarn", "Piece", "Branch", "Course"} else "Step")
        kind = "Work" if action.startswith("Work ") else action
        if category in {"Yarn", "Piece", "Branch", "Course"} and action != category:
            raise fail("declaration")
        if category == "Step" and kind in {"Yarn", "Piece", "Branch", "Course"}:
            raise fail("step")
        keys = LAYOUT.get(kind)
        if keys is None or len(parts) != len(keys) + 1:
            raise fail("syntax")
        values = []
        for key, val in zip(keys, parts[1:], strict=True):
            if not val.startswith(key + " ") or not val[len(key) + 1 :]:
                raise fail("syntax")
            values.append(val[len(key) + 1 :])
        seen.add(label)
        records.append(Instruction(label, action, tuple(values)))
    ast = PatternM1BAst(terminology, lines[2][6:], caps, tuple(records))
    from .pattern_m1b_bind import replay

    unbound = replay(ast)
    # External identities are intentionally absent from text-only admission.
    # Every other existing structural diagnostic still rejects the text.
    report = SemanticValidator().validate_crochet_ir(unbound)
    internal = tuple(
        diagnostic
        for diagnostic in report.diagnostics
        if diagnostic.message_key
        not in {"design_spec_ref.unresolved", "material_profile_ref.unresolved"}
    )
    if internal:
        raise PatternFormatError(ValidationReport.from_iterable(internal))
    return ast


def _name(identifier: str | None) -> str:
    if identifier is None:
        return "none"
    prefix, ordinal = identifier.rsplit("_", 1)
    names = {
        "component": "Piece",
        "branch": "Branch",
        "course": "Course",
        "frontier": "Boundary",
        "location": "Marker",
        "event": "Step",
        "yarn": "Yarn",
        "color": "Color",
        "opening": "Opening",
    }
    return _label(int(ordinal), names[prefix])


def _names(values: list[str]) -> str:
    return ", ".join(_name(v) for v in values) or "none"


def export_pattern_m1b(
    value: dict[str, Any], terminology: TerminologyProfile, *, validator: SemanticValidator
) -> str:
    if not isinstance(terminology, TerminologyProfile):
        raise fail("terminology")
    p = semantic_projection(value, validator=validator)
    original_operations = {op["operation_id"]: op for op in value["construction_operations"]}
    external_requirements = {}
    for original_event in value["construction_sequence"]:
        ref = original_event["subject_ref"]
        if ref["entity_type"] == "CONSTRUCTION_OPERATION":
            op = original_operations[ref["operation_id"]]
            if op["operation_type"] == "DECLARE_OPENING":
                external_requirements[original_event["sequence_index"]] = op[
                    "design_requirement_id"
                ]
    records: list[Instruction] = []

    def add(label: str, action: str, *values: str) -> None:
        records.append(Instruction(label, action, tuple(values)))

    fs = {f["frontier_id"]: f for f in p["frontiers"]}
    steps = {
        t["frontier_transition_id"]: _name("event_" + str(t["after_event_index"]))
        for t in p["frontier_transitions"]
    }

    def desc(fid: str) -> str:
        f = fs[fid]
        return (
            _name(fid)
            + " ("
            + "/".join(
                (
                    _name(f["component_id"]),
                    _name(f["branch_id"]),
                    f["topology"].lower(),
                    _name(f["anchor_attachment_location_id"]),
                    _name(f["active_yarn_id"]),
                )
            )
            + ")"
        )

    for yarn in p["yarns"]:
        add(_name(yarn["yarn_id"]), "Yarn", _name(yarn["color_id"]))
    for piece in p["components"]:
        add(
            _name(piece["component_id"]),
            "Piece",
            _names(piece["branch_ids"]),
            _names(piece["initial_frontier_ids"]),
            _names(piece["terminal_frontier_ids"]),
        )
    for b in p["branches"]:
        add(
            _name(b["branch_id"]),
            "Branch",
            _name(b["component_id"]),
            _names(b["parent_branch_ids"]),
            steps[b["created_by_transition_id"]] if b["created_by_transition_id"] else "start",
            _names(b["course_ids"]),
            _names(b["entry_frontier_ids"]),
            _names(b["terminal_frontier_ids"]),
        )
    for c in p["courses"]:
        add(
            _name(c["course_id"]),
            "Course",
            str(c["ordinal"] + 1),
            _name(c["component_id"]),
            _name(c["branch_id"]),
            c["course_form"].lower(),
            c["turn_mode"].lower().replace("_", " "),
            c["work_direction"].lower(),
            _names(c["input_frontier_ids"]),
            _names(c["output_frontier_ids"]),
            _names(c["member_event_ids"]),
        )
    ts = {t["frontier_transition_id"]: t for t in p["frontier_transitions"]}
    st = {s["stitch_id"]: s for s in p["stitches"]}
    ops = {o["operation_id"]: o for o in p["construction_operations"]}
    openings = {o["opening_id"]: o for o in p["openings"]}
    top_ids = {
        location["attachment_location_id"]
        for location in p["attachment_locations"]
        if location["location_type"] == "TOP_LOOP"
    }
    for event in p["construction_sequence"]:
        label, ref = _name(event["event_id"]), event["subject_ref"]
        tlist = event["frontier_transition_ids"]
        if len(tlist) > 1:
            raise fail("multiple_transitions")
        t = ts[tlist[0]] if tlist else None
        if ref["entity_type"] == "STITCH":
            s = st[ref["stitch_id"]]
            if t is None:
                raise fail("transition")
            edit = s["frontier_edit"]
            gap = (
                ", ".join(_name(edit[n]) for n in ("left_location_id", "right_location_id"))
                if edit["edit_type"] == "INSERT_AT_GAP"
                else "none"
            )
            family = TERMS[terminology.value][FAMILIES.index(s["stitch_type"])]
            suffix = "" if s["shaping"] == "PLAIN" else " " + s["shaping"].lower()
            out = t["output_frontier_ids"][0]
            total = sum(loc in top_ids for loc in fs[out]["attachment_location_ids"])
            add(
                label,
                "Work 1 " + family + suffix,
                _names(s["base_attachment_location_ids"]),
                _names(s["top_attachment_location_ids"]),
                _name(edit["frontier_id"]),
                gap,
                desc(out),
                _name(s["course_id"]),
                str(total),
            )
            continue
        op = ops[ref["operation_id"]]
        kind = op["operation_type"]
        ins, outs = op["input_frontier_ids"], op["output_frontier_ids"]
        if kind in {"MAGIC_RING", "ATTACH"}:
            if kind == "ATTACH" and ins:
                add(
                    label,
                    "Reattach yarn",
                    _names(op["output_yarn_ids"]),
                    _names(ins),
                    _names(op["attachment_location_ids"]),
                    desc(outs[0]),
                )
            else:
                add(
                    label,
                    "Make a magic ring" if kind == "MAGIC_RING" else "Start yarn",
                    _names(op["output_yarn_ids"]),
                    _names(op["attachment_location_ids"]),
                    desc(outs[0]),
                )
        elif kind in {"COLOR_CHANGE", "CUT_YARN"}:
            add(
                label,
                "Change yarn" if kind == "COLOR_CHANGE" else "Cut yarn",
                _names(op["input_yarn_ids"]),
                *([_names(op["output_yarn_ids"])] if kind == "COLOR_CHANGE" else []),
            )
        elif kind in {"RESERVE", "SPLIT"}:
            outputs = " | ".join(
                desc(fid)
                + " using "
                + _names(fs[fid]["attachment_location_ids"])
                + " as "
                + fs[fid]["lifecycle_state"].lower()
                for fid in outs
            )
            add(label, "Reserve" if kind == "RESERVE" else "Split", _names(ins), outputs)
        elif kind == "JOIN":
            mappings = " | ".join(
                _name(m["input_frontier_id"])
                + " "
                + m["orientation"].lower()
                + " using "
                + _names(m["consumed_attachment_location_ids"])
                for m in op["join_input_mappings"]
            )
            add(label, "Join", mappings, op["join_method"].lower(), desc(outs[0]))
        elif kind == "CLOSE":
            add(label, "Close", _names(ins), desc(outs[0]))
        elif kind == "DECLARE_OPENING":
            opening = openings[op["opening_id"]]
            add(
                label,
                "Leave open",
                _names(ins),
                external_requirements[event["sequence_index"]],
                opening["purpose"].lower().replace("_", " "),
                opening["closure_expectation"].lower().replace("_", " "),
                _name(op["opening_id"]),
                desc(outs[0]),
            )
        else:
            raise fail("operation")
    ast = PatternM1BAst(
        terminology, p["schema_version"], tuple(p["required_capabilities"]), tuple(records)
    )
    text = render_ast(ast)
    parse_pattern_m1b_text(text)
    return text


def bind_pattern_m1b_semantics(ast: PatternM1BAst, context: PatternParseContext) -> dict[str, Any]:
    from .pattern_m1b_bind import replay

    if not isinstance(ast, PatternM1BAst) or not isinstance(context, PatternParseContext):
        raise fail("context")
    if type(context.design_spec) is not dict or type(context.yarn_bindings) is not tuple:
        raise fail("context_type")
    identities: dict[tuple[str, int], dict[str, Any]] = {}
    for binding in context.yarn_bindings:
        if (
            type(binding) is not PatternYarnBinding
            or type(binding.symbol) is not str
            or type(binding.material_profile) is not dict
            or type(binding.color_label) is not str
            or type(binding.srgb_hex) is not str
        ):
            raise fail("binding_type")
        report = SemanticValidator().validate_material_profile(binding.material_profile)
        if not report.ok:
            raise PatternFormatError(report)
        material = binding.material_profile
        identity = (material["profile_id"], material["revision"])
        if identity in identities and identities[identity] != material:
            raise fail("material_identity_conflict")
        identities[identity] = material
    DesignSpec.from_dict(context.design_spec)
    admitted = parse_pattern_m1b_text(render_ast(ast))
    value = replay(admitted, context)
    report = _validator(context).validate_crochet_ir(value)
    if not report.ok:
        raise PatternFormatError(report)
    return value


def parse_pattern_m1b(text: str, *, context: PatternParseContext) -> dict[str, Any]:
    return bind_pattern_m1b_semantics(parse_pattern_m1b_text(text), context)


def verify_semantic_round_trip_m1b(
    value: dict[str, Any],
    terminology: TerminologyProfile,
    *,
    context: PatternParseContext,
    validator: SemanticValidator,
) -> ValidationReport:
    try:
        text = export_pattern_m1b(value, terminology, validator=validator)
        parsed = parse_pattern_m1b(text, context=context)
        if semantic_bytes(value, validator=validator) != semantic_bytes(
            parsed, validator=_validator(context)
        ):
            raise fail("semantic_mismatch")
    except ArtifactValidationError as error:
        return error.report
    return ValidationReport()
