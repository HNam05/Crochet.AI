"""Independent checks of the prototype's human work order and schematic units."""

from __future__ import annotations

import math
import subprocess
from typing import Any

import pytest

from crochet_ai.prototype_backend import LocalPrototype
from crochet_ai.prototype_storage import PrototypeStore


@pytest.fixture(scope="module")
def trial(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True,
    ).stdout.strip()
    with_store = PrototypeStore(tmp_path_factory.mktemp("human-work-order"))
    try:
        return LocalPrototype(with_store, commit).generate({
            "prototype_version": "1.0.0", "shape": "sphere",
            "diameter_mm": 40, "height_mm": 40,
            "stitches_per_100mm": 25, "courses_per_100mm": 28,
            "hook_diameter_mm": 3, "yarn_label": "Acceptance demonstration",
            "color_hex": "#B88757", "uncertainty_percent": 10,
        })
    finally:
        with_store.close()


def test_continuous_hand_work_never_skips_or_reorders_input_bases(trial: dict[str, Any]) -> None:
    ir = trial["crochet_ir"]
    events = {event["event_id"]: event for event in ir["construction_sequence"]}
    stitches = {stitch["stitch_id"]: stitch for stitch in ir["stitches"]}
    frontiers = {frontier["frontier_id"]: frontier for frontier in ir["frontiers"]}
    for course in ir["courses"]:
        bases = [
            location
            for event_id in course["member_event_ids"]
            for location in stitches[events[event_id]["subject_ref"]["stitch_id"]][
                "base_attachment_location_ids"
            ]
        ]
        assert bases == frontiers[course["input_frontier_ids"][0]]["attachment_location_ids"]


def test_live_counter_counts_tops_instead_of_compound_instruction_nodes(
    trial: dict[str, Any],
) -> None:
    saw_increase = saw_decrease = False
    for course in trial["courses"]:
        after = 0
        for step in trial["steps"]:
            if step["course_id"] != course["course_id"]:
                continue
            arity = (len(step["base_location_ids"]), len(step["top_location_ids"]))
            assert arity in {(1, 1), (1, 2), (2, 1)}
            saw_increase |= arity == (1, 2)
            saw_decrease |= arity == (2, 1)
            after += arity[1]
            assert step["produced_stitches"] == arity[1]
            assert step["course_stitches_after"] == after
        assert after == course["total_stitches"]
    assert saw_increase and saw_decrease


def test_schematic_uses_independent_stitch_and_course_pitch(trial: dict[str, Any]) -> None:
    assert trial["preview"]["role"] == "ILLUSTRATIVE_NOT_PHYSICAL"
    for course in trial["courses"]:
        points = [p for p in trial["preview"]["points"] if p["course_id"] == course["course_id"]]
        assert len(points) == course["total_stitches"]
        for point in points:
            x, y, z = point["xyz_mm"]
            assert math.hypot(x, z) * math.tau == pytest.approx(len(points) * 4)
            assert y == pytest.approx(course["number"] * 100 / 28)
    assert trial["verification_state"] == "NOT_VERIFIED"
    assert trial["physical_status"] == "UNTESTED"


def test_ring_is_one_preparation_then_separate_stitches_and_a_closure(
    trial: dict[str, Any],
) -> None:
    steps = trial["steps"]
    ring, close = steps[0], steps[-1]
    assert ring["kind"] == "MAGIC_RING"
    assert close["kind"] == "CLOSE"
    assert ring["course_id"] is close["course_id"] is None
    assert ring["course_number"] is close["course_number"] is None
    assert "Fadenring" in ring["instruction_de"]
    assert all("denselben Fadenring" in step["instruction_de"] for step in steps[1:7])
    assert len({step["step_id"] for step in steps}) == len(steps)
