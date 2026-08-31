"""Execution-normalized CrochetIR semantic equivalence."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

from .canonical import CanonicalProfile, jcs_bytes
from .diagnostics import ArtifactValidationError, Diagnostic, FailureCode, ValidationReport
from .schema import artifact_fingerprint
from .validation import SemanticValidator


def _first_use_order(values: list[str | None]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is not None and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _label_map(values: list[str], prefix: str) -> dict[str, str]:
    return {value: f"{prefix}{index}" for index, value in enumerate(values)}


def _id_from_subject_ref(reference: dict[str, Any]) -> str:
    return cast(
        str,
        reference["stitch_id"]
        if reference["entity_type"] == "STITCH"
        else reference["operation_id"],
    )


def _canonical_label_index(label: str) -> int:
    return int(label.rsplit("_", 1)[1])


def _table_label_index(identifier: str, item: dict[str, Any]) -> int:
    return _canonical_label_index(cast(str, item[identifier]))


def _equivalence_failure(value: dict[str, Any], key: str, summary: str) -> ArtifactValidationError:
    return ArtifactValidationError(
        ValidationReport.from_iterable(
            [
                Diagnostic(
                    code=FailureCode.DETERMINISM,
                    gate="V9",
                    message_key=key,
                    summary=summary,
                    artifact_hash=artifact_fingerprint(value),
                )
            ]
        )
    )


def semantic_projection(
    value: dict[str, Any], *, validator: SemanticValidator | None = None
) -> dict[str, Any]:
    active_validator = validator or SemanticValidator()
    report = active_validator.validate_crochet_ir(value)
    if not report.ok:
        raise ArtifactValidationError(report)
    projected = deepcopy(value)
    events = sorted(projected["construction_sequence"], key=lambda item: item["sequence_index"])
    transitions = sorted(
        projected["frontier_transitions"], key=lambda item: item["transition_index"]
    )
    event_map = _label_map([event["event_id"] for event in events], "event_")
    stitch_order: list[str] = []
    operation_order: list[str] = []
    yarn_uses: list[str | None] = []
    opening_order: list[str] = []
    stitches_by_id = {item["stitch_id"]: item for item in projected["stitches"]}
    operations_by_id = {item["operation_id"]: item for item in projected["construction_operations"]}
    for event in events:
        yarn_uses.extend((event["active_yarn_id_before"], event["active_yarn_id_after"]))
        reference = event["subject_ref"]
        if reference["entity_type"] == "STITCH":
            stitch_id = reference["stitch_id"]
            stitch_order.append(stitch_id)
            yarn_uses.append(stitches_by_id[stitch_id]["yarn_id"])
        else:
            operation_id = reference["operation_id"]
            operation_order.append(operation_id)
            operation = operations_by_id[operation_id]
            yarn_uses.extend(operation["input_yarn_ids"])
            yarn_uses.extend(operation["output_yarn_ids"])
            if operation["operation_type"] == "DECLARE_OPENING":
                opening_order.append(operation["opening_id"])
    stitch_map = _label_map(stitch_order, "stitch_")
    operation_map = _label_map(operation_order, "operation_")
    transition_map = _label_map(
        [item["frontier_transition_id"] for item in transitions], "transition_"
    )
    frontier_order: list[str] = []
    for transition in transitions:
        frontier_order.extend(transition["output_frontier_ids"])
    frontier_map = _label_map(frontier_order, "frontier_")
    locations = projected["attachment_locations"]
    locations_by_producer: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for location in locations:
        producer = location["producer_ref"]
        producer_id = (
            producer["stitch_id"]
            if producer["entity_type"] == "STITCH"
            else producer["operation_id"]
        )
        locations_by_producer.setdefault((producer["entity_type"], producer_id), []).append(
            location
        )
    location_order: list[dict[str, Any]] = []
    for event in events:
        reference = event["subject_ref"]
        producer_id = _id_from_subject_ref(reference)
        location_order.extend(
            sorted(
                locations_by_producer.get((reference["entity_type"], producer_id), []),
                key=lambda location: location["ordinal_within_producer"],
            )
        )
    location_map = _label_map(
        [item["attachment_location_id"] for item in location_order], "location_"
    )
    course_map = _label_map(projected["course_order"], "course_")
    frontiers_by_id = {item["frontier_id"]: item for item in projected["frontiers"]}
    courses_by_id = {item["course_id"]: item for item in projected["courses"]}
    component_uses: list[str | None] = []
    branch_uses: list[str | None] = []
    for course_id in projected["course_order"]:
        course = courses_by_id[course_id]
        component_uses.append(course["component_id"])
        branch_uses.append(course["branch_id"])
    for frontier_id in frontier_order:
        frontier = frontiers_by_id[frontier_id]
        component_uses.append(frontier["component_id"])
        branch_uses.append(frontier["branch_id"])
    component_order = _first_use_order(component_uses)
    branch_order = _first_use_order(branch_uses)
    yarn_order = _first_use_order(yarn_uses)
    if set(component_order) != {item["component_id"] for item in projected["components"]}:
        raise _equivalence_failure(
            value,
            "equivalence.unreachable_component",
            "Every component needs a canonical semantic first use",
        )
    if set(branch_order) != {item["branch_id"] for item in projected["branches"]}:
        raise _equivalence_failure(
            value,
            "equivalence.unreachable_branch",
            "Every branch needs a canonical semantic first use",
        )
    if set(yarn_order) != {item["yarn_id"] for item in projected["yarns"]}:
        raise _equivalence_failure(
            value, "equivalence.unreachable_yarn", "Every yarn needs a canonical semantic first use"
        )
    component_map = _label_map(component_order, "component_")
    branch_map = _label_map(branch_order, "branch_")
    yarn_map = _label_map(yarn_order, "yarn_")
    yarns_by_id = {item["yarn_id"]: item for item in projected["yarns"]}
    color_order = _first_use_order([yarns_by_id[yarn_id]["color_id"] for yarn_id in yarn_order])
    if set(color_order) != {item["color_id"] for item in projected["colors"]}:
        raise _equivalence_failure(
            value, "equivalence.unreachable_color", "Every color needs a canonical yarn first use"
        )
    color_map = _label_map(color_order, "color_")
    if set(opening_order) != {item["opening_id"] for item in projected["openings"]}:
        raise _equivalence_failure(
            value,
            "equivalence.unreachable_opening",
            "Every opening needs a declaring operation first use",
        )
    opening_map = _label_map(opening_order, "opening_")
    openings_by_id = {item["opening_id"]: item for item in projected["openings"]}
    requirement_order = _first_use_order(
        [openings_by_id[opening_id]["design_requirement_id"] for opening_id in opening_order]
    )
    requirement_map = _label_map(requirement_order, "opening_requirement_")
    material_order = _first_use_order(
        [yarns_by_id[yarn_id]["material_profile_ref"]["profile_id"] for yarn_id in yarn_order]
    )
    material_map = _label_map(material_order, "material_")
    path_by_yarn = {item["yarn_id"]: item for item in projected["yarn_paths"]}
    path_map = {
        path_by_yarn[yarn_id]["yarn_path_id"]: f"yarn_path_{index}"
        for index, yarn_id in enumerate(yarn_order)
    }
    segment_map: dict[str, str] = {}
    for yarn_index, yarn_id in enumerate(yarn_order):
        for segment_index, segment in enumerate(path_by_yarn[yarn_id]["segments"]):
            segment_map[segment["yarn_segment_id"]] = f"yarn_segment_{yarn_index}_{segment_index}"

    mappings: dict[str, dict[str, str]] = {
        "color_id": color_map,
        "active_color_id_before": color_map,
        "active_color_id_after": color_map,
        "yarn_id": yarn_map,
        "active_yarn_id": yarn_map,
        "active_yarn_id_before": yarn_map,
        "active_yarn_id_after": yarn_map,
        "attachment_location_id": location_map,
        "left_location_id": location_map,
        "right_location_id": location_map,
        "anchor_attachment_location_id": location_map,
        "stitch_id": stitch_map,
        "operation_id": operation_map,
        "start_operation_id": operation_map,
        "end_operation_id": operation_map,
        "declared_by_operation_id": operation_map,
        "event_id": event_map,
        "course_id": course_map,
        "frontier_id": frontier_map,
        "input_frontier_id": frontier_map,
        "frontier_transition_id": transition_map,
        "created_by_transition_id": transition_map,
        "branch_id": branch_map,
        "component_id": component_map,
        "opening_id": opening_map,
        "design_requirement_id": requirement_map,
        "yarn_path_id": path_map,
        "yarn_segment_id": segment_map,
    }
    list_mappings: dict[str, dict[str, str]] = {
        "base_attachment_location_ids": location_map,
        "top_attachment_location_ids": location_map,
        "attachment_location_ids": location_map,
        "consumed_attachment_location_ids": location_map,
        "retired_attachment_location_ids": location_map,
        "created_attachment_location_ids": location_map,
        "reserved_attachment_location_ids": location_map,
        "boundary_attachment_location_ids": location_map,
        "input_frontier_ids": frontier_map,
        "output_frontier_ids": frontier_map,
        "entry_frontier_ids": frontier_map,
        "terminal_frontier_ids": frontier_map,
        "initial_frontier_ids": frontier_map,
        "input_yarn_ids": yarn_map,
        "output_yarn_ids": yarn_map,
        "frontier_transition_ids": transition_map,
        "member_event_ids": event_map,
        "event_ids": event_map,
        "parent_branch_ids": branch_map,
        "course_ids": course_map,
        "course_order": course_map,
        "branch_ids": branch_map,
    }

    def rename(node: Any, parent_key: str | None = None) -> Any:
        if isinstance(node, list):
            mapping = list_mappings.get(parent_key or "")
            return [
                mapping.get(item, item) if mapping and isinstance(item, str) else rename(item)
                for item in node
            ]
        if not isinstance(node, dict):
            return node
        result: dict[str, Any] = {}
        for key, child in node.items():
            if key in {"label", "derivation_id"}:
                continue
            if key == "profile_id" and parent_key == "material_profile_ref":
                result[key] = material_map[child]
            elif key in mappings and child is not None:
                result[key] = mappings[key][child]
            else:
                result[key] = rename(child, key)
        return result

    projected.pop("crochet_ir_id")
    projected.pop("design_spec_ref")
    projected.pop("derivations")
    projected.pop("provenance")
    renamed = rename(projected)
    table_orders: dict[str, tuple[str, dict[str, str]]] = {
        "colors": ("color_id", color_map),
        "yarns": ("yarn_id", yarn_map),
        "attachment_locations": ("attachment_location_id", location_map),
        "stitches": ("stitch_id", stitch_map),
        "construction_operations": ("operation_id", operation_map),
        "courses": ("course_id", course_map),
        "frontiers": ("frontier_id", frontier_map),
        "branches": ("branch_id", branch_map),
        "components": ("component_id", component_map),
        "openings": ("opening_id", opening_map),
        "yarn_paths": ("yarn_path_id", path_map),
    }
    for table, (identifier, _) in table_orders.items():
        renamed[table] = sorted(
            renamed[table], key=lambda item: _table_label_index(identifier, item)
        )
    renamed["construction_sequence"] = sorted(
        renamed["construction_sequence"], key=lambda item: item["sequence_index"]
    )
    renamed["frontier_transitions"] = sorted(
        renamed["frontier_transitions"], key=lambda item: item["transition_index"]
    )
    renamed["required_capabilities"] = sorted(renamed["required_capabilities"])
    for branch in renamed["branches"]:
        branch["parent_branch_ids"] = sorted(branch["parent_branch_ids"])
        branch["course_ids"] = sorted(branch["course_ids"])
    for component in renamed["components"]:
        component["branch_ids"] = sorted(component["branch_ids"])
    return cast(dict[str, Any], renamed)


def semantic_bytes(value: dict[str, Any], *, validator: SemanticValidator | None = None) -> bytes:
    return jcs_bytes(semantic_projection(value, validator=validator))


def semantic_hash(value: dict[str, Any], *, validator: SemanticValidator | None = None) -> str:
    from hashlib import sha256

    payload = (
        b"Crochet.AI\x00"
        + CanonicalProfile.SEMANTIC_EQUIVALENCE.encode("ascii")
        + b"\x00"
        + semantic_bytes(value, validator=validator)
    )
    return sha256(payload).hexdigest()


def are_semantically_equivalent(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    validator: SemanticValidator | None = None,
) -> bool:
    return semantic_bytes(left, validator=validator) == semantic_bytes(right, validator=validator)
