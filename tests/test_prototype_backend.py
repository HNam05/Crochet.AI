from __future__ import annotations

import json
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from crochet_ai.prototype_backend import LocalPrototype
from crochet_ai.prototype_input import assemble_request
from crochet_ai.prototype_server import make_server
from crochet_ai.prototype_storage import PrototypeStore, PrototypeStoreError
from crochet_ai.schema import validate_schema

DEFAULT_REQUEST = {
    "prototype_version": "1.0.0",
    "shape": "sphere",
    "diameter_mm": 40,
    "height_mm": 40,
    "stitches_per_100mm": 25,
    "courses_per_100mm": 28,
    "hook_diameter_mm": 3,
    "yarn_label": "Meine Testwolle",
    "color_hex": "#B88757",
    "uncertainty_percent": 10,
}


def _commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()


def _assemble(request: object) -> tuple[dict, dict, object]:
    return assemble_request(request, software_commit=_commit(), working_tree_dirty=True)


def test_project_generation_is_ir_bound_and_round_trips(tmp_path: Path) -> None:
    store = PrototypeStore(tmp_path)
    project = LocalPrototype(store, _commit()).generate(DEFAULT_REQUEST)
    assert project["semantic_validation"] == project["round_trip_state"] == "PASS"
    assert project["verification_state"] == "NOT_VERIFIED"
    assert project["physical_status"] == "UNTESTED"
    assert project["project_id"] == project["source_crochet_ir_sha256"]
    assert len(project["steps"]) == len(project["crochet_ir"]["construction_sequence"])
    assert [step["event_index"] for step in project["steps"]] == list(range(len(project["steps"])))
    produced = {step["step_id"] for step in project["steps"] for _ in step["top_location_ids"]}
    assert len(project["preview"]["points"]) == sum(
        len(step["top_location_ids"]) for step in project["steps"]
    )
    assert {point["step_id"] for point in project["preview"]["points"]} <= produced
    assert project["courses"][0]["total_stitches"] == 6
    assert project["pattern_text"]
    assert project["run_config"]["phase_policy"] == "FIXED_ZERO_CONTINUOUS_V1"
    assert "Fadenring" in project["steps"][1]["instruction_de"]
    ir = project["crochet_ir"]
    stitches = {item["stitch_id"]: item for item in ir["stitches"]}
    events = {item["event_id"]: item for item in ir["construction_sequence"]}
    frontiers = {item["frontier_id"]: item for item in ir["frontiers"]}
    for course in ir["courses"]:
        input_locations = frontiers[course["input_frontier_ids"][0]]["attachment_location_ids"]
        cursor = 0
        for event_id in course["member_event_ids"]:
            subject = events[event_id]["subject_ref"]
            stitch = stitches[subject["stitch_id"]]
            expected = [
                input_locations[(cursor + offset) % len(input_locations)]
                for offset in range(len(stitch["base_attachment_location_ids"]))
            ]
            assert stitch["base_attachment_location_ids"] == expected
            cursor += len(expected)
    assert project["session"] == {"project_id": project["project_id"], "revision": 0, "cursor": 0}
    store.close()


def test_ellipsoid_and_closed_request_assembly(tmp_path: Path) -> None:
    request = {**DEFAULT_REQUEST, "shape": "ellipsoid", "height_mm": 60}
    design, material, config = _assemble(request)
    assert validate_schema("design_spec", design).ok
    assert validate_schema("material_profile", material).ok
    assert config.min_courses == config.max_courses
    generated = LocalPrototype(PrototypeStore(tmp_path), _commit()).generate(request)
    assert generated["generation"]["status"] == "CANDIDATES_EMITTED"
    assert generated["design_spec"]["target_geometry"]["primitive"] == "ELLIPSOID"
    assert generated["round_trip_state"] == "PASS"
    for key, bad in (("shape", "torus"), ("color_hex", "red"), ("stitches_per_100mm", True)):
        with pytest.raises(ValueError):
            _assemble({**request, key: bad})
    with pytest.raises(ValueError):
        _assemble({**DEFAULT_REQUEST, "surprise": 1})


