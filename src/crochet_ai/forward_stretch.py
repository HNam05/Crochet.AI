"""Experimental target-free preparation of anisotropic stretch terms.

This is a stretch-term prototype, not an F0 simulator. It assigns no
coordinates and makes no convergence, geometry, or verification claim.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass

from .forward_graph import ForwardGraph, StitchMaterialResponse
from .forward_inputs import ForwardInputs


class ForwardStretchError(ValueError):
    """Invalid or ambiguous graph-to-stretch-term mapping."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class StretchTerm:
    edge_type: str
    source_location_id: str
    target_location_id: str
    rest_length_mm: float
    stiffness_n_per_mm: float
    response_id: str


@dataclass(frozen=True, slots=True)
class ForwardStretchTerms:
    """Prepared experimental stretch terms; this is not a simulation result."""

    status: str
    projection_sha256: str
    material_sha256: str
    forward_inputs_sha256: str
    terms: tuple[StretchTerm, ...]


def prepare_stretch_terms(graph: ForwardGraph, inputs: ForwardInputs) -> ForwardStretchTerms:
    """Prepare target-free COURSE and limited WALE rest-length terms.

    COURSE terms use source top-loop stitch pitch and course stiffness. WALE
    terms include only plain 1-to-1 top-loop incidences; magic-ring anchors are
    omitted because the interior stitch gauge is not assumed to transfer to
    the ring. Non-plain shaping is rejected before any term is returned.
    """

    if not isinstance(graph, ForwardGraph):
        raise ForwardStretchError("stretch.graph_type")
    if not isinstance(inputs, ForwardInputs):
        raise ForwardStretchError("stretch.inputs_type")
    course_stiffness = _positive_finite(inputs.stiffness_course_n_per_mm, "course_stiffness")
    wale_stiffness = _positive_finite(inputs.stiffness_wale_n_per_mm, "wale_stiffness")
    if any(group.shaping != "PLAIN" for group in graph.shaping_groups):
        raise ForwardStretchError("stretch.unsupported_shaping")

    nodes: dict[str, str] = {}
    for node in graph.nodes:
        if node.attachment_location_id in nodes:
            raise ForwardStretchError("stretch.ambiguous_node")
        nodes[node.attachment_location_id] = node.location_type

    top_owners: dict[str, list[str]] = defaultdict(list)
    shaping_by_id = {}
    for group in graph.shaping_groups:
        if group.stitch_id in shaping_by_id:
            raise ForwardStretchError("stretch.ambiguous_shaping_group")
        shaping_by_id[group.stitch_id] = group
        if (
            group.shaping != "PLAIN"
            or group.base_arity != 1
            or group.top_arity != 1
            or len(group.base_attachment_location_ids) != 1
            or len(group.top_attachment_location_ids) != 1
        ):
            raise ForwardStretchError("stretch.unsupported_shaping")
        top_owners[group.top_attachment_location_ids[0]].append(group.stitch_id)

    for location_id, owners in top_owners.items():
        if len(owners) != 1 or nodes.get(location_id) != "TOP_LOOP":
            raise ForwardStretchError("stretch.ambiguous_top_producer")
    if any(
        location_type == "TOP_LOOP" and len(top_owners.get(location_id, [])) != 1
        for location_id, location_type in nodes.items()
    ):
        raise ForwardStretchError("stretch.ambiguous_top_producer")

    responses = {}
    for response in graph.material_responses:
        if response.stitch_id in responses:
            raise ForwardStretchError("stretch.ambiguous_material_response")
        responses[response.stitch_id] = response

    terms: list[StretchTerm] = []
    for edge in graph.edges:
        if edge.edge_type == "COURSE":
            if nodes.get(edge.source_location_id) != "TOP_LOOP":
                raise ForwardStretchError("stretch.course_source_not_top_loop")
            if nodes.get(edge.target_location_id) != "TOP_LOOP":
                raise ForwardStretchError("stretch.course_target_not_top_loop")
            source_stitch = _unique_owner(top_owners, edge.source_location_id)
            response = _response_for(responses, source_stitch)
            terms.append(
                StretchTerm(
                    "COURSE",
                    edge.source_location_id,
                    edge.target_location_id,
                    _positive_finite(response.effective_stitch_pitch_mm, "stitch_pitch"),
                    course_stiffness,
                    response.response_id,
                )
            )
        elif edge.edge_type == "WALE":
            edge_group = shaping_by_id.get(edge.stitch_id or "")
            if edge_group is None or (
                edge_group.base_attachment_location_ids[0] != edge.source_location_id
                or edge_group.top_attachment_location_ids[0] != edge.target_location_id
            ):
                raise ForwardStretchError("stretch.wale_producer_mismatch")
            source_kind = nodes.get(edge.source_location_id)
            if source_kind == "MAGIC_RING_ANCHOR":
                if nodes.get(edge.target_location_id) != "TOP_LOOP":
                    raise ForwardStretchError("stretch.wale_target_not_top_loop")
                continue
            if source_kind != "TOP_LOOP" or nodes.get(edge.target_location_id) != "TOP_LOOP":
                raise ForwardStretchError("stretch.wale_not_top_to_top")
            response = _response_for(responses, edge_group.stitch_id)
            terms.append(
                StretchTerm(
                    "WALE",
                    edge.source_location_id,
                    edge.target_location_id,
                    _positive_finite(response.effective_course_pitch_mm, "course_pitch"),
                    wale_stiffness,
                    response.response_id,
                )
            )
        else:
            raise ForwardStretchError("stretch.unsupported_edge_type")

    terms.sort(
        key=lambda term: (
            term.edge_type,
            term.source_location_id,
            term.target_location_id,
            term.response_id,
        )
    )
    return ForwardStretchTerms(
        "EXPERIMENTAL_STRETCH_TERMS",
        graph.projection_sha256,
        graph.material_sha256,
        inputs.sha256,
        tuple(terms),
    )


