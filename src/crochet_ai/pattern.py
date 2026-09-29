# ruff: noqa: E501, E701, E702
"""Payload-free, controlled Pattern V1A grammar.

Only the non-branching construction core is deliberately implemented here.
The parser produces typed text facts; the binder creates a fresh CrochetIR
using external material identities only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal, cast

from .canonical import CanonicalProfile, canonical_hash
from .certification import CertificationManifest
from .diagnostics import ArtifactValidationError, Diagnostic, FailureCode, ValidationReport
from .equivalence import semantic_bytes, semantic_hash
from .pattern_context import PatternParseContext
from .validation import SemanticValidator

PATTERN_FORMAT_VERSION = 1
_HEADER = "CROCHET PATTERN V1"
_TERMS = {"US": "US_EN", "UK": "UK_EN", "DE": "DE_DE"}
_WORDS = {"US_EN": ("sc", "ch"), "UK_EN": ("dc", "ch"), "DE_DE": ("fM", "Lm")}


class TerminologyProfile(StrEnum):
    US_EN = "US_EN"
    UK_EN = "UK_EN"
    DE_DE = "DE_DE"


@dataclass(frozen=True, slots=True)
class PatternCommand:
    kind: Literal["MAGIC_RING", "ATTACH", "CHAIN", "SC", "COLOR_CHANGE", "CLOSE"]
    yarn: str | None = None
    marker: str | None = None
    shaping: Literal["PLAIN", "INCREASE", "DECREASE"] | None = None
    total: int | None = None


@dataclass(frozen=True, slots=True)
class PatternCourse:
    label: str
    form: Literal["LINEAR", "CYCLIC"]
    anchor: str | None
    commands: tuple[PatternCommand, ...]


@dataclass(frozen=True, slots=True)
class UnresolvedPatternSemantics:
    terminology: TerminologyProfile
    materials: tuple[str, ...]
    leading: tuple[PatternCommand, ...]
    courses: tuple[PatternCourse, ...]
    trailing: tuple[PatternCommand, ...]


@dataclass(frozen=True, slots=True)
class PatternDocument:
    format_version: int
    terminology: TerminologyProfile
    unresolved: UnresolvedPatternSemantics


class PatternFormatError(ArtifactValidationError):
    pass


def _fail(text: str, key: str, summary: str, observed: object = None) -> PatternFormatError:
    return PatternFormatError(ValidationReport.from_iterable([Diagnostic(
        code=FailureCode.EXPORT_ROUNDTRIP, gate="V9", message_key=key, summary=summary,
        artifact_hash=sha256(text.encode()).hexdigest(), observed=observed,
        implementation_version="pattern-v1a",
    )]))


def _term(profile: TerminologyProfile) -> str:
    return {"US_EN": "US", "UK_EN": "UK", "DE_DE": "DE"}[profile.value]


def _label(index: int, prefix: str) -> str:
    return f"{prefix} {chr(65 + index)}"


def _validator(context: PatternParseContext) -> SemanticValidator:
    profiles: dict[str | tuple[str, int], dict[str, Any]] = {
        (str(item.material_profile["profile_id"]), int(item.material_profile["revision"])): item.material_profile
        for item in context.yarn_bindings
    }
    return SemanticValidator(design_specs={context.design_spec["design_spec_id"]: context.design_spec}, material_profiles=profiles)


def _command_line(command: PatternCommand, profile: TerminologyProfile) -> str:
    sc, chain = _WORDS[profile.value]
    if command.kind == "MAGIC_RING": return f"Make a magic ring with {command.yarn}; set {command.marker}."
    if command.kind == "ATTACH": return f"Start {command.yarn} at {command.marker}."
    if command.kind == "COLOR_CHANGE": return f"Change to {command.yarn}."
    if command.kind == "CLOSE": return "Close work."
    if command.kind == "CHAIN": return f"Work 1 {chain}. ({command.total})"
    suffix = {"PLAIN": "", "INCREASE": " increase", "DECREASE": " decrease"}[command.shaping or "PLAIN"]
    return f"Work 1 {sc}{suffix}. ({command.total})"


def render_pattern(document: PatternDocument) -> str:
    unresolved = document.unresolved
    lines = [_HEADER, f"Terminology: {_term(unresolved.terminology)}", "", "Materials"]
    lines += [f"{item}: external material binding." for item in unresolved.materials]
    lines += ["", "Instructions"]
    lines += [_command_line(item, unresolved.terminology) for item in unresolved.leading]
    for course in unresolved.courses:
        extra = f", anchor {course.anchor}" if course.form == "CYCLIC" else ""
        lines.append(f"{course.label} ({course.form.lower()}{extra}):")
        lines += [_command_line(item, unresolved.terminology) for item in course.commands]
    lines += [_command_line(item, unresolved.terminology) for item in unresolved.trailing]
    return "\n".join([*lines, "", "END"]) + "\n"


def _assert_exportable(value: dict[str, Any]) -> None:
    allowed = {"MAGIC_RING", "ATTACH", "COLOR_CHANGE", "CLOSE"}
    if len(value["components"]) != 1 or len(value["branches"]) != 1 or any(item["operation_type"] not in allowed for item in value["construction_operations"]):
        raise ValueError("M1A supports only one non-branching component")
    if any(item["stitch_type"] not in {"CHAIN", "SINGLE_CROCHET"} or item["shaping"] not in {"PLAIN", "INCREASE", "DECREASE"} for item in value["stitches"]):
        raise ValueError("M1A supports only chain and V1 single crochet")


def _from_ir(value: dict[str, Any], terminology: TerminologyProfile) -> UnresolvedPatternSemantics:
    _assert_exportable(value)
    yarn_names = {item["yarn_id"]: _label(index, "Yarn") for index, item in enumerate(value["yarns"])}
    locations = {item["attachment_location_id"]: item for item in value["attachment_locations"]}
    marker_names = {item: _label(index, "Marker") for index, item in enumerate(locations)}
    frontiers = {item["frontier_id"]: item for item in value["frontiers"]}
    transitions = {item["frontier_transition_id"]: item for item in value["frontier_transitions"]}
    stitches = {item["stitch_id"]: item for item in value["stitches"]}; ops = {item["operation_id"]: item for item in value["construction_operations"]}
    courses_by_id = {item["course_id"]: item for item in value["courses"]}
    course_commands: dict[str, list[PatternCommand]] = {item["course_id"]: [] for item in value["courses"]}
    leading: list[PatternCommand] = []; trailing: list[PatternCommand] = []
    seen_stitch = False
    for event in sorted(value["construction_sequence"], key=lambda item: item["sequence_index"]):
        subject = event["subject_ref"]
        if subject["entity_type"] == "STITCH":
            seen_stitch = True; stitch = stitches[subject["stitch_id"]]
            transition = transitions[event["frontier_transition_ids"][0]]; output = frontiers[transition["output_frontier_ids"][0]]
            total = sum(locations[item]["location_type"] == "TOP_LOOP" for item in output["attachment_location_ids"])
            course_commands[stitch["course_id"]].append(PatternCommand("CHAIN" if stitch["stitch_type"] == "CHAIN" else "SC", shaping=stitch["shaping"], total=total)); continue
        operation = ops[subject["operation_id"]]; typ = operation["operation_type"]
        if typ in {"MAGIC_RING", "ATTACH"}:
            command = PatternCommand(typ, yarn_names[operation["output_yarn_ids"][0]], marker_names[operation["attachment_location_ids"][0]])
        elif typ == "COLOR_CHANGE": command = PatternCommand("COLOR_CHANGE", yarn_names[operation["output_yarn_ids"][0]])
        else: command = PatternCommand("CLOSE")
        (trailing if seen_stitch else leading).append(command)
    rendered_courses: list[PatternCourse] = []
    for index, course_id in enumerate(value["course_order"]):
        course = courses_by_id[course_id]; input_frontier = frontiers[course["input_frontier_ids"][0]]
        rendered_courses.append(PatternCourse(f"{'Round' if course['course_form'] == 'CYCLIC' else 'Row'} {index + 1}", course["course_form"], marker_names[input_frontier["anchor_attachment_location_id"]] if course["course_form"] == "CYCLIC" else None, tuple(course_commands[course_id])))
    return UnresolvedPatternSemantics(terminology, tuple(yarn_names.values()), tuple(leading), tuple(rendered_courses), tuple(trailing))


def build_pattern_document(value: dict[str, Any], terminology: TerminologyProfile, *, validator: SemanticValidator | None = None) -> PatternDocument:
    report = (validator or SemanticValidator()).validate_crochet_ir(value)
    if not report.ok: raise PatternFormatError(report)
    return PatternDocument(PATTERN_FORMAT_VERSION, terminology, _from_ir(value, terminology))


def export_pattern(value: dict[str, Any], terminology: TerminologyProfile, *, validator: SemanticValidator | None = None) -> str:
    return render_pattern(build_pattern_document(value, terminology, validator=validator))


_MATERIAL = re.compile(r"^(Yarn [A-Z]): external material binding\.$")
_COURSE = re.compile(r"^(Round|Row) ([1-9][0-9]*) \((cyclic|linear)(?:, anchor (Marker [A-Z]))?\):$")
_MAGIC = re.compile(r"^Make a magic ring with (Yarn [A-Z]); set (Marker [A-Z])\.$")
_ATTACH = re.compile(r"^Start (Yarn [A-Z]) at (Marker [A-Z])\.$")
_COLOR = re.compile(r"^Change to (Yarn [A-Z])\.$")
_CHAIN = re.compile(r"^Work 1 (ch|Lm)\. \(([0-9]+)\)$")
_SC = re.compile(r"^Work 1 (sc|dc|fM)(?: (increase|decrease))?\. \(([0-9]+)\)$")


def parse_pattern_text(text: str) -> UnresolvedPatternSemantics:
    if len(text.encode()) > 100_000 or len(text.splitlines()) > 2_000 or text != "\n".join(text.splitlines()) + "\n": raise _fail(text, "pattern.envelope", "Pattern must use bounded canonical LF text")
    lines = text.splitlines()
    if len(lines) < 8 or lines[0] != _HEADER or not lines[1].startswith("Terminology: ") or lines[2:4] != ["", "Materials"]: raise _fail(text, "pattern.envelope", "Pattern V1A header is malformed")
    try: terminology = TerminologyProfile(_TERMS[lines[1][13:]])
    except KeyError as error: raise _fail(text, "pattern.terminology", "Unsupported terminology") from error
    index = 4; materials: list[str] = []
    while index < len(lines) and lines[index]:
        match = _MATERIAL.fullmatch(lines[index])
        if not match or match.group(1) in materials: raise _fail(text, "pattern.material", "Malformed material declaration")
        materials.append(match.group(1)); index += 1
    if not materials or lines[index:index + 2] != ["", "Instructions"]: raise _fail(text, "pattern.material", "Materials and instructions are required")
    index += 2; leading: list[PatternCommand] = []; trailing: list[PatternCommand] = []; courses: list[PatternCourse] = []; active: list[PatternCommand] | None = None; course_meta: tuple[str, Literal["LINEAR", "CYCLIC"], str | None] | None = None
    while index < len(lines) and lines[index]:
        line = lines[index]
        match = _COURSE.fullmatch(line)
        if match:
            title, number, form, anchor = match.groups()
            if (title == "Round") != (form == "cyclic") or (form == "cyclic") != (anchor is not None): raise _fail(text, "pattern.course", "Course form requires its matching visible anchor")
            if course_meta is not None: courses.append(PatternCourse(*course_meta, tuple(active or [])))
            course_meta = (f"{title} {number}", "CYCLIC" if form == "cyclic" else "LINEAR", anchor); active = []; index += 1; continue
        if (match := _MAGIC.fullmatch(line)): command = PatternCommand("MAGIC_RING", match.group(1), match.group(2))
        elif (match := _ATTACH.fullmatch(line)): command = PatternCommand("ATTACH", match.group(1), match.group(2))
        elif (match := _COLOR.fullmatch(line)): command = PatternCommand("COLOR_CHANGE", match.group(1))
        elif line == "Close work.": command = PatternCommand("CLOSE")
        elif (match := _CHAIN.fullmatch(line)):
            if match.group(1) != _WORDS[terminology.value][1]: raise _fail(text, "pattern.terminology", "Wrong chain terminology")
            command = PatternCommand("CHAIN", shaping="PLAIN", total=int(match.group(2)))
        elif (match := _SC.fullmatch(line)):
            if match.group(1) != _WORDS[terminology.value][0]: raise _fail(text, "pattern.terminology", "Wrong single-crochet terminology")
            shaping = {None: "PLAIN", "increase": "INCREASE", "decrease": "DECREASE"}[match.group(2)]
            command = PatternCommand("SC", shaping=cast(Literal["PLAIN", "INCREASE", "DECREASE"], shaping), total=int(match.group(3)))
        else: raise _fail(text, "pattern.syntax", "Unsupported Pattern V1A syntax", line)
        if command.kind in {"SC", "CHAIN"} and active is None: raise _fail(text, "pattern.course", "Stitches require Row or Round")
        if command.kind not in {"SC", "CHAIN"} and active is not None:
            assert course_meta is not None
            courses.append(PatternCourse(*course_meta, tuple(active)))
            active = None; course_meta = None
        (active if active is not None else (leading if not courses else trailing)).append(command); index += 1
    if course_meta is not None: courses.append(PatternCourse(*course_meta, tuple(active or [])))
    if lines[index:] != ["", "END"]: raise _fail(text, "pattern.envelope", "Pattern requires final blank line and END")
    return UnresolvedPatternSemantics(terminology, tuple(materials), tuple(leading), tuple(courses), tuple(trailing))


class _Builder:
    def __init__(self, unresolved: UnresolvedPatternSemantics, context: PatternParseContext) -> None:
        self.u, self.c = unresolved, context; self.bindings = {item.symbol: item for item in context.yarn_bindings}
        if len(self.bindings) != len(context.yarn_bindings) or set(self.bindings) != set(unresolved.materials): raise ValueError("ParseContext must bind exactly visible materials")
        self.colors: list[dict[str, Any]]=[]; self.yarns: list[dict[str, Any]]=[]; self.loc: list[dict[str, Any]]=[]; self.st: list[dict[str, Any]]=[]; self.ops: list[dict[str, Any]]=[]; self.events: list[dict[str, Any]]=[]; self.trans: list[dict[str, Any]]=[]; self.frontiers: list[dict[str, Any]]=[]; self.courses: list[dict[str, Any]]=[]; self.deriv: list[dict[str, Any]]=[]
        self.yarn: dict[str,str]={}; self.color: dict[str,str]={}; self.live: list[str]=[]; self.frontier: str|None=None; self.topology: str|None=None; self.current: str|None=None; self.current_color: str|None=None; self.initial: str|None=None; self.start: dict[str,tuple[str,str]]={}; self.work: dict[str,list[str]]={}
        for index,symbol in enumerate(unresolved.materials):
            b=self.bindings[symbol]; cid=f"color_{index}"; yid=f"yarn_{index}"; self.yarn[symbol]=yid; self.color[symbol]=cid; self.colors.append({"color_id":cid,"label":b.color_label,"srgb_hex":b.srgb_hex}); self.yarns.append({"yarn_id":yid,"material_profile_ref":{"profile_id":b.material_profile["profile_id"],"revision":b.material_profile["revision"],"sha256":canonical_hash(b.material_profile,CanonicalProfile.MATERIAL_PROFILE)},"color_id":cid,"label":symbol}); self.work[yid]=[]

    def d(self, subject:dict[str,str])->str:
        x=f"deriv_pattern_{len(self.deriv)}"; self.deriv.append({"derivation_id":x,"method":"MANUAL_BOOTSTRAP","rule_id":"pattern.v1a","rule_version":"1","parameter_sha256":"0"*64,"subject_refs":[subject]}); return x
    def event(self,subject:dict[str,str],trans:str|None,before:str|None,after:str|None,bcolor:str|None,acolor:str|None)->str:
        x=f"ev_pattern_{len(self.events)}"; self.events.append({"event_id":x,"sequence_index":len(self.events),"subject_ref":subject,"active_yarn_id_before":before,"active_yarn_id_after":after,"active_color_id_before":bcolor,"active_color_id_after":acolor,"frontier_transition_ids":[] if trans is None else [trans]}); return x
    def frontier_obj(self,locations:list[str],state:str,transition:str,yarn:str|None)->str:
        x=f"frontier_pattern_{len(self.frontiers)}"; self.frontiers.append({"frontier_id":x,"component_id":"component_0","branch_id":"branch_0","topology":self.topology,"lifecycle_state":state,"attachment_location_ids":locations,"anchor_attachment_location_id":locations[0] if self.topology=="CYCLIC" and locations else None,"active_yarn_id":yarn if state=="ACTIVE" else None,"created_by_transition_id":transition}); return x
    def transition(self,subject:dict[str,str],kind:str,inputs:list[str],retired:list[str],created:list[str])->str:
        x=f"ftrans_pattern_{len(self.trans)}"; self.trans.append({"frontier_transition_id":x,"transition_index":len(self.trans),"after_event_index":len(self.events),"caused_by_subject_ref":subject,"transition_type":kind,"input_frontier_ids":inputs,"output_frontier_ids":[],"retired_attachment_location_ids":retired,"created_attachment_location_ids":created,"reserved_attachment_location_ids":[],"opening_id":None}); return x
    def location(self,typ:str,subject:dict[str,str],ordinal:int)->str:
        x=f"loc_pattern_{len(self.loc)}"; self.loc.append({"attachment_location_id":x,"location_type":typ,"producer_ref":subject,"ordinal_within_producer":ordinal}); return x
    def operation(self,typ:str,inputs:list[str],iny:list[str],outy:list[str])->str:
        x=f"op_pattern_{len(self.ops)}"; self.ops.append({"operation_id":x,"operation_type":typ,"input_frontier_ids":inputs,"output_frontier_ids":[],"attachment_location_ids":[],"join_input_mappings":[],"input_yarn_ids":iny,"output_yarn_ids":outy,"opening_id":None,"design_requirement_id":None,"join_method":"NONE","derivation_id":self.d({"entity_type":"CONSTRUCTION_OPERATION","operation_id":x})}); return x
    def start_work(self,cmd:PatternCommand)->None:
        if self.frontier is not None or cmd.yarn is None: raise ValueError("invalid start")
        y=self.yarn[cmd.yarn]; c=self.color[cmd.yarn]; self.topology="CYCLIC" if cmd.kind=="MAGIC_RING" else "LINEAR"; op=self.operation(cmd.kind,[],[],[y]); subj={"entity_type":"CONSTRUCTION_OPERATION","operation_id":op}; site=self.location("MAGIC_RING_ANCHOR" if cmd.kind=="MAGIC_RING" else "FABRIC_ATTACHMENT_POINT",subj,0); t=self.transition(subj,"CREATE",[],[],[site]); f=self.frontier_obj([site],"ACTIVE",t,y); self.ops[-1]["output_frontier_ids"]=[f];self.ops[-1]["attachment_location_ids"]=[site];self.trans[-1]["output_frontier_ids"]=[f];self.event(subj,t,None,y,None,c);self.frontier=f;self.initial=f;self.live=[site];self.current=y;self.current_color=c;self.start[y]=(op,cmd.kind)
    def change(self,cmd:PatternCommand)->None:
        if cmd.yarn is None or self.current is None: raise ValueError("invalid color change")
        y=self.yarn[cmd.yarn];c=self.color[cmd.yarn];op=self.operation("COLOR_CHANGE",[],[self.current],[y]);subj={"entity_type":"CONSTRUCTION_OPERATION","operation_id":op};self.event(subj,None,self.current,y,self.current_color,c);self.current=y;self.current_color=c;self.start[y]=(op,"COLOR_CHANGE")
    def stitch(self,cmd:PatternCommand,course:str)->str:
        if self.frontier is None or self.current is None or cmd.total is None: raise ValueError("missing stitch state")
        shape=cmd.shaping or "PLAIN"; typ="CHAIN" if cmd.kind=="CHAIN" else "SINGLE_CROCHET"; base_count=0 if typ=="CHAIN" else (2 if shape=="DECREASE" else 1); bases=self.live[:base_count]
        if len(bases)!=base_count: raise ValueError("invalid visible SC arity")
        sid=f"st_pattern_{len(self.st)}"; subj={"entity_type":"STITCH","stitch_id":sid}; tops=[self.location("TOP_LOOP",subj,i) for i in range(2 if shape=="INCREASE" else 1)]
        if typ=="CHAIN":
            if self.topology=="CYCLIC":
                if not self.live: raise ValueError("cyclic chain needs anchor")
                edit: dict[str, Any] = {"edit_type":"INSERT_AT_GAP","frontier_id":self.frontier,"left_location_id":self.live[-1],"right_location_id":self.live[0]}
            else: edit={"edit_type":"INSERT_AT_GAP","frontier_id":self.frontier,"left_location_id":self.live[-1] if self.live else None,"right_location_id":None}
            after=[*self.live,*tops]
        else: edit={"edit_type":"REPLACE_SPAN","frontier_id":self.frontier};after=[*tops,*self.live[base_count:]]
        self.st.append({"stitch_id":sid,"stitch_type":typ,"shaping":shape,"base_arity":len(bases),"top_arity":len(tops),"base_attachment_location_ids":bases,"top_attachment_location_ids":tops,"frontier_edit":edit,"yarn_id":self.current,"color_id":self.current_color,"course_id":course,"derivation_id":self.d(subj)});t=self.transition(subj,"ADVANCE",[self.frontier],bases,tops);f=self.frontier_obj(after,"ACTIVE",t,self.current);self.trans[-1]["output_frontier_ids"]=[f];e=self.event(subj,t,self.current,self.current,self.current_color,self.current_color);self.work[self.current].append(e);self.frontier=f;self.live=after
        visible=sum(next(item for item in self.loc if item["attachment_location_id"]==x)["location_type"]=="TOP_LOOP" for x in after)
        if visible!=cmd.total: raise ValueError("displayed total does not equal live TOP_LOOP count")
        return e
    def close(self)->None:
        if self.frontier is None or self.current is None: raise ValueError("invalid close")
        op=self.operation("CLOSE",[self.frontier],[],[]);subj={"entity_type":"CONSTRUCTION_OPERATION","operation_id":op};t=self.transition(subj,"CLOSE",[self.frontier],self.live,[]);f=self.frontier_obj([],"CLOSED",t,None);self.ops[-1]["output_frontier_ids"]=[f];self.trans[-1]["output_frontier_ids"]=[f];e=self.event(subj,t,self.current,self.current,self.current_color,self.current_color);self.work[self.current].append(e);self.frontier=f;self.live=[]
    def build(self)->dict[str,Any]:
        for x in self.u.leading:
            if x.kind in {"MAGIC_RING","ATTACH"}:self.start_work(x)
            elif x.kind=="COLOR_CHANGE":self.change(x)
            else:raise ValueError("invalid leading command")
        for ordinal,course in enumerate(self.u.courses):
            if self.frontier is None or self.topology!=course.form or (course.form=="CYCLIC" and course.anchor is None):raise ValueError("invalid course state")
            cid=f"course_pattern_{ordinal}";input_frontier=self.frontier;members=[self.stitch(x,cid) for x in course.commands]
            if not members:raise ValueError("empty course")
            self.courses.append({"course_id":cid,"ordinal":ordinal,"component_id":"component_0","branch_id":"branch_0","course_form":course.form,"turn_mode":"CONTINUOUS_SPIRAL" if course.form=="CYCLIC" else "TURN","work_direction":"CLOCKWISE" if course.form=="CYCLIC" else "FORWARD","member_event_ids":members,"input_frontier_ids":[input_frontier],"output_frontier_ids":[self.frontier],"derivation_id":self.d({"entity_type":"COURSE","course_id":cid})})
        for x in self.u.trailing:
            if x.kind=="COLOR_CHANGE":self.change(x)
            elif x.kind=="CLOSE":self.close()
            else:raise ValueError("invalid trailing command")
        if self.frontier is None or self.initial is None or self.current is None:raise ValueError("missing construction")
        paths: list[dict[str, Any]]=[]
        for yarn in self.yarns:
            y=yarn["yarn_id"]
            if y in self.start:
                op,kind=self.start[y];paths.append({"yarn_path_id":f"ypath_pattern_{len(paths)}","yarn_id":y,"segments":[{"yarn_segment_id":f"yseg_pattern_{len(paths)}","start_operation_id":op,"start_operation_type":kind,"event_ids":self.work[y],"end_operation_id":None,"end_operation_type":None}]})
        caps=["CORE_STITCHES_V1"]
        if any(x["operation_type"]=="MAGIC_RING" for x in self.ops):caps.append("MAGIC_RING_V1")
        if any(x["operation_type"]=="ATTACH" for x in self.ops):caps.append("FRONTIER_BRANCHING_V1")
        if any(x["shaping"]!="PLAIN" for x in self.st):caps.append("SHAPING_V1")
        if any(x["operation_type"]=="COLOR_CHANGE" for x in self.ops):caps.append("COLOR_CHANGES_V1")
        value={"schema_version":"1.0.0","semantics_profile":"CROCHET_CORE_1.0.0","crochet_ir_id":"cir_pattern_v1a","design_spec_ref":{"design_spec_id":self.c.design_spec["design_spec_id"],"sha256":canonical_hash(self.c.design_spec,CanonicalProfile.DESIGN_SPEC)},"units":{"length":"MILLIMETER","mass":"GRAM","angle":"RADIAN"},"required_capabilities":caps,"colors":self.colors,"yarns":self.yarns,"attachment_locations":self.loc,"stitches":self.st,"construction_operations":self.ops,"construction_sequence":self.events,"courses":self.courses,"course_order":[x["course_id"] for x in self.courses],"frontiers":self.frontiers,"frontier_transitions":self.trans,"branches":[{"branch_id":"branch_0","component_id":"component_0","parent_branch_ids":[],"created_by_transition_id":None,"course_ids":[x["course_id"] for x in self.courses],"entry_frontier_ids":[self.initial],"terminal_frontier_ids":[self.frontier]}],"components":[{"component_id":"component_0","branch_ids":["branch_0"],"initial_frontier_ids":[self.initial],"terminal_frontier_ids":[self.frontier]}],"openings":[],"yarn_paths":paths,"derivations":self.deriv,"provenance":{"generator":{"solver_family":"IMPORT","name":"pattern-v1a-binder","version":"1"},"solver_parameters":[],"solver_parameters_sha256":"0"*64,"random_seed":None,"search_budget":{"budget_type":"CANDIDATE_EVALUATIONS","limit":1,"consumed":0,"exhausted":False},"input_artifacts":[],"software_commit":"0"*40,"canonicalization":{"profile":"CROCHET_IR_CANONICAL_JSON_V1","hash_algorithm":"SHA-256"}}}
        report=_validator(self.c).validate_crochet_ir(value)
        if not report.ok:raise PatternFormatError(report)
        return value


def bind_pattern_semantics(unresolved: UnresolvedPatternSemantics, context: PatternParseContext) -> dict[str, Any]:
    try:return _Builder(unresolved,context).build()
    except PatternFormatError:raise
    except (ValueError,KeyError,TypeError) as error:raise _fail("","pattern.binding","Pattern text or external binding is invalid",str(error)) from error


def parse_pattern(text:str,*,context:PatternParseContext)->dict[str,Any]:return bind_pattern_semantics(parse_pattern_text(text),context)


def build_certification_manifest(value:dict[str,Any],text:str,terminology:TerminologyProfile,*,validator:SemanticValidator|None=None)->CertificationManifest:
    active=validator or SemanticValidator();return CertificationManifest(PATTERN_FORMAT_VERSION,canonical_hash(value,CanonicalProfile.CROCHET_IR,validator=active),semantic_hash(value,validator=active),sha256(text.encode()).hexdigest(),terminology.value,"pattern-v1a","semantic-validator-v1")


def verify_semantic_round_trip(value:dict[str,Any],terminology:TerminologyProfile,*,context:PatternParseContext,validator:SemanticValidator|None=None)->ValidationReport:
    try:
        text=export_pattern(value,terminology,validator=validator);bound=parse_pattern(text,context=context)
        if semantic_bytes(value,validator=validator)!=semantic_bytes(bound,validator=_validator(context)):raise _fail(text,"pattern.semantic_mismatch","Round trip changes CrochetIR semantics")
    except ArtifactValidationError as error:
        return ValidationReport.from_iterable([Diagnostic(code=FailureCode.EXPORT_ROUNDTRIP,gate="V9",message_key="pattern.round_trip_failed",summary="Pattern export cannot be certified as a semantic round trip",artifact_hash=sha256(repr(value).encode()).hexdigest(),cause_ids=tuple(x.diagnostic_id for x in error.report.diagnostics),implementation_version="pattern-v1a")])
    return ValidationReport()
