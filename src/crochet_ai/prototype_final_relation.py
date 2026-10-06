"""Independent bounded audit of the native-to-prototype CrochetIR relation."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, cast

from .canonical import CanonicalProfile, canonical_hash, jcs_bytes, validate_ijson
from .diagnostics import ArtifactValidationError
from .equivalence import semantic_projection
from .json_types import JSONValue
from .validation import SemanticValidator

PROFILE = "PROTOTYPE_FINAL_RELATION_AUDIT_V1"
POLICY = "FIXED_ZERO_CONTINUOUS_V1"
_PARAMETER_FIELDS = {"prototype.phase_policy", "prototype.count_schedule", "prototype.final_phases"}
_TABLES = (
    "colors",
    "yarns",
    "attachment_locations",
    "stitches",
    "construction_operations",
    "courses",
    "frontiers",
    "frontier_transitions",
    "branches",
    "components",
    "openings",
    "yarn_paths",
    "derivations",
    "construction_sequence",
)


class PrototypeRelationInputError(ValueError):
    """Malformed or over-budget audit input, rejected before hashing."""


class _UnsupportedRelationScope(Exception):
    pass


@dataclass(frozen=True, slots=True)
class PrototypeFinalRelationReport:
    status: str
    sha256: str
    _payload: bytes

    def to_dict(self) -> dict[str, Any]:
        import json

        return cast(dict[str, Any], json.loads(self._payload))


def _bound(
    values: tuple[object, ...], max_events: int, max_courses: int, max_parameters: int
) -> None:
    if any(type(v) is not int or v <= 0 for v in (max_events, max_courses, max_parameters)):
        raise PrototypeRelationInputError("resource_limits_positive_exact_integers_required")
    if max_events > 30_000 or max_courses > 512 or max_parameters > 256:
        raise PrototypeRelationInputError("resource_limits_exceed_profile_ceilings")
    count = 0
    for value in values:
        if not isinstance(value, dict):
            raise PrototypeRelationInputError("artifact_object_required")
        pending: list[tuple[object, int]] = [(value, 0)]
        while pending:
            node, depth = pending.pop()
            count += 1
            if count > 100_000 or depth > 64:
                raise PrototypeRelationInputError("input_complexity_exceeded")
            if isinstance(node, dict):
                if len(pending) + len(node) > 100_000 - count:
                    raise PrototypeRelationInputError("input_complexity_exceeded")
                if any(
                    not isinstance(key, str) or not key.isascii() or len(key) > 128 for key in node
                ):
                    raise PrototypeRelationInputError("input_key_limit_exceeded")
                pending.extend((item, depth + 1) for item in node.values())
            elif isinstance(node, list):
                if len(pending) + len(node) > 100_000 - count:
                    raise PrototypeRelationInputError("input_complexity_exceeded")
                pending.extend((item, depth + 1) for item in node)
            elif isinstance(node, str) and len(node) > 4096:
                raise PrototypeRelationInputError("input_string_limit_exceeded")
    for ir in values[-2:]:
        assert isinstance(ir, dict)
        for key in ("construction_sequence", "frontier_transitions"):
            rows = ir.get(key)
            if not isinstance(rows, list) or len(rows) > max_events:
                raise PrototypeRelationInputError(f"{key}_budget_exceeded")
        courses = ir.get("courses")
        provenance = ir.get("provenance")
        params = provenance.get("solver_parameters") if isinstance(provenance, dict) else None
        if not isinstance(courses, list) or len(courses) > max_courses:
            raise PrototypeRelationInputError("courses_budget_exceeded")
        if not isinstance(params, list) or len(params) > max_parameters:
            raise PrototypeRelationInputError("solver_parameters_budget_exceeded")
        for table in _TABLES:
            rows = ir.get(table)
            if not isinstance(rows, list) or len(rows) > 30_000:
                raise PrototypeRelationInputError(f"{table}_resource_ceiling_exceeded")
    for value in values:
        validate_ijson(value)


def _actual_schedule(ir: dict[str, Any]) -> tuple[list[int], list[int]]:
    courses = {row["course_id"]: row for row in ir["courses"]}
    stitches = {row["stitch_id"]: row for row in ir["stitches"]}
    events = sorted(ir["construction_sequence"], key=lambda row: row["sequence_index"])
    event_by_id = {event["event_id"]: event for event in events}
    schedule: list[int] = []
    phases: list[int] = []
    frontiers = {row["frontier_id"]: row for row in ir["frontiers"]}
    for index, course_id in enumerate(ir["course_order"]):
        course = courses[course_id]
        nodes = [
            stitches[event_by_id[event_id]["subject_ref"]["stitch_id"]]
            for event_id in course["member_event_ids"]
        ]
        bases = sum(node["base_arity"] for node in nodes)
        tops = sum(node["top_arity"] for node in nodes)
        before = frontiers[course["input_frontier_ids"][0]]["attachment_location_ids"]
        if index:
            phases.append(before.index(nodes[0]["base_attachment_location_ids"][0]))
        schedule.append(tops)
        if bases <= 0:
            raise ValueError("course_has_no_input")
    return schedule, phases


def _execution_chain(ir: dict[str, Any]) -> bool:
    events = sorted(ir["construction_sequence"], key=lambda row: row["sequence_index"])
    transitions = sorted(ir["frontier_transitions"], key=lambda row: row["transition_index"])
    frontiers = {row["frontier_id"]: row for row in ir["frontiers"]}
    stitches = {row["stitch_id"]: row for row in ir["stitches"]}
    operations = {row["operation_id"]: row for row in ir["construction_operations"]}
    courses = {row["course_id"]: row for row in ir["courses"]}
    if not events or len(transitions) != len(events):
        return False
    if [e["sequence_index"] for e in events] != list(range(len(events))):
        return False
    if [t["transition_index"] for t in transitions] != list(range(len(transitions))):
        return False
    first, last = events[0], events[-1]
    try:
        ring = operations[first["subject_ref"]["operation_id"]]
        close = operations[last["subject_ref"]["operation_id"]]
        if ring["operation_type"] != "MAGIC_RING" or close["operation_type"] != "CLOSE":
            return False
        current_id = transitions[0]["output_frontier_ids"][0]
        current_cycle = list(frontiers[current_id]["attachment_location_ids"])
        if not current_cycle or current_cycle != ring["attachment_location_ids"]:
            return False
        if frontiers[current_id]["anchor_attachment_location_id"] != current_cycle[0]:
            return False
        if (
            transitions[0]["transition_type"] != "CREATE"
            or transitions[0]["created_attachment_location_ids"] != current_cycle
        ):
            return False
        event_by_id = {event["event_id"]: i for i, event in enumerate(events)}
        transition_by_id = {t["frontier_transition_id"]: t for t in transitions}
        cursor_event = 1
        for course_id in ir["course_order"]:
            course = courses[course_id]
            input_ids = course["input_frontier_ids"]
            if input_ids != [current_id] or not course["member_event_ids"]:
                return False
            if [event_by_id[eid] for eid in course["member_event_ids"]] != list(
                range(cursor_event, cursor_event + len(course["member_event_ids"]))
            ):
                return False
            course_input_id = current_id
            course_input_cycle = list(current_cycle)
            first_stitch = stitches[events[cursor_event]["subject_ref"]["stitch_id"]]
            phase = course_input_cycle.index(first_stitch["base_attachment_location_ids"][0])
            consumed = 0
            for event_id in course["member_event_ids"]:
                event = events[event_by_id[event_id]]
                ref = event["subject_ref"]
                if ref["entity_type"] != "STITCH" or len(event["frontier_transition_ids"]) != 1:
                    return False
                stitch = stitches[ref["stitch_id"]]
                transition = transition_by_id[event["frontier_transition_ids"][0]]
                arity = stitch["base_arity"]
                expected = [
                    course_input_cycle[(phase + consumed + i) % len(course_input_cycle)]
                    for i in range(arity)
                ]
                bases = stitch["base_attachment_location_ids"]
                if bases != expected or transition["retired_attachment_location_ids"] != bases:
                    return False
                if transition["input_frontier_ids"] != [current_id]:
                    return False
                if (
                    transition["caused_by_subject_ref"] != ref
                    or transition["created_attachment_location_ids"]
                    != stitch["top_attachment_location_ids"]
                ):
                    return False
                if transition["transition_type"] != "ADVANCE":
                    return False
                first_base = bases[0]
                start = current_cycle.index(first_base)
                rotated = current_cycle[start:] + current_cycle[:start]
                if rotated[: len(bases)] != bases:
                    return False
                rewritten = list(stitch["top_attachment_location_ids"]) + rotated[len(bases) :]
                old_anchor = current_cycle[0]
                anchor = (
                    old_anchor
                    if old_anchor in rewritten
                    else stitch["top_attachment_location_ids"][0]
                )
                offset = rewritten.index(anchor)
                rewritten = rewritten[offset:] + rewritten[:offset]
                new_id = transition["output_frontier_ids"][0]
                if (
                    list(frontiers[new_id]["attachment_location_ids"]) != rewritten
                    or frontiers[new_id]["anchor_attachment_location_id"] != anchor
                ):
                    return False
                current_id, current_cycle = new_id, rewritten
                consumed += arity
            if consumed != len(course_input_cycle):
                return False
            next_id = course["output_frontier_ids"][0]
            if next_id != current_id or course["input_frontier_ids"] != [course_input_id]:
                return False
            cursor_event += len(course["member_event_ids"])
        if cursor_event != len(events) - 1 or last["frontier_transition_ids"] != [
            transitions[-1]["frontier_transition_id"]
        ]:
            return False
        terminal = transitions[-1]
        return bool(
            terminal["transition_type"] == "CLOSE"
            and terminal["input_frontier_ids"] == [current_id]
            and terminal["retired_attachment_location_ids"] == current_cycle
            and terminal["created_attachment_location_ids"] == []
            and frontiers[terminal["output_frontier_ids"][0]]["attachment_location_ids"] == []
            and frontiers[terminal["output_frontier_ids"][0]]["lifecycle_state"] == "CLOSED"
        )
    except (KeyError, IndexError, TypeError, ValueError):
        return False


def _params(ir: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = ir["provenance"]["solver_parameters"]
    if any(not isinstance(row, dict) or set(row) != {"name", "value"} for row in rows):
        raise ValueError("malformed_parameter")
    names = [row["name"] for row in rows]
    if len(names) != len(set(names)):
        raise ValueError("duplicate_parameter")
    return {row["name"]: row["value"] for row in rows}, rows


def _without_phase_fields(value: dict[str, Any], validator: SemanticValidator) -> dict[str, Any]:
    projected = semantic_projection(value, validator=validator)
    for stitch in projected["stitches"]:
        stitch.pop("base_attachment_location_ids", None)
    for frontier in projected["frontiers"]:
        frontier.pop("attachment_location_ids", None)
        frontier.pop("anchor_attachment_location_id", None)
    for transition in projected["frontier_transitions"]:
        if transition.get("transition_type") in {"ADVANCE", "CLOSE"}:
            transition.pop("retired_attachment_location_ids", None)
    return projected


def inspect_prototype_final_relation(
    design: dict[str, Any],
    material: dict[str, Any],
    original_proposal: dict[str, Any],
    crochet_ir: dict[str, Any],
    *,
    validator: SemanticValidator,
    max_events: int = 30_000,
    max_courses: int = 512,
    max_parameters: int = 256,
) -> PrototypeFinalRelationReport:
    """Audit exactly one supported native proposal against its phase-zero final IR."""
    _bound(
        (design, material, original_proposal, crochet_ir), max_events, max_courses, max_parameters
    )
    hashes = {
        "design_spec_sha256": canonical_hash(
            design, CanonicalProfile.DESIGN_SPEC, validator=validator
        ),
        "material_profile_sha256": canonical_hash(
            material, CanonicalProfile.MATERIAL_PROFILE, validator=validator
        ),
        "original_proposal_sha256": canonical_hash(
            original_proposal, CanonicalProfile.CROCHET_IR, validator=validator
        ),
        "final_ir_sha256": canonical_hash(
            crochet_ir, CanonicalProfile.CROCHET_IR, validator=validator
        ),
    }
    assertions: dict[str, bool] = {}
    diagnostics: list[dict[str, str]] = []

    def check(
        name: str,
        result: bool,
        reason: str,
        *,
        code: str = "E_DETERMINISM",
        diagnostic: bool = True,
    ) -> None:
        assertions[name] = result
        if not result and diagnostic:
            diagnostics.append({"code": code, "reason": reason})

    status = "INDETERMINATE"
    try:
        for value in (design, material, original_proposal, crochet_ir):
            report = (
                validator.validate_design_spec(value)
                if value is design
                else (
                    validator.validate_material_profile(value)
                    if value is material
                    else validator.validate_crochet_ir(value)
                )
            )
            if not report.ok:
                raise ArtifactValidationError(report)
        original_params, original_rows = _params(original_proposal)
        final_params, final_rows = _params(crochet_ir)
        extras = {name: final_params.get(name) for name in _PARAMETER_FIELDS}
        native = not any(row["name"].startswith("prototype.") for row in original_rows)
        check("native_original", native, "original proposal contains prototype parameters")
        check(
            "exact_prototype_parameters",
            set(name for name in final_params if name.startswith("prototype."))
            == _PARAMETER_FIELDS,
            "final proposal does not contain exactly the three supported prototype parameters",
            diagnostic=False,
        )
        policy_ok = extras["prototype.phase_policy"] == POLICY
        check(
            "supported_phase_policy",
            policy_ok,
            "prototype phase policy is unsupported",
            diagnostic=False,
        )
        original_claims = original_params.copy()
        final_claims = {
            name: value for name, value in final_params.items() if not name.startswith("prototype.")
        }
        same_params = jcs_bytes(cast(JSONValue, original_claims)) == jcs_bytes(
            cast(JSONValue, final_claims)
        )
        op = original_proposal["provenance"]
        fp = crochet_ir["provenance"]
        provenance = {
            k: deepcopy(v)
            for k, v in op.items()
            if k not in {"solver_parameters_sha256", "solver_parameters"}
        }
        final_provenance = {
            k: deepcopy(v)
            for k, v in fp.items()
            if k not in {"solver_parameters_sha256", "solver_parameters"}
        }
        check(
            "original_parameters_and_provenance_preserved",
            same_params and jcs_bytes(provenance) == jcs_bytes(final_provenance),
            "original parameters or non-digest provenance changed",
            code="E_PROVENANCE",
        )
        for source, rows in ((original_proposal, original_rows), (crochet_ir, final_rows)):
            ordered = sorted(rows, key=lambda row: row["name"])
            expected = sha256(
                b"Crochet.AI\0ANALYTIC_COMPILER_PARAMETERS_V1\0"
                + jcs_bytes(cast(JSONValue, ordered))
            ).hexdigest()
            check(
                "parameter_digest_" + ("original" if source is original_proposal else "final"),
                source["provenance"].get("solver_parameters_sha256") == expected,
                "parameter digest mismatch",
                code="E_PROVENANCE",
            )
        claims = []
        unsupported_claims = False
        for value in (original_proposal, crochet_ir):
            from .analytic_claims import inspect_analytic_candidate_claims

            claim = inspect_analytic_candidate_claims(design, material, value, validator=validator)
            data = cast(dict[str, Any], claim.to_dict())
            if (
                claim.status == "NOT_APPLICABLE"
                or "analytic_closed_sc_schedule_out_of_scope" in data["missing_checks"]
            ):
                raise _UnsupportedRelationScope
            unsupported_claims |= any(
                item.startswith("unsupported_parameter:") for item in data["missing_checks"]
            )
            claims.append(claim.status != "FAIL" and all(data["assertions"].values()))
        ring = next(
            row
            for row in original_proposal["construction_operations"]
            if row["operation_type"] == "MAGIC_RING"
        )
        if (
            len(ring["attachment_location_ids"]) < 2
            or "MULTI_STITCH_RING_V1" not in original_proposal["required_capabilities"]
        ):
            raise _UnsupportedRelationScope
        schedules = [_actual_schedule(value) for value in (original_proposal, crochet_ir)]
        counts_equal = schedules[0][0] == schedules[1][0]
        check(
            "actual_count_schedule_equal",
            counts_equal,
            "actual ordered round counts differ",
            code="E_COUNT",
        )
        check(
            "actual_execution_chains",
            _execution_chain(original_proposal) and _execution_chain(crochet_ir),
            "raw execution chain, span replacement, or required anchor is invalid",
            code="E_FRONTIER",
        )
        expected_count = ",".join(str(item) for item in schedules[1][0])
        expected_phases = ",".join("0" for _ in schedules[1][1])
        check(
            "canonical_prototype_schedule_strings",
            type(extras["prototype.count_schedule"]) is str
            and extras["prototype.count_schedule"] == expected_count
            and type(extras["prototype.final_phases"]) is str
            and extras["prototype.final_phases"] == expected_phases,
            "prototype schedule parameters are not canonical strings for the actual final schedule",
            code="E_PROVENANCE",
        )
        check(
            "zero_final_phases",
            schedules[1][1] == [0] * len(schedules[1][1]),
            "actual final course phases are not all zero",
            code="E_COUNT",
        )
        check(
            "independent_analytic_cyclic_claims",
            all(claims),
            "analytic schedule claims were false or unsupported",
            code="E_COUNT",
        )
        semantic_equal = jcs_bytes(
            _without_phase_fields(original_proposal, validator)
        ) == jcs_bytes(_without_phase_fields(crochet_ir, validator))
        check(
            "phase_normalized_semantics_equal",
            semantic_equal,
            "phase-normalized construction semantics differ",
        )
        unsupported = (
            unsupported_claims
            or extras["prototype.phase_policy"] != POLICY
            or any(
                name.startswith("prototype.") and name not in _PARAMETER_FIELDS
                for name in final_params
            )
        )
        if diagnostics:
            status = "FAIL"
        elif unsupported:
            status = "INDETERMINATE"
        elif all(assertions.values()):
            status = "PASS"
        else:
            status = "FAIL"
    except _UnsupportedRelationScope:
        status = "FAIL" if diagnostics else "INDETERMINATE"
    except ArtifactValidationError as error:
        status = "FAIL"
        diagnostics.append({"code": "E_SCHEMA", "reason": str(error)[:256]})
    except (KeyError, IndexError, TypeError, ValueError) as error:
        status = "FAIL"
        diagnostics.append(
            {"code": "E_PROVENANCE", "reason": str(error)[:256] or "invalid_relation_input"}
        )
    payload: dict[str, Any] = {
        "profile": PROFILE,
        "status": status,
        **hashes,
        "assertions": assertions,
        "diagnostics": diagnostics,
        "missing_checks": [] if status == "PASS" else ["supported_final_relation"],
        "scope": "closed-pole single-component single-branch single-yarn "
        "continuous-spiral SC phase relation",
        "budgets": {
            "max_events": max_events,
            "max_courses": max_courses,
            "max_parameters": max_parameters,
            "max_nodes": 100_000,
            "max_depth": 64,
            "max_string_characters": 4096,
            "max_key_characters": 128,
            "max_object_key_characters": 128,
            "max_table_entries": 30_000,
        },
        "source_authentication": "NOT_VERIFIED",
        "physical_status": "UNTESTED",
    }
    encoded = jcs_bytes(payload)
    digest = sha256(b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + encoded).hexdigest()
    return PrototypeFinalRelationReport(status, digest, encoded)


def unique_original_proposal(
    final_ir: dict[str, Any], proposals: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Return a uniquely lineage-matching native proposal; never select first by order."""
    try:
        final = {row["name"]: row["value"] for row in final_ir["provenance"]["solver_parameters"]}
        for key in _PARAMETER_FIELDS:
            final.pop(key, None)
        final.pop("prototype.phase_policy", None)
        matches: list[dict[str, Any]] = []
        for proposal in proposals:
            params = {
                row["name"]: row["value"] for row in proposal["provenance"]["solver_parameters"]
            }
            if any(name.startswith("prototype.") for name in params):
                continue
            params.pop("prototype.phase_policy", None)
            left = {k: v for k, v in final.items()}
            right = params
            fprov = {
                k: deepcopy(v)
                for k, v in final_ir["provenance"].items()
                if k not in {"solver_parameters_sha256", "solver_parameters"}
            }
            oprov = {
                k: deepcopy(v)
                for k, v in proposal["provenance"].items()
                if k not in {"solver_parameters_sha256", "solver_parameters"}
            }
            if jcs_bytes(left) == jcs_bytes(right) and jcs_bytes(fprov) == jcs_bytes(oprov):
                matches.append(proposal)
        return matches[0] if len(matches) == 1 else None
    except (KeyError, TypeError, ValueError):
        return None
