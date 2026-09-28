"""Target-free construction boundary for future independent forward simulation.

This module does not import generator, placement, target geometry or Pattern V1
code. It produces no geometry and makes no convergence or physical claim.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from .canonical import CanonicalProfile, canonical_hash, jcs_bytes, parse_json
from .diagnostics import ArtifactValidationError
from .validation import SemanticValidator

PROFILE = "FORWARD_PHYSICAL_SEMANTICS_V1"


class PhysicalProjectionError(ValueError):
    """Invalid or unsupported forward construction, never a failed simulation."""


# An explicit allowlist: additions to CrochetIR cannot silently enter simulation.
# Nested objects have closed schemas in the validated source contract.
_FIELDS = {
    "yarns": ("yarn_id", "material_profile_ref"),
    "attachment_locations": (
        "attachment_location_id",
        "location_type",
        "producer_ref",
        "ordinal_within_producer",
    ),
    "stitches": (
        "stitch_id",
        "stitch_type",
        "shaping",
        "base_arity",
        "top_arity",
        "base_attachment_location_ids",
        "top_attachment_location_ids",
        "frontier_edit",
        "yarn_id",
        "course_id",
    ),
    "construction_operations": (
        "operation_id",
        "operation_type",
        "input_frontier_ids",
        "output_frontier_ids",
        "attachment_location_ids",
        "join_input_mappings",
        "input_yarn_ids",
        "output_yarn_ids",
        "opening_id",
        "join_method",
    ),
    "construction_sequence": (
        "event_id",
        "sequence_index",
        "subject_ref",
        "active_yarn_id_before",
        "active_yarn_id_after",
        "frontier_transition_ids",
    ),
    "courses": (
        "course_id",
        "ordinal",
        "component_id",
        "branch_id",
        "course_form",
        "turn_mode",
        "work_direction",
        "member_event_ids",
        "input_frontier_ids",
        "output_frontier_ids",
    ),
    "frontiers": (
        "frontier_id",
        "component_id",
        "branch_id",
        "topology",
        "lifecycle_state",
        "attachment_location_ids",
        "anchor_attachment_location_id",
        "active_yarn_id",
        "created_by_transition_id",
    ),
    "frontier_transitions": (
        "frontier_transition_id",
        "transition_index",
        "after_event_index",
        "caused_by_subject_ref",
        "transition_type",
        "input_frontier_ids",
        "output_frontier_ids",
        "retired_attachment_location_ids",
        "created_attachment_location_ids",
        "reserved_attachment_location_ids",
        "opening_id",
    ),
    "branches": (
        "branch_id",
        "component_id",
        "parent_branch_ids",
        "created_by_transition_id",
        "course_ids",
        "entry_frontier_ids",
        "terminal_frontier_ids",
    ),
    "components": (
        "component_id",
        "branch_ids",
        "initial_frontier_ids",
        "terminal_frontier_ids",
    ),
    "openings": (
        "opening_id",
        "component_id",
        "declared_by_operation_id",
        "boundary_attachment_location_ids",
        "closure_expectation",
    ),
    "yarn_paths": ("yarn_path_id", "yarn_id", "segments"),
}


@dataclass(frozen=True, slots=True, init=False)
class PhysicalSemanticProjection:
    """Immutable bytes, constructible only through source validation and projection.

    The validator is an admission boundary, not a simulator dependency. Only this
    object's bytes, not its enclosing IR hash or validator, may enter simulation.
    No raw projection payload, solver seed or target argument is accepted.
    """

    canonical_bytes: bytes
    sha256: str

    def __init__(
        self,
        crochet_ir: dict[str, Any],
        material: dict[str, Any],
        *,
        validator: SemanticValidator,
    ) -> None:
        for report in (
            validator.validate_material_profile(material),
            validator.validate_crochet_ir(crochet_ir),
        ):
            if not report.ok:
                raise ArtifactValidationError(report)
        if (
            len(crochet_ir["components"]) != 1
            or len(crochet_ir["branches"]) != 1
            or len(crochet_ir["yarns"]) != 1
            or crochet_ir["openings"]
            or any(s["stitch_type"] != "SINGLE_CROCHET" for s in crochet_ir["stitches"])
            or any(c["course_form"] != "CYCLIC" for c in crochet_ir["courses"])
            or sorted(o["operation_type"] for o in crochet_ir["construction_operations"])
            != ["CLOSE", "MAGIC_RING"]
        ):
            raise PhysicalProjectionError("physical.unsupported_construction")
        material_hash = canonical_hash(material, CanonicalProfile.MATERIAL_PROFILE)
        expected = {
            "profile_id": material["profile_id"],
            "revision": material["revision"],
            "sha256": material_hash,
        }
        if any(yarn["material_profile_ref"] != expected for yarn in crochet_ir["yarns"]):
            raise PhysicalProjectionError("physical.material_binding")

        # Do not copy the enclosing IR and then delete a blacklist of target fields.
        value: dict[str, Any] = {
            "profile": PROFILE,
            "semantics_profile": crochet_ir["semantics_profile"],
            "units": deepcopy(crochet_ir["units"]),
            "course_order": list(crochet_ir["course_order"]),
        }
        for table, names in _FIELDS.items():
            entries = [{name: deepcopy(row[name]) for name in names} for row in crochet_ir[table]]
            order = (
                "sequence_index"
                if table == "construction_sequence"
                else "transition_index"
                if table == "frontier_transitions"
                else names[0]
            )
            value[table] = sorted(entries, key=lambda row: row[order])
        for branch in value["branches"]:
            branch["parent_branch_ids"] = sorted(branch["parent_branch_ids"])
            branch["course_ids"] = sorted(branch["course_ids"])
        for component in value["components"]:
            component["branch_ids"] = sorted(component["branch_ids"])
        encoded = jcs_bytes(value)
        digest = sha256(b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + encoded).hexdigest()
        object.__setattr__(self, "canonical_bytes", encoded)
        object.__setattr__(self, "sha256", digest)

    def to_dict(self) -> dict[str, Any]:
        value = parse_json(self.canonical_bytes)
        if not isinstance(value, dict):
            raise PhysicalProjectionError("physical.internal_projection_shape")
        return value
