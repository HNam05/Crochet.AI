"""Target-independent reconstruction from visible M1B commands and external yarns."""

from __future__ import annotations

import re
from collections import Counter
from hashlib import sha256
from typing import Any

from .canonical import CanonicalProfile, canonical_hash
from .diagnostics import ArtifactValidationError
from .pattern import _label, _replace_live, _validator
from .pattern_context import PatternParseContext
from .pattern_m1b import (
    FAMILIES,
    LAYOUT,
    TERMS,
    Instruction,
    PatternM1BAst,
    boundary,
    fail,
    items,
    render_ast,
    symbol,
)
from .validation import SemanticValidator


def replay(ast: PatternM1BAst, context: PatternParseContext | None = None) -> dict[str, Any]:
    return _Replay(ast, context).build()


class _Replay:
    def __init__(self, ast: PatternM1BAst, context: PatternParseContext | None) -> None:
        self.ast, self.context = ast, context
        self.value: dict[str, Any] = {
            name: []
            for name in (
                "colors",
                "yarns",
                "attachment_locations",
                "stitches",
                "construction_operations",
                "construction_sequence",
                "courses",
                "frontiers",
                "frontier_transitions",
                "branches",
                "components",
                "openings",
                "yarn_paths",
                "derivations",
            )
        }
        self.fs: dict[str, dict[str, Any]] = {}
        self.locations: set[str] = set()
        self.tops: set[str] = set()
        self.live: set[str] = set()
        self.yarns: dict[str, str] = {}
        self.segments: dict[str, list[dict[str, Any]]] = {}
        self.current: str | None = None
        self.color: str | None = None
        self.memberships = 0
        self.step_transitions: dict[str, str] = {}
        self.digest = sha256(
            b"Crochet.AI\0M1B_VISIBLE_INSTRUCTIONS_V1\0" + render_ast(ast).encode()
        ).hexdigest()

    def d(self, subject: dict[str, str]) -> str:
        identifier = f"deriv_m1b_{len(self.value['derivations'])}"
        self.value["derivations"].append(
            {
                "derivation_id": identifier,
                "method": "IMPORTED",
                "rule_id": "pattern.m1b.visible-instruction",
                "rule_version": "1",
                "parameter_sha256": self.digest,
                "subject_refs": [subject],
            }
        )
        return identifier

    def front(self, fid: str, states: tuple[str, ...]) -> dict[str, Any]:
        if fid not in self.live or self.fs[fid]["lifecycle_state"] not in states:
            raise fail("frontier_lifecycle", "Instruction requires a current eligible boundary")
        return self.fs[fid]

    def new_locations(self, ids: list[str], kind: str, subject: dict[str, str]) -> None:
        if not ids or len(self.locations) + len(ids) > 8192:
            raise fail("location_budget")
        for ordinal, identifier in enumerate(ids):
            if identifier != symbol(_label(len(self.locations), "Marker"), "Marker"):
                raise fail("marker_order", "New markers follow their visible creation order")
            self.locations.add(identifier)
            if kind == "TOP_LOOP":
                self.tops.add(identifier)
            self.value["attachment_locations"].append(
                {
                    "attachment_location_id": identifier,
                    "location_type": kind,
                    "producer_ref": subject,
                    "ordinal_within_producer": ordinal,
                }
            )

    def output(self, descriptor: str, locations: list[str], state: str, transition: str) -> str:
        fid, piece, branch, topology, anchor, yarn = boundary(descriptor)
        expected = symbol(_label(len(self.fs), "Boundary"), "Boundary")
        if fid != expected or fid in self.fs or len(set(locations)) != len(locations):
            raise fail("boundary_order")
        if any(loc not in self.locations for loc in locations):
            raise fail("unknown_marker")
        if topology == "CYCLIC" and anchor != (locations[0] if locations else None):
            raise fail("anchor", "A cyclic boundary must begin at its declared anchor")
        if topology == "LINEAR" and anchor is not None:
            raise fail("anchor")
        self.memberships += len(locations)
        if self.memberships > 262144:
            raise fail("snapshot_budget")
        f = {
            "frontier_id": fid,
            "component_id": piece,
            "branch_id": branch,
            "topology": topology,
            "lifecycle_state": state,
            "attachment_location_ids": list(locations),
            "anchor_attachment_location_id": anchor,
            "active_yarn_id": yarn,
            "created_by_transition_id": transition,
        }
        if state == "CLOSED" and locations:
            raise fail("closure")
        self.fs[fid] = f
        self.value["frontiers"].append(f)
        if state in {"ACTIVE", "RESERVED"}:
            self.live.add(fid)
        return fid

    def material_declarations(self) -> None:
        records = [r for r in self.ast.instructions if r.action == "Yarn"]
        bindings = {}
        if self.context is not None:
            for binding in self.context.yarn_bindings:
                report = SemanticValidator().validate_material_profile(binding.material_profile)
                if not report.ok:
                    raise ArtifactValidationError(report)
                if binding.symbol in bindings:
                    raise fail("material_binding")
                bindings[binding.symbol] = binding
            if set(bindings) != {r.label for r in records}:
                raise fail("material_binding", "Bind exactly the visible yarn symbols")
        colors: dict[str, dict[str, Any]] = {}
        for r in records:
            y, c = symbol(r.label, "Yarn"), symbol(r.values[0], "Color")
            b = bindings.get(r.label)
            color = {
                "color_id": c,
                "label": b.color_label if b else r.values[0],
                "srgb_hex": b.srgb_hex if b else "#000000",
            }
            if c in colors and colors[c] != color:
                raise fail("color_binding", "Shared color symbols must resolve consistently")
            colors[c] = color
            if b:
                m = b.material_profile
                ref = {
                    "profile_id": m["profile_id"],
                    "revision": m["revision"],
                    "sha256": canonical_hash(m, CanonicalProfile.MATERIAL_PROFILE),
                }
            else:
                ref = {"profile_id": "mp_unbound", "revision": 1, "sha256": "0" * 64}
            self.value["yarns"].append(
                {"yarn_id": y, "label": r.label, "color_id": c, "material_profile_ref": ref}
            )
            self.yarns[y] = c
            self.segments[y] = []
        self.value["colors"] = list(colors.values())

    def declarations(self) -> None:
        saw_step = False
        for r in self.ast.instructions:
            if r.label.startswith("Step "):
                saw_step = True
                continue
            if saw_step:
                raise fail("declaration_order")
            f = dict(zip(LAYOUT[r.action], r.values, strict=True))
            if r.action == "Piece":
                self.value["components"].append(
                    {
                        "component_id": symbol(r.label, "Piece"),
                        "branch_ids": items(f["branches"], "Branch"),
                        "initial_frontier_ids": items(f["starts"], "Boundary"),
                        "terminal_frontier_ids": items(f["finishes"], "Boundary"),
                    }
                )
            elif r.action == "Branch":
                self.value["branches"].append(
                    {
                        "branch_id": symbol(r.label, "Branch"),
                        "component_id": symbol(f["piece"], "Piece"),
                        "parent_branch_ids": items(f["parents"], "Branch"),
                        "created_by_transition_id": None
                        if f["created"] == "start"
                        else symbol(f["created"], "Step"),
                        "course_ids": items(f["courses"], "Course"),
                        "entry_frontier_ids": items(f["enters"], "Boundary"),
                        "terminal_frontier_ids": items(f["finishes"], "Boundary"),
                    }
                )
            elif r.action == "Course":
                if re.fullmatch(r"[1-9][0-9]{0,3}", f["number"]) is None:
                    raise fail("course_number")
                if f["form"] not in {"linear", "cyclic"} or f["direction"] not in {
                    "forward",
                    "reverse",
                    "clockwise",
                    "counterclockwise",
                }:
                    raise fail("course_form")
                self.value["courses"].append(
                    {
                        "course_id": symbol(r.label, "Course"),
                        "ordinal": int(f["number"]) - 1,
                        "component_id": symbol(f["piece"], "Piece"),
                        "branch_id": symbol(f["branch"], "Branch"),
                        "course_form": f["form"].upper(),
                        "turn_mode": f["turn"].upper().replace(" ", "_"),
                        "work_direction": f["direction"].upper(),
                        "input_frontier_ids": items(f["starts"], "Boundary"),
                        "output_frontier_ids": items(f["finishes"], "Boundary"),
                        "member_event_ids": items(f["steps"], "Step"),
                        "derivation_id": self.d(
                            {"entity_type": "COURSE", "course_id": symbol(r.label, "Course")}
                        ),
                    }
                )

    def step(self, r: Instruction) -> None:
        v, index = self.value, len(self.value["construction_sequence"])
        if index >= 4096 or r.label != _label(index, "Step"):
            raise fail("step_order")
        action = "Work" if r.action.startswith("Work ") else r.action
        f = dict(zip(LAYOUT[action], r.values, strict=True))
        eid = symbol(r.label, "Step")
        oid = "op_m1b_" + r.label.split()[1]
        tid = f"ftrans_m1b_{len(v['frontier_transitions'])}"
        before, before_color = self.current, self.color
        ins: list[str] = []
        outs: list[str] = []
        created: list[str] = []
        retired: list[str] = []
        reserved: list[str] = []
        iny: list[str] = []
        outy: list[str] = []
        sites: list[str] = []
        maps: list[dict[str, Any]] = []
        opening_id: str | None = None
        requirement: str | None = None
        method = "NONE"
        has_transition = True
        types = {
            "Make a magic ring": "MAGIC_RING",
            "Start yarn": "ATTACH",
            "Reattach yarn": "ATTACH",
            "Reserve": "RESERVE",
            "Split": "SPLIT",
            "Join": "JOIN",
            "Close": "CLOSE",
            "Leave open": "DECLARE_OPENING",
            "Change yarn": "COLOR_CHANGE",
            "Cut yarn": "CUT_YARN",
        }
        kind = types.get(action, "STITCH")
        subject = (
            {"entity_type": "STITCH", "stitch_id": "st_m1b_" + r.label.split()[1]}
            if kind == "STITCH"
            else {"entity_type": "CONSTRUCTION_OPERATION", "operation_id": oid}
        )
        transition_kind = "ADVANCE" if kind == "STITCH" else kind
        if action in {"Make a magic ring", "Start yarn", "Reattach yarn"}:
            y = symbol(f["yarn"], "Yarn")
            if y not in self.yarns or self.current is not None:
                raise fail("start_yarn", "Starting or reattaching requires an inactive yarn state")
            self.current, self.color = y, self.yarns[y]
            outy = [y]
            if action == "Reattach yarn":
                fid = symbol(f["on"], "Boundary")
                previous = self.front(fid, ("RESERVED",))
                ins, sites = [fid], items(f["at"], "Marker")
                if len(sites) != 1 or sites[0] not in previous["attachment_location_ids"]:
                    raise fail("reattach_marker")
                after = previous["attachment_location_ids"]
                transition_kind = "REATTACH"
            else:
                sites = items(f["sites"], "Marker")
                self.new_locations(
                    sites,
                    "MAGIC_RING_ANCHOR"
                    if action == "Make a magic ring"
                    else "FABRIC_ATTACHMENT_POINT",
                    subject,
                )
                created, after = sites, sites
                transition_kind = "CREATE"
            outs = [self.output(f["output"], after, "ACTIVE", tid)]
        elif action == "Work":
            if self.current is None:
                raise fail("stitch_yarn")
            fid = symbol(f["on"], "Boundary")
            previous = self.front(fid, ("ACTIVE",))
            live = list(previous["attachment_location_ids"])
            ins, bases, tops = [fid], items(f["bases"], "Marker"), items(f["tops"], "Marker")
            word = r.action.removeprefix("Work 1 ")
            shape = "PLAIN"
            for suffix in (" increase", " decrease"):
                if word.endswith(suffix):
                    shape, word = suffix.strip().upper(), word[: -len(suffix)]
            if word not in TERMS[self.ast.terminology.value]:
                raise fail("stitch_family")
            family = FAMILIES[TERMS[self.ast.terminology.value].index(word)]
            arity = (
                (0, 1)
                if family == "CHAIN" and shape == "PLAIN"
                else (1, 1)
                if shape == "PLAIN"
                else (1, 2)
                if family == "SINGLE_CROCHET" and shape == "INCREASE"
                else (2, 1)
                if family == "SINGLE_CROCHET" and shape == "DECREASE"
                else None
            )
            if arity != (len(bases), len(tops)):
                raise fail("stitch_arity")
            self.new_locations(tops, "TOP_LOOP", subject)
            if family == "CHAIN":
                gap = f["gap"].split(", ")
                if len(gap) != 2:
                    raise fail("gap")
                left, right = [None if m == "none" else symbol(m, "Marker") for m in gap]
                if previous["topology"] == "CYCLIC":
                    if (
                        left not in live
                        or right not in live
                        or live[(live.index(left) + 1) % len(live)] != right
                    ):
                        raise fail("gap")
                    offset = live.index(left) + 1
                elif left is None and right == (live[0] if live else None):
                    offset = 0
                elif right is None and left == (live[-1] if live else None):
                    offset = len(live)
                elif left in live and right in live and live.index(right) == live.index(left) + 1:
                    offset = live.index(right)
                else:
                    raise fail("gap")
                after = live[:offset] + tops + live[offset:]
                edit = {
                    "edit_type": "INSERT_AT_GAP",
                    "frontier_id": fid,
                    "left_location_id": left,
                    "right_location_id": right,
                }
            else:
                if f["gap"] != "none":
                    raise fail("gap")
                after = _replace_live(live, bases, tops, previous["topology"] == "CYCLIC")
                edit = {"edit_type": "REPLACE_SPAN", "frontier_id": fid}
            output_info = boundary(f["output"])
            if previous["topology"] == "CYCLIC":
                anchor = output_info[4]
                if anchor not in after:
                    raise fail("anchor")
                at = after.index(anchor)
                after = after[at:] + after[:at]
            if re.fullmatch(r"[0-9]{1,4}", f["total"]) is None or int(f["total"]) != sum(
                m in self.tops for m in after
            ):
                raise fail("total", "Visible total disagrees with remaining top loops")
            outs = [self.output(f["output"], after, "ACTIVE", tid)]
            retired, created = bases, tops
            v["stitches"].append(
                {
                    "stitch_id": subject["stitch_id"],
                    "stitch_type": family,
                    "shaping": shape,
                    "base_arity": len(bases),
                    "top_arity": len(tops),
                    "base_attachment_location_ids": bases,
                    "top_attachment_location_ids": tops,
                    "frontier_edit": edit,
                    "yarn_id": self.current,
                    "color_id": self.color,
                    "course_id": symbol(f["course"], "Course"),
                    "derivation_id": self.d(subject),
                }
            )
        elif action in {"Reserve", "Split"}:
            fid = symbol(f["on"], "Boundary")
            previous = self.front(fid, ("ACTIVE",))
            ins = [fid]
            partition: list[str] = []
            states = []
            for part in f["outputs"].split(" | "):
                match = re.fullmatch(r"(.+) using (.+) as (active|reserved)", part)
                if match is None:
                    raise fail("partition")
                descriptor, markers, state = match.groups()
                ms = items(markers, "Marker")
                source = previous["attachment_location_ids"]
                if (
                    not ms
                    or any(m not in source for m in ms)
                    or [source.index(m) for m in ms] != sorted(source.index(m) for m in ms)
                ):
                    raise fail("partition_order")
                partition.extend(ms)
                states.append(state)
                if state == "reserved":
                    reserved.extend(ms)
                outs.append(self.output(descriptor, ms, state.upper(), tid))
            if len(outs) < 2 or Counter(partition) != Counter(previous["attachment_location_ids"]):
                raise fail("partition_conservation")
            if (
                action == "Reserve" and (states.count("active") != 1 or "reserved" not in states)
            ) or (action == "Split" and "reserved" in states):
                raise fail("partition_state")
        elif action == "Join":
            after = []
            for part in f["inputs"].split(" | "):
                match = re.fullmatch(r"(Boundary [A-Z]{1,4}) (forward|reversed) using (.+)", part)
                if match is None:
                    raise fail("join")
                name, orientation, markers = match.groups()
                fid = symbol(name, "Boundary")
                previous = self.front(fid, ("ACTIVE", "RESERVED"))
                if fid in ins:
                    raise fail("join_input")
                consumed = items(markers, "Marker")
                order = list(previous["attachment_location_ids"])
                if any(m not in order for m in consumed):
                    raise fail("join_marker")
                if orientation == "reversed":
                    order.reverse()
                after.extend(m for m in order if m not in consumed)
                ins.append(fid)
                maps.append(
                    {
                        "input_frontier_id": fid,
                        "orientation": orientation.upper(),
                        "consumed_attachment_location_ids": consumed,
                    }
                )
                retired.extend(consumed)
            if len(ins) < 2 or f["method"] not in {"crocheted", "sewn"}:
                raise fail("join_method")
            sites, method = list(retired), f["method"].upper()
            outs = [self.output(f["output"], after, "ACTIVE" if after else "CLOSED", tid)]
        elif action in {"Close", "Leave open"}:
            fid = symbol(f["on"], "Boundary")
            previous = self.front(fid, ("ACTIVE", "RESERVED"))
            ins = [fid]
            if action == "Close":
                retired = list(previous["attachment_location_ids"])
                outs = [self.output(f["output"], [], "CLOSED", tid)]
            else:
                opening_id, requirement = symbol(f["opening"], "Opening"), f["requirement"]
                if (
                    re.fullmatch(r"opening_req_[A-Za-z0-9][A-Za-z0-9._-]{0,105}", requirement)
                    is None
                ):
                    raise fail("opening_requirement")
                outs = [
                    self.output(
                        f["output"], previous["attachment_location_ids"], "DECLARED_OPEN", tid
                    )
                ]
                v["openings"].append(
                    {
                        "opening_id": opening_id,
                        "component_id": previous["component_id"],
                        "design_requirement_id": requirement,
                        "declared_by_operation_id": oid,
                        "boundary_attachment_location_ids": list(
                            previous["attachment_location_ids"]
                        ),
                        "purpose": f["purpose"].upper().replace(" ", "_"),
                        "closure_expectation": f["expectation"].upper().replace(" ", "_"),
                        "derivation_id": self.d(
                            {"entity_type": "OPENING", "opening_id": opening_id}
                        ),
                    }
                )
        elif action in {"Change yarn", "Cut yarn"}:
            expected = symbol(f["from"] if action == "Change yarn" else f["yarn"], "Yarn")
            if self.current != expected or not self.segments[expected]:
                raise fail("yarn_state")
            iny = [expected]
            self.segments[expected][-1].update(end_operation_id=oid, end_operation_type=kind)
            if action == "Change yarn":
                y = symbol(f["to"], "Yarn")
                if y not in self.yarns:
                    raise fail("yarn_binding")
                outy, self.current, self.color = [y], y, self.yarns[y]
            else:
                self.current, self.color = None, None
            has_transition = False
        else:
            raise fail("action")
        for fid in ins:
            self.live.remove(fid)
        if kind != "STITCH":
            v["construction_operations"].append(
                {
                    "operation_id": oid,
                    "operation_type": kind,
                    "input_frontier_ids": ins,
                    "output_frontier_ids": outs,
                    "attachment_location_ids": sites,
                    "join_input_mappings": maps,
                    "input_yarn_ids": iny,
                    "output_yarn_ids": outy,
                    "opening_id": opening_id,
                    "design_requirement_id": requirement,
                    "join_method": method,
                    "derivation_id": self.d(subject),
                }
            )
        if has_transition:
            v["frontier_transitions"].append(
                {
                    "frontier_transition_id": tid,
                    "transition_index": len(v["frontier_transitions"]),
                    "after_event_index": index,
                    "caused_by_subject_ref": subject,
                    "transition_type": transition_kind,
                    "input_frontier_ids": ins,
                    "output_frontier_ids": outs,
                    "retired_attachment_location_ids": retired,
                    "created_attachment_location_ids": created,
                    "reserved_attachment_location_ids": reserved,
                    "opening_id": opening_id,
                }
            )
            self.step_transitions[eid] = tid
        v["construction_sequence"].append(
            {
                "event_id": eid,
                "sequence_index": index,
                "subject_ref": subject,
                "active_yarn_id_before": before,
                "active_yarn_id_after": self.current,
                "active_color_id_before": before_color,
                "active_color_id_after": self.color,
                "frontier_transition_ids": [tid] if has_transition else [],
            }
        )
        if kind in {"MAGIC_RING", "ATTACH", "COLOR_CHANGE"}:
            if self.current is None:
                raise fail("segment")
            self.segments[self.current].append(
                {
                    "yarn_segment_id": f"yseg_m1b_{index}",
                    "start_operation_id": oid,
                    "start_operation_type": kind,
                    "event_ids": [],
                    "end_operation_id": None,
                    "end_operation_type": None,
                }
            )
        elif kind != "CUT_YARN" and self.current is not None:
            self.segments[self.current][-1]["event_ids"].append(eid)

    def build(self) -> dict[str, Any]:
        self.material_declarations()
        self.declarations()
        for record in self.ast.instructions:
            if record.label.startswith("Step "):
                self.step(record)
        if self.live or not self.fs or not self.value["stitches"]:
            raise fail("unfinished", "Every boundary must close or be explicitly left open")
        for branch in self.value["branches"]:
            created = branch["created_by_transition_id"]
            if created is not None:
                if created not in self.step_transitions:
                    raise fail("branch_start")
                branch["created_by_transition_id"] = self.step_transitions[created]
        for yarn, segments in self.segments.items():
            if not segments:
                raise fail("unused_yarn")
            self.value["yarn_paths"].append(
                {"yarn_path_id": "ypath_" + yarn, "yarn_id": yarn, "segments": segments}
            )
        self.value.update(
            schema_version=self.ast.core,
            semantics_profile="CROCHET_CORE_" + self.ast.core,
            crochet_ir_id="cir_pattern_m1b",
            units={"length": "MILLIMETER", "mass": "GRAM", "angle": "RADIAN"},
            required_capabilities=list(self.ast.capabilities),
            course_order=[c["course_id"] for c in self.value["courses"]],
            design_spec_ref={
                "design_spec_id": self.context.design_spec["design_spec_id"]
                if self.context
                else "ds_unbound",
                "sha256": canonical_hash(
                    self.context.design_spec,
                    CanonicalProfile.DESIGN_SPEC,
                    validator=_validator(self.context),
                )
                if self.context
                else "0" * 64,
            },
            provenance={
                "generator": {
                    "solver_family": "IMPORT",
                    "name": "pattern-m1b-binder",
                    "version": "1",
                },
                "solver_parameters": [
                    {"name": "visible_instructions_sha256", "value": self.digest}
                ],
                "solver_parameters_sha256": self.digest,
                "random_seed": None,
                "search_budget": {
                    "budget_type": "CANDIDATE_EVALUATIONS",
                    "limit": 1,
                    "consumed": 0,
                    "exhausted": False,
                },
                "input_artifacts": [],
                "software_commit": "0" * 40,
                "canonicalization": {
                    "profile": "CROCHET_IR_CANONICAL_JSON_V1",
                    "hash_algorithm": "SHA-256",
                },
            },
        )
        return self.value
