from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from threading import Thread
from typing import cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from test_prototype_backend import DEFAULT_REQUEST, _commit

from crochet_ai.canonical import jcs_bytes
from crochet_ai.prototype_backend import LocalPrototype
from crochet_ai.prototype_proposals import (
    PROFILE,
    ProposalBundleIntegrityError,
    retained_proposals,
)
from crochet_ai.prototype_server import make_server
from crochet_ai.prototype_storage import PrototypeStore, PrototypeStoreError
from crochet_ai.validation import SemanticValidator


def _small_request() -> dict[str, object]:
    return {**DEFAULT_REQUEST, "diameter_mm": 20, "height_mm": 20}


@pytest.fixture(scope="module")
def saved_project(tmp_path_factory: pytest.TempPathFactory) -> tuple[PrototypeStore, dict]:
    store = PrototypeStore(tmp_path_factory.mktemp("proposal-bundle") / "prototype")
    project = LocalPrototype(store, _commit()).generate(_small_request())
    return store, project


def test_bundle_is_original_ordered_snapshot_bound_to_trace_and_link(
    saved_project: tuple[PrototypeStore, dict],
) -> None:
    store, project = saved_project
    generation = project["generation"]
    bundle = generation["proposal_bundle"]
    assert bundle["profile"] == PROFILE
    assert len(bundle["candidate_proposals"]) == 1
    assert (
        bundle["proposal_ir_sha256"] == generation["search_trace"]["terminal"]["proposal_ir_sha256"]
    )
    assert bundle["search_trace_sha256"] == generation["search_trace_sha256"]
    assert bundle["proposal_to_final_sha256"] == generation["proposal_to_final_sha256"]
    assert (
        generation["proposal_bundle_sha256"]
        == sha256(b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + jcs_bytes(bundle)).hexdigest()
    )
    assert retained_proposals(project) == bundle["candidate_proposals"]
    project_id = project["project_id"]
    store.set_session(project_id, 0, 1)
    store.add_feedback(
        {
            "feedback_id": "feedback_test",
            "project_id": project_id,
            "source_crochet_ir_sha256": project_id,
            "outcome": "WORKED",
            "notes": "ok",
        }
    )
    store.close()
    restored = PrototypeStore(saved_project[0].path.parent)
    loaded = restored.get_project(project_id)
    assert loaded is not None
    assert retained_proposals(loaded) == bundle["candidate_proposals"]
    assert loaded["session"] == {"project_id": project_id, "revision": 1, "cursor": 1}
    assert restored.feedback(project_id)[0]["notes"] == "ok"
    restored.close()


@pytest.mark.parametrize("damage", ["digest", "partial", "trace", "link", "project"])
def test_corrupt_or_partial_snapshot_is_rejected(
    saved_project: tuple[PrototypeStore, dict],
    damage: str,
) -> None:
    project = deepcopy(saved_project[1])
    generation = project["generation"]
    if damage == "digest":
        generation["proposal_bundle"]["proposal_ir_sha256"][0] = "0" * 64
    elif damage == "partial":
        del generation["proposal_bundle_sha256"]
    elif damage == "trace":
        generation["search_trace"]["terminal"]["proposal_ir_sha256"][0] = "0" * 64
    elif damage == "link":
        generation["proposal_to_final"]["final_crochet_ir_sha256"] = "0" * 64
        generation["proposal_to_final_sha256"] = sha256(
            b"Crochet.AI\0PROTOTYPE_GENERATION_LINK_V1\0"
            + jcs_bytes(generation["proposal_to_final"])
        ).hexdigest()
    else:
        project["project_id"] = "0" * 64
    with pytest.raises(ProposalBundleIntegrityError):
        retained_proposals(project)


def test_refreshed_bundle_digest_does_not_hide_binding_contradiction(
    saved_project: tuple[PrototypeStore, dict],
) -> None:
    project = deepcopy(saved_project[1])
    generation = project["generation"]
    generation["proposal_bundle"]["design_spec_sha256"] = "0" * 64
    generation["proposal_bundle_sha256"] = sha256(
        b"Crochet.AI\0" + PROFILE.encode("ascii") + b"\0" + jcs_bytes(generation["proposal_bundle"])
    ).hexdigest()
    with pytest.raises(ProposalBundleIntegrityError, match="trace_binding"):
        retained_proposals(project)