def test_session_conflicts_feedback_and_restart_persistence(tmp_path: Path) -> None:
    store = PrototypeStore(tmp_path)
    project = LocalPrototype(store, _commit()).generate(DEFAULT_REQUEST)
    pid = project["project_id"]
    first = store.set_session(pid, 0, 2)
    assert first == {"project_id": pid, "revision": 1, "cursor": 2}
    with pytest.raises(PrototypeStoreError, match="E_CONFLICT"):
        store.set_session(pid, 0, 1)
    record = LocalPrototype(store, _commit()).feedback_record(
        {
            "prototype_version": "1.0.0",
            "project_id": pid,
            "outcome": "NEEDS_CHANGES",
            "notes": "Zu eng",
            "actual_diameter_mm": 38,
            "actual_height_mm": None,
        }
    )
    assert record["review_state"] == "HUMAN_FEEDBACK_UNREVIEWED"
    assert record["source_crochet_ir_sha256"] == pid
    store.close()
    restored = PrototypeStore(tmp_path)
    assert restored.get_project(pid)["session"] == first
    assert restored.feedback(pid) == [record]
    restored.close()


def test_http_host_origin_csrf_size_and_asset_allowlist(tmp_path: Path) -> None:
    server = make_server(0, tmp_path, _commit())
    from threading import Thread

    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(base + "/api/bootstrap") as response:
            import json

            bootstrap = json.load(response)["data"]
        token = bootstrap["csrf_token"]
        headers = {"Origin": base, "X-CSRF-Token": token, "Content-Type": "application/json"}
        bad_host = Request(
            base + "/api/session",
            data=b"{}",
            headers={
                **headers,
                "Host": f"evil.test:{server.server_address[1]}",
                "Origin": f"http://evil.test:{server.server_address[1]}",
            },
            method="POST",
        )
        with pytest.raises(HTTPError) as error:
            urlopen(bad_host)
        assert error.value.code == 403
        bad = Request(
            base + "/api/session",
            data=b"{}",
            headers={**headers, "Origin": "http://evil.test"},
            method="POST",
        )
        with pytest.raises(HTTPError) as error:
            urlopen(bad)
        assert error.value.code == 403
        large = Request(base + "/api/session", data=b" " * 65_537, headers=headers, method="POST")
        with pytest.raises(HTTPError) as error:
            urlopen(large)
        assert error.value.code == 413
        duplicate = Request(
            base + "/api/session",
            data=b'{"prototype_version":"1.0.0","prototype_version":"1.0.0"}',
            headers=headers,
            method="POST",
        )
        with pytest.raises(HTTPError) as error:
            urlopen(duplicate)
        assert error.value.code == 400
        nonfinite = Request(
            base + "/api/session", data=b'{"x":NaN}', headers=headers, method="POST"
        )
        with pytest.raises(HTTPError) as error:
            urlopen(nonfinite)
        assert error.value.code == 400
        with pytest.raises(HTTPError) as error:
            urlopen(base + "/prototype_input.py")
        assert error.value.code == 404
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        server.prototype_store.close()


def test_storage_budget_counts_utf8_bytes_across_feedback_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from crochet_ai import prototype_storage

    store = PrototypeStore(tmp_path)
    pid = "a" * 64
    project = store.save_project({
        "project_id": pid, "source_crochet_ir_sha256": pid, "steps": [],
    }, "2026-10-05T00:00:00Z")
    first = {
        "feedback_id": "feedback_1", "project_id": pid,
        "source_crochet_ir_sha256": pid, "notes": "ä" * 100,
    }
    second = {**first, "feedback_id": "feedback_2"}
    def encoded_size(value: object) -> int:
        return len(json.dumps(
            value, ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8"))
    monkeypatch.setattr(prototype_storage, "MAX_TOTAL_PAYLOAD_BYTES",
                        encoded_size(project) + encoded_size(first) + encoded_size(second) - 1)
    try:
        store.add_feedback(first)
        with pytest.raises(PrototypeStoreError, match=r"store\.byte_limit"):
            store.add_feedback(second)
        assert store.feedback(pid) == [first]
    finally:
        store.close()
