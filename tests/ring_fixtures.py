"""Independent ring fixtures: no production parser, exporter, or solver helpers."""

from copy import deepcopy
from typing import Any

from conftest import make_closed_ir


def make_multi_ring_ir(count: int = 6) -> dict[str, Any]:
    template = make_closed_ir()
    value = deepcopy(template)
    value["schema_version"] = "1.1.0"
    value["semantics_profile"] = "CROCHET_CORE_1.1.0"
    value["required_capabilities"].append("MULTI_STITCH_RING_V1")
    ring = value["construction_operations"][0]
    close = value["construction_operations"][1]
    sites = [f"loc_ring_{index}" for index in range(count)]
    ring["attachment_location_ids"] = sites
    ring_subject = {"entity_type": "CONSTRUCTION_OPERATION", "operation_id": ring["operation_id"]}
    value["attachment_locations"] = [
        {
            "attachment_location_id": site,
            "location_type": "MAGIC_RING_ANCHOR",
            "producer_ref": ring_subject,
            "ordinal_within_producer": index,
        }
        for index, site in enumerate(sites)
    ]
    initial = deepcopy(template["frontiers"][0])
    initial["attachment_location_ids"] = sites
    initial["anchor_attachment_location_id"] = sites[0]
    value["frontiers"] = [initial]
    create = deepcopy(template["frontier_transitions"][0])
    create["created_attachment_location_ids"] = sites
    value["frontier_transitions"] = [create]
    value["construction_sequence"] = [deepcopy(template["construction_sequence"][0])]
    value["stitches"] = []
    value["derivations"] = [
        item
        for item in value["derivations"]
        if item["derivation_id"]
        in {ring["derivation_id"], close["derivation_id"], value["courses"][0]["derivation_id"]}
    ]
    event_ids: list[str] = []
    live = list(sites)
    previous = initial["frontier_id"]
    for index, site in enumerate(sites):
        sid, lid = f"st_ring_{index}", f"loc_top_{index}"
        fid, tid, eid = f"frontier_ring_{index}", f"ftrans_ring_{index}", f"ev_ring_{index}"
        subject = {"entity_type": "STITCH", "stitch_id": sid}
        stitch = deepcopy(template["stitches"][0])
        stitch.update(
            stitch_id=sid,
            base_attachment_location_ids=[site],
            top_attachment_location_ids=[lid],
            derivation_id=f"deriv_ring_{index}",
        )
        stitch["frontier_edit"]["frontier_id"] = previous
        value["stitches"].append(stitch)
        value["attachment_locations"].append(
            {
                "attachment_location_id": lid,
                "location_type": "TOP_LOOP",
                "producer_ref": subject,
                "ordinal_within_producer": 0,
            }
        )
        live = [*live[:index], lid, *live[index + 1 :]]
        frontier = deepcopy(template["frontiers"][1])
        frontier.update(
            frontier_id=fid,
            attachment_location_ids=list(live),
            anchor_attachment_location_id=live[0],
            created_by_transition_id=tid,
        )
        value["frontiers"].append(frontier)
        transition = deepcopy(template["frontier_transitions"][1])
        transition.update(
            frontier_transition_id=tid,
            transition_index=index + 1,
            after_event_index=index + 1,
            caused_by_subject_ref=subject,
            input_frontier_ids=[previous],
            output_frontier_ids=[fid],
            retired_attachment_location_ids=[site],
            created_attachment_location_ids=[lid],
        )
        value["frontier_transitions"].append(transition)
        event = deepcopy(template["construction_sequence"][1])
        event.update(
            event_id=eid,
            sequence_index=index + 1,
            subject_ref=subject,
            frontier_transition_ids=[tid],
        )
        value["construction_sequence"].append(event)
        event_ids.append(eid)
        derivation = deepcopy(
            next(
                item
                for item in template["derivations"]
                if item["derivation_id"] == template["stitches"][0]["derivation_id"]
            )
        )
        derivation.update(derivation_id=f"deriv_ring_{index}", subject_refs=[subject])
        value["derivations"].append(derivation)
        previous = fid
    close["input_frontier_ids"] = [previous]
    close_transition = deepcopy(template["frontier_transitions"][-1])
    close_transition.update(
        transition_index=count + 1,
        after_event_index=count + 1,
        input_frontier_ids=[previous],
        retired_attachment_location_ids=list(live),
    )
    value["frontier_transitions"].append(close_transition)
    value["frontiers"].append(deepcopy(template["frontiers"][-1]))
    close_event = deepcopy(template["construction_sequence"][-1])
    close_event["sequence_index"] = count + 1
    value["construction_sequence"].append(close_event)
    value["courses"][0]["member_event_ids"] = event_ids
    value["courses"][0]["output_frontier_ids"] = [previous]
    value["yarn_paths"][0]["segments"][0]["event_ids"] = [*event_ids, close_event["event_id"]]
    return value
