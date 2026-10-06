"""Bounded, versioned persistence integrity for original local proposals."""

from __future__ import annotations

import re
from hashlib import sha256
from typing import Any

from .canonical import CanonicalProfile, canonical_hash, jcs_bytes, validate_ijson
from .validation import SemanticValidator

PROFILE = "PROTOTYPE_PROPOSAL_BUNDLE_V1"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_BUNDLE_FIELDS = {
    "profile",
    "design_spec_sha256",
    "material_profile_sha256",
    "run_config_sha256",
    "search_trace_sha256",
    "proposal_to_final_sha256",
    "final_crochet_ir_sha256",
    "proposal_ir_sha256",
    "candidate_proposals",
}
_LINK_FIELDS = {
    "profile",
    "search_trace_sha256",
    "proposal_crochet_ir_sha256",
    "final_crochet_ir_sha256",
    "phase_policy",
    "counts",
    "proposal_phases",
    "final_phases",
    "verification_state",
    "physical_status",
}


class ProposalBundleIntegrityError(ValueError):
    """Stored proposal evidence is incomplete or internally inconsistent."""


def _fail(reason: str) -> ProposalBundleIntegrityError:
    return ProposalBundleIntegrityError("proposal_bundle." + reason)


def _digest(value: object, reason: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise _fail(reason)
    return value


def _bounded(value: object) -> None:
    pending = [(value, 0)]
    nodes = 0
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > 100_000 or depth > 64:
            raise _fail("input_complexity")
        if isinstance(item, dict):
            if any(not isinstance(key, str) or len(key) > 128 for key in item):
                raise _fail("input_key")
            if len(pending) + len(item) > 100_000 - nodes:
                raise _fail("input_complexity")
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            if len(pending) + len(item) > 100_000 - nodes:
                raise _fail("input_complexity")
            pending.extend((child, depth + 1) for child in item)
        elif isinstance(item, str) and len(item) > 4096:
            raise _fail("input_string")
    try:
        validate_ijson(value)
    except ValueError as error:
        raise _fail("input_json") from error


def _bundle_hash(bundle: dict[str, Any]) -> str:
    _bounded(bundle)
    return sha256(b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + jcs_bytes(bundle)).hexdigest()


def create_proposal_bundle(
    trace: dict[str, Any],
    trace_sha256: str,
    link: dict[str, Any],
    link_sha256: str,
    proposals: list[dict[str, Any]],
    validator: SemanticValidator,
) -> tuple[dict[str, Any], str]:
    _bounded(trace)
    _bounded(link)
    bindings = trace.get("bindings")
    terminal = trace.get("terminal")
    if not isinstance(bindings, dict) or not isinstance(terminal, dict):
        raise _fail("trace_fields")
    hashes = terminal.get("proposal_ir_sha256")
    if not isinstance(hashes, list) or not 1 <= len(hashes) <= 128 or len(hashes) != len(proposals):
        raise _fail("proposal_order")
    _bounded(proposals)
    proposal_hashes = [
        canonical_hash(item, CanonicalProfile.CROCHET_IR, validator=validator) for item in proposals
    ]
    if hashes != proposal_hashes:
        raise _fail("proposal_hashes")
    bundle: dict[str, Any] = {
        "profile": PROFILE,
        "design_spec_sha256": bindings.get("design_spec_sha256"),
        "material_profile_sha256": bindings.get("material_profile_sha256"),
        "run_config_sha256": bindings.get("run_config_sha256"),
        "search_trace_sha256": trace_sha256,
        "proposal_to_final_sha256": link_sha256,
        "final_crochet_ir_sha256": link.get("final_crochet_ir_sha256"),
        "proposal_ir_sha256": proposal_hashes,
        "candidate_proposals": proposals,
    }
    return bundle, _bundle_hash(bundle)


def retained_proposals(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate snapshot provenance and return original proposals; legacy yields []."""
    generation = project.get("generation")
    if not isinstance(generation, dict):
        raise _fail("generation")
    has_bundle = "proposal_bundle" in generation
    has_digest = "proposal_bundle_sha256" in generation
    if not has_bundle and not has_digest:
        return []
    if not has_bundle or not has_digest:
        raise _fail("partial")
    bundle = generation["proposal_bundle"]
    if (
        not isinstance(bundle, dict)
        or set(bundle) != _BUNDLE_FIELDS
        or bundle.get("profile") != PROFILE
    ):
        raise _fail("fields")
    trace = generation.get("search_trace")
    link = generation.get("proposal_to_final")
    design, material, ir = (
        project.get("design_spec"),
        project.get("material_profile"),
        project.get("crochet_ir"),
    )
    run_config = project.get("run_config")
    for value in (bundle, trace, link, design, material, ir, run_config):
        _bounded(value)
    bundle_hash = _digest(generation.get("proposal_bundle_sha256"), "digest")
    candidate_values = bundle.get("candidate_proposals")
    proposal_values = bundle.get("proposal_ir_sha256")
    if (
        not isinstance(candidate_values, list)
        or not 1 <= len(candidate_values) <= 128
        or not isinstance(proposal_values, list)
        or len(proposal_values) != len(candidate_values)
    ):
        raise _fail("proposal_order")
    for key in (
        "design_spec_sha256",
        "material_profile_sha256",
        "run_config_sha256",
        "search_trace_sha256",
        "proposal_to_final_sha256",
        "final_crochet_ir_sha256",
    ):
        _digest(bundle.get(key), "bundle_identity")
    for item in proposal_values:
        _digest(item, "proposal_hash")
    if _bundle_hash(bundle) != bundle_hash:
        raise _fail("digest_mismatch")

    trace_hash = _digest(generation.get("search_trace_sha256"), "trace_digest")
    if (
        not isinstance(trace, dict)
        or sha256(b"Crochet.AI\0ANALYTIC_SEARCH_TRACE_V1\0" + jcs_bytes(trace)).hexdigest()
        != trace_hash
        or bundle["search_trace_sha256"] != trace_hash
    ):
        raise _fail("trace_binding")
    bindings = trace.get("bindings")
    terminal = trace.get("terminal")
    if not isinstance(bindings, dict) or not isinstance(terminal, dict):
        raise _fail("trace_fields")
    for key in ("design_spec_sha256", "material_profile_sha256", "run_config_sha256"):
        if _digest(bindings.get(key), "trace_binding") != bundle[key]:
            raise _fail("trace_binding")
    hashes = terminal.get("proposal_ir_sha256")
    proposals = bundle["candidate_proposals"]
    if (
        not isinstance(hashes, list)
        or not isinstance(proposals, list)
        or hashes != bundle["proposal_ir_sha256"]
        or len(hashes) != len(proposals)
    ):
        raise _fail("proposal_order")

    link_hash = _digest(generation.get("proposal_to_final_sha256"), "link_digest")
    if (
        not isinstance(link, dict)
        or set(link) != _LINK_FIELDS
        or link.get("profile") != "PROTOTYPE_GENERATION_LINK_V1"
    ):
        raise _fail("link_fields")
    if (
        sha256(b"Crochet.AI\0PROTOTYPE_GENERATION_LINK_V1\0" + jcs_bytes(link)).hexdigest()
        != link_hash
    ):
        raise _fail("link_digest_mismatch")
    final_hash = _digest(project.get("project_id"), "project_id")
    if (
        bundle["proposal_to_final_sha256"] != link_hash
        or link.get("search_trace_sha256") != trace_hash
        or link.get("final_crochet_ir_sha256") != final_hash
        or bundle["final_crochet_ir_sha256"] != final_hash
        or project.get("source_crochet_ir_sha256") != final_hash
    ):
        raise _fail("final_binding")
    if not isinstance(design, dict) or not isinstance(material, dict) or not isinstance(ir, dict):
        raise _fail("project_fields")
    if not isinstance(run_config, dict):
        raise _fail("run_config")
    try:
        design_id, material_id = design["design_spec_id"], material["profile_id"]
        if not isinstance(design_id, str) or not isinstance(material_id, str):
            raise _fail("project_identity")
        validator = SemanticValidator(
            design_specs={design_id: design},
            material_profiles={material_id: material},
        )
        if (
            canonical_hash(design, CanonicalProfile.DESIGN_SPEC, validator=validator)
            != bundle["design_spec_sha256"]
        ):
            raise _fail("design_binding")
        if (
            canonical_hash(material, CanonicalProfile.MATERIAL_PROFILE, validator=validator)
            != bundle["material_profile_sha256"]
        ):
            raise _fail("material_binding")
        if canonical_hash(ir, CanonicalProfile.CROCHET_IR, validator=validator) != final_hash:
            raise _fail("final_hash")
    except ProposalBundleIntegrityError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise _fail("canonical_artifact") from error
    flat_config: dict[str, Any] = {}
    for key, value in run_config.items():
        if key == "phase_policy":
            continue
        if isinstance(value, dict):
            flat_config.update({f"{key}.{nested}": item for nested, item in value.items()})
        else:
            flat_config[key] = value
    config_hash = sha256(
        b"Crochet.AI\0ANALYTIC_SEARCH_RUN_CONFIG_V1\0"
        + jcs_bytes([[key, value] for key, value in sorted(flat_config.items())])
    ).hexdigest()
    if config_hash != bundle["run_config_sha256"]:
        raise _fail("run_config_binding")
    proposal_hashes: list[str] = []
    try:
        for proposal in proposals:
            if not isinstance(proposal, dict):
                raise _fail("proposal_type")
            proposal_hashes.append(
                canonical_hash(proposal, CanonicalProfile.CROCHET_IR, validator=validator)
            )
    except ProposalBundleIntegrityError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise _fail("proposal_canonical") from error
    if (
        proposal_hashes != hashes
        or not proposals
        or link.get("proposal_crochet_ir_sha256") != hashes[0]
    ):
        raise _fail("proposal_binding")
    counts, phases, final_phases = (
        link.get("counts"),
        link.get("proposal_phases"),
        link.get("final_phases"),
    )
    if (
        not isinstance(counts, list)
        or not counts
        or len(counts) > 512
        or any(type(count) is not int or count <= 0 for count in counts)
        or not isinstance(phases, list)
        or len(phases) != len(counts) - 1
        or any(type(phase) is not int or not 0 <= phase < 512 for phase in phases)
        or not isinstance(final_phases, list)
        or len(final_phases) != len(counts) - 1
        or any(type(phase) is not int or phase != 0 for phase in final_phases)
        or run_config.get("phase_policy") != link.get("phase_policy")
    ):
        raise _fail("link_schedule")
    hypotheses = trace.get("hypotheses")
    matching = (
        [
            item
            for item in hypotheses
            if isinstance(item, dict) and item.get("proposal_ir_sha256") == hashes[0]
        ]
        if isinstance(hypotheses, list)
        else []
    )
    if len(matching) != 1:
        raise _fail("trace_selected_proposal")
    phase_record = matching[0].get("phase")
    if (
        matching[0].get("counts") != counts
        or not isinstance(phase_record, dict)
        or phase_record.get("phases") != phases
        or not isinstance(matching[0].get("counts"), list)
        or any(type(count) is not int for count in matching[0]["counts"])
        or not isinstance(phase_record.get("phases"), list)
        or any(type(phase) is not int for phase in phase_record["phases"])
    ):
        raise _fail("trace_selected_schedule")
    courses = project.get("courses")
    if (
        not isinstance(courses, list)
        or len(courses) != len(counts)
        or any(not isinstance(course, dict) for course in courses)
        or any(type(course.get("total_stitches")) is not int for course in courses)
        or [course["total_stitches"] for course in courses] != counts
    ):
        raise _fail("final_course_counts")
    if (
        link.get("phase_policy") != "FIXED_ZERO_CONTINUOUS_V1"
        or link.get("verification_state") != "NOT_VERIFIED"
        or link.get("physical_status") != "UNTESTED"
    ):
        raise _fail("link_policy")
    return proposals