def test_legacy_requires_both_snapshot_fields_absent(
    saved_project: tuple[PrototypeStore, dict],
) -> None:
    project = deepcopy(saved_project[1])
    generation = project["generation"]
    del generation["proposal_bundle"]
    del generation["proposal_bundle_sha256"]
    assert retained_proposals(project) == []


def test_http_verify_delivers_retained_proposals_and_rejects_oversized_envelope(
    saved_project: tuple[PrototypeStore, dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import crochet_ai.prototype_server as prototype_server
    from crochet_ai.backend_api import MAX_REQUEST_BYTES, BackendAPI

    store, project = saved_project
    directory = store.path.parent
    store.close()
    captured: list[dict] = []
    original_handle = prototype_server.BackendAPI.handle

    def capture(self: BackendAPI, request: dict) -> dict:
        if request.get("operation") == "verify_candidate":
            captured.append(request)
        return original_handle(self, request)

    monkeypatch.setattr(prototype_server.BackendAPI, "handle", capture)
    server = make_server(0, directory, _commit())
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urlopen(base + "/api/bootstrap") as response:
            token = json.load(response)["data"]["csrf_token"]
        headers = {
            "Origin": base,
            "X-CSRF-Token": token,
            "Content-Type": "application/json",
        }
        verify = Request(
            base + "/api/verify",
            data=json.dumps({"project_id": project["project_id"]}).encode(),
            headers=headers,
            method="POST",
        )
        with urlopen(verify, timeout=90) as response:
            delivered = json.load(response)
        evidence = captured[-1]["search_evidence"]
        assert (
            evidence["candidate_proposals"]
            == project["generation"]["proposal_bundle"]["candidate_proposals"]
        )
        assert delivered["ok"]
        assert delivered["data"]["verification_state"] == "NOT_VERIFIED"
        assert delivered["data"]["physical_status"] == "UNTESTED"
        v5 = next(gate for gate in delivered["data"]["gates"] if gate["gate_id"] == "V5")
        assert v5["linked_evidence"]["search_audit"]["status"] == "PASS"
        assert v5["outcome"] == "INDETERMINATE"

        original_retained = prototype_server.retained_proposals

        def oversized(value: dict) -> list[dict]:
            proposals = original_retained(value)
            proposals[0]["transport_padding"] = "x" * MAX_REQUEST_BYTES
            return proposals

        monkeypatch.setattr(prototype_server, "retained_proposals", oversized)
        with pytest.raises(HTTPError) as error:
            urlopen(verify, timeout=15)
        assert error.value.code == 413
        assert json.loads(error.value.read())["error"]["reason"] == "verification.request_size"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        server.prototype_store.close()


def test_storage_quota_rolls_back_project_and_initial_session(
    saved_project: tuple[PrototypeStore, dict],
) -> None:
    original = saved_project[1]
    store = PrototypeStore(saved_project[0].path.parent)
    rejected = deepcopy(original)
    rejected["project_id"] = "f" * 64
    rejected["source_crochet_ir_sha256"] = "f" * 64
    rejected["extra"] = "x" * (4 * 1024 * 1024)
    with pytest.raises(PrototypeStoreError, match=r"store\.byte_limit"):
        store.save_project(rejected, "2026-10-06T00:00:00+00:00")
    assert store.get_project("f" * 64) is None
    assert (
        store.db.execute(
            "SELECT count(*) FROM sessions WHERE project_id=?", ("f" * 64,)
        ).fetchone()[0]
        == 0
    )
    store.close()


def test_nested_bounds_reject_before_any_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    import crochet_ai.prototype_proposals as proposals

    def unexpected_hash(*args: object, **kwargs: object) -> str:
        raise AssertionError("hashing must follow bounds admission")

    monkeypatch.setattr(proposals, "canonical_hash", unexpected_hash)
    deep: object = {}
    for _ in range(66):
        deep = {"x": deep}
    with pytest.raises(ProposalBundleIntegrityError, match="input_complexity"):
        proposals.create_proposal_bundle(
            {"bindings": {}, "terminal": {"proposal_ir_sha256": ["0" * 64]}},
            "0" * 64,
            {},
            "0" * 64,
            [deep],
            cast(SemanticValidator, None),
        )
