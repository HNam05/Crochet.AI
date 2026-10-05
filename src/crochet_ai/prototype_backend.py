"""Local human-test generation service; keeps candidate generation and evidence separate."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from threading import Lock
from typing import Any
from uuid import uuid4

from .analytic_compile import CompileProvenance, compile_closed_schedule
from .analytic_solver import AnalyticRunConfig, generate_analytic
from .canonical import CanonicalProfile, canonical_hash, jcs_bytes
from .cli import _provenance
from .json_types import JSONValue
from .pattern import TerminologyProfile, export_pattern, verify_semantic_round_trip
from .pattern_context import PatternParseContext, PatternYarnBinding
from .prototype_input import PROTOTYPE_VERSION, assemble_request
from .prototype_presentation import present_ir
from .prototype_storage import PrototypeStore
from .schema import validate_schema
from .validation import SemanticValidator


def _wire_config(config: AnalyticRunConfig) -> dict[str, Any]:
    value = asdict(config)
    value["minimum_shaping_separation_turns"] = (
        f"{config.minimum_shaping_separation_turns.numerator}/"
        f"{config.minimum_shaping_separation_turns.denominator}"
    )
    return value


class LocalPrototype:
    def __init__(self, store: PrototypeStore, software_commit: str) -> None:
        self.store = store
        self.provenance = _provenance(software_commit)
        self.generation_lock = Lock()

    def generate(self, request: object) -> dict[str, Any]:
        if not self.generation_lock.acquire(blocking=False):
            raise RuntimeError("E_BUSY")
        try:
            design, material, config = assemble_request(
                request, software_commit=self.provenance.software_commit, working_tree_dirty=True
            )
            if not isinstance(request, dict):
                raise ValueError("request.fields")
            for kind, value in (("design_spec", design), ("material_profile", material)):
                report = validate_schema(kind, value)
                if not report.ok:
                    raise ValueError(f"request.{kind}_invalid")
            validator = SemanticValidator(
                material_profiles={material["profile_id"]: material},
                design_specs={design["design_spec_id"]: design},
            )
            batch = generate_analytic(design, material, config, self.provenance)
            if batch.status.value != "CANDIDATES_EMITTED" or len(batch.candidates) != 1:
                raise RuntimeError(f"generation.{batch.status.value}.{batch.reason}")
            if batch.search_trace is None:
                raise RuntimeError("generation.search_trace_missing")
            proposal = batch.candidates[0].crochet_ir.to_dict()
            counts = batch.candidates[0].count_search.counts
            proposal_provenance = proposal["provenance"]
            if not isinstance(proposal_provenance, dict):
                raise RuntimeError("generation.proposal_provenance")
            parameters = proposal_provenance["solver_parameters"]
            if not isinstance(parameters, list):
                raise RuntimeError("generation.proposal_parameters")
            proposal_parameters: list[tuple[str, str | int | float | bool]] = []
            for parameter in parameters:
                if not isinstance(parameter, dict):
                    raise RuntimeError("generation.proposal_parameter")
                name, parameter_value = parameter["name"], parameter["value"]
                if not isinstance(name, str) or not isinstance(parameter_value, (str, int, float)):
                    raise RuntimeError("generation.proposal_parameter")
                if name != "source_snapshot_sha256":
                    proposal_parameters.append((name, parameter_value))
            final_provenance = CompileProvenance(
                self.provenance.software_commit,
                self.provenance.source_snapshot_sha256,
                (
                    *proposal_parameters,
                    ("prototype.phase_policy", "FIXED_ZERO_CONTINUOUS_V1"),
                    ("prototype.count_schedule", ",".join(str(count) for count in counts)),
                    ("prototype.final_phases", ",".join("0" for _ in range(len(counts) - 1))),
                ),
            )
            ir = compile_closed_schedule(
                design,
                material,
                counts,
                (0,) * (len(counts) - 1),
                final_provenance,
                max_stitches=config.max_stitches,
            )
            validated = validator.validate_crochet_ir(ir)
            if not validated.ok:
                raise RuntimeError("generation.semantic_validation")
            source_sha = canonical_hash(ir, CanonicalProfile.CROCHET_IR, validator=validator)
            generation_link: dict[str, JSONValue] = {
                "profile": "PROTOTYPE_GENERATION_LINK_V1",
                "search_trace_sha256": batch.search_trace.sha256,
                "proposal_crochet_ir_sha256": canonical_hash(
                    proposal, CanonicalProfile.CROCHET_IR, validator=validator,
                ),
                "final_crochet_ir_sha256": source_sha,
                "phase_policy": "FIXED_ZERO_CONTINUOUS_V1",
                "counts": list(counts),
                "proposal_phases": list(batch.candidates[0].placement.phases),
                "final_phases": [0] * (len(counts) - 1),
                "verification_state": "NOT_VERIFIED",
                "physical_status": "UNTESTED",
            }
            generation_link_sha256 = sha256(
                b"Crochet.AI\0PROTOTYPE_GENERATION_LINK_V1\0" + jcs_bytes(generation_link)
            ).hexdigest()
            color = design["colors"][0]
            context = PatternParseContext(
                design,
                (PatternYarnBinding("Yarn A", material, color["label"], color["srgb_hex"]),),
            )
            round_trip = verify_semantic_round_trip(
                ir, TerminologyProfile.DE_DE, context=context, validator=validator
            )
            if not round_trip.ok:
                raise RuntimeError("generation.export_round_trip")
            pattern = export_pattern(ir, TerminologyProfile.DE_DE, validator=validator)
            gauge = material["calibration_responses"][0]["effective_gauge"]
            project = present_ir(
                ir,
                request["color_hex"],
                {"revision": 0, "cursor": 0},
                gauge["effective_stitch_pitch_mm"],
                gauge["effective_course_pitch_mm"],
                source_sha,
            )
            project.update(
                {
                    "request": request,
                    "design_spec": design,
                    "material_profile": material,
                    "run_config": {
                        **_wire_config(config),
                        "phase_policy": "FIXED_ZERO_CONTINUOUS_V1",
                    },
                    "pattern_text": pattern,
                    "source_crochet_ir_sha256": source_sha,
                    "project_id": source_sha,
                    "generation": {
                        "status": batch.status.value,
                        "reason": batch.reason,
                        "search_trace": batch.search_trace.to_dict(),
                        "search_trace_sha256": batch.search_trace.sha256,
                        "proposal_to_final": generation_link,
                        "proposal_to_final_sha256": generation_link_sha256,
                        "work": {
                            "count_transitions": batch.count_transition_evaluations,
                            "placement_transitions": batch.placement_transition_evaluations,
                            "placement_pairs": batch.placement_pair_evaluations,
                            "proposal_phases": list(batch.candidates[0].placement.phases),
                            "selected_phase_policy": "FIXED_ZERO_CONTINUOUS_V1",
                        },
                    },
                }
            )
            return self.store.save_project(project, datetime.now(UTC).isoformat())
        finally:
            self.generation_lock.release()

    def feedback_record(self, body: object) -> dict[str, Any]:
        required = {
            "prototype_version",
            "project_id",
            "outcome",
            "notes",
            "actual_diameter_mm",
            "actual_height_mm",
        }
        if (
            not isinstance(body, dict)
            or set(body) != required
            or body["prototype_version"] != PROTOTYPE_VERSION
        ):
            raise ValueError("feedback.fields")
        if not isinstance(body["project_id"], str):
            raise ValueError("feedback.project_id")
        project = self.store.get_project(body["project_id"])
        if project is None:
            raise KeyError("project.not_found")
        if not isinstance(body["outcome"], str) or body["outcome"] not in {
            "WORKED",
            "NEEDS_CHANGES",
            "NOT_FINISHED",
        }:
            raise ValueError("feedback.outcome")
        if not isinstance(body["notes"], str) or len(body["notes"]) > 4000:
            raise ValueError("feedback.notes")
        measurements: dict[str, float | None] = {}
        for field in ("actual_diameter_mm", "actual_height_mm"):
            value = body[field]
            if value is not None and (type(value) not in {int, float} or not 0 < value <= 1000):
                raise ValueError(f"feedback.{field}")
            measurements[field] = value
        record = {
            "feedback_id": f"feedback_{uuid4().hex}",
            "created_at": datetime.now(UTC).isoformat(),
            "project_id": project["project_id"],
            "source_crochet_ir_sha256": project["source_crochet_ir_sha256"],
            "outcome": body["outcome"],
            "notes": body["notes"],
            **measurements,
            "review_state": "HUMAN_FEEDBACK_UNREVIEWED",
        }
        return self.store.add_feedback(record)