def _unique_owner(top_owners: dict[str, list[str]], location_id: str) -> str:
    owners = top_owners.get(location_id, [])
    if len(owners) != 1:
        raise ForwardStretchError("stretch.ambiguous_top_producer")
    return owners[0]


def _response_for(
    responses: dict[str, StitchMaterialResponse], stitch_id: str
) -> StitchMaterialResponse:
    response = responses.get(stitch_id)
    if response is None:
        raise ForwardStretchError("stretch.material_response_missing")
    return response


def _positive_finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ForwardStretchError(f"stretch.{name}_invalid")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ForwardStretchError(f"stretch.{name}_invalid")
    return number


def _stretch_energy_n_mm(
    terms: tuple[StretchTerm, ...],
    coordinates_mm: Mapping[str, tuple[float, ...]],
) -> float:
    """Pure synthetic-coordinate spring energy helper for unit tests only."""

    energy = 0.0
    dimension: int | None = None
    for term in terms:
        try:
            source = coordinates_mm[term.source_location_id]
            target = coordinates_mm[term.target_location_id]
        except KeyError as error:
            raise ForwardStretchError("stretch.coordinate_missing") from error
        if len(source) not in (2, 3) or len(target) != len(source):
            raise ForwardStretchError("stretch.coordinate_dimension")
        if dimension is not None and dimension != len(source):
            raise ForwardStretchError("stretch.coordinate_dimension")
        dimension = len(source)
        if any(not math.isfinite(value) for value in (*source, *target)):
            raise ForwardStretchError("stretch.coordinate_non_finite")
        rest = _positive_finite(term.rest_length_mm, "rest_length")
        stiffness = _positive_finite(term.stiffness_n_per_mm, "stiffness")
        distance = math.sqrt(
            sum((right - left) ** 2 for left, right in zip(source, target, strict=True))
        )
        energy += 0.5 * stiffness * (distance - rest) ** 2
    if not math.isfinite(energy):
        raise ForwardStretchError("stretch.energy_non_finite")
    return energy
