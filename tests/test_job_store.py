import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from test_analytic_solver import PROVENANCE

from crochet_ai.backend_api import BackendAPI
from crochet_ai.job_store import JobStore, JobStoreError
from crochet_ai.job_worker import execute_one, execute_one_isolated

REQUEST = '{"api_version":"1.0.0","operation":"capabilities"}'


def test_idempotency_and_result_survive_reopen(tmp_path: Path) -> None:
    path = tmp_path / "jobs.sqlite"
    store = JobStore(path)
    job_id = store.submit(REQUEST, "client-1")
    assert store.submit(json.dumps(json.loads(REQUEST), indent=2), "client-1") == job_id
    with pytest.raises(JobStoreError, match="idempotency_conflict"):
        store.submit('{"different":true}', "client-1")
    assert execute_one(store, BackendAPI(PROVENANCE))
    reopened = JobStore(path)
    value = reopened.get(job_id)
    assert value["status"] == "SUCCEEDED"
    assert value["result"]["data"]["physical_verification_available"] is False
    assert value["result_sha256"]
    assert not execute_one(reopened, BackendAPI(PROVENANCE))


def test_parallel_idempotency_and_exclusive_claims(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.sqlite")
    with ThreadPoolExecutor(max_workers=8) as pool:
        same = list(pool.map(lambda _: store.submit(REQUEST, "same"), range(16)))
        assert len(set(same)) == 1
        others = list(pool.map(lambda i: store.submit(REQUEST, f"client-{i}"), range(15)))
        claims = list(pool.map(lambda _: store.claim(), range(32)))
    claimed = [claim.job_id for claim in claims if claim is not None]
    assert set(claimed) == set(same + others)
    assert len(claimed) == len(set(claimed))


def test_cancellation_never_publishes_running_results(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.sqlite")
    queued = store.submit(REQUEST, "queued")
    assert store.cancel(queued) == "CANCELLED"
    assert store.claim() is None
    running = store.submit(REQUEST, "running")
    claim = store.claim()
    assert claim is not None
    assert store.cancel(running) == "CANCEL_REQUESTED"
    assert not store.finish(claim, {"should_not_publish": True})
    assert store.get(running)["status"] == "CANCELLED"
    assert store.get(running)["result"] is None
    assert not store.finish(claim, {"late": True})


def test_expired_worker_cannot_overwrite_recovered_job(tmp_path: Path) -> None:
    now = [10.0]
    store = JobStore(tmp_path / "jobs.sqlite", lease_seconds=3, clock=lambda: now[0])
    job_id = store.submit(REQUEST, "lost")
    claim = store.claim()
    assert claim is not None
    now[0] = 13.0
    assert store.recover_expired() == 1
    assert not store.finish(claim, {"stale": True})
    state = store.get(job_id)
    assert state["status"] == "FAILED" and state["error_code"] == "E_WORKER_INTERRUPTED"


def test_result_tampering_and_capacity_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "jobs.sqlite"
    store = JobStore(path, max_jobs=1)
    job_id = store.submit(REQUEST, "first")
    with pytest.raises(JobStoreError, match="capacity"):
        store.submit(REQUEST, "second")
    execute_one(store, BackendAPI(PROVENANCE))
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE jobs SET result=? WHERE job_id=?", (b'{"tampered":true}', job_id)
        )
    with pytest.raises(JobStoreError, match="result_integrity"):
        store.get(job_id)


def test_unrelated_database_is_not_migrated(tmp_path: Path) -> None:
    path = tmp_path / "foreign.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE unrelated(value TEXT)")
    with pytest.raises(JobStoreError, match="unrecognized_database"):
        JobStore(path)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall() == [("unrelated",)]


def test_payload_quota_fails_publication_atomically(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "quota.sqlite", max_payload_bytes=100)
    job_id = store.submit(REQUEST, "first")
    claim = store.claim()
    assert claim is not None
    assert not store.finish(claim, {"oversized": "a" * 100})
    row = store.get(job_id)
    assert row["status"] == "FAILED" and row["error_code"] == "E_STORAGE_LIMIT"
    assert row["result"] is None


def test_spawned_worker_publishes_only_complete_result(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "spawn.sqlite")
    job_id = store.submit(REQUEST, "first")
    assert execute_one_isolated(store, BackendAPI(PROVENANCE), max_wall_seconds=20)
    assert store.get(job_id)["status"] == "SUCCEEDED"


def test_watchdog_is_budget_failure_not_no_solution(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "watchdog.sqlite")
    job_id = store.submit(REQUEST, "first")
    assert execute_one_isolated(store, BackendAPI(PROVENANCE), max_wall_seconds=0.000001)
    row = store.get(job_id)
    assert row["status"] == "FAILED"
    assert row["result"]["error"] == {
        "code": "E_SEARCH_BUDGET",
        "reason": "worker.watchdog_interrupted",
    }


def test_spawn_failure_is_recorded_without_waiting_for_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from multiprocessing.process import BaseProcess

    def fail_start(self: BaseProcess) -> None:
        raise OSError("synthetic resource failure")

    monkeypatch.setattr(BaseProcess, "start", fail_start)
    store = JobStore(tmp_path / "spawn-failure.sqlite")
    job_id = store.submit(REQUEST, "first")
    assert execute_one_isolated(store, BackendAPI(PROVENANCE), max_wall_seconds=20)
    row = store.get(job_id)
    assert row["status"] == "FAILED"
    assert row["result"]["error"]["reason"] == "worker.start_failed.OSError"


@pytest.mark.parametrize(
    "child_payload",
    [b'{"payload":"private child bytes"', b"[" * 2000 + b"]" * 2000],
)
def test_malformed_child_response_fails_immediately_without_exposing_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, child_payload: bytes
) -> None:
    import crochet_ai.job_worker as job_worker

    class FakeConnection:
        def __init__(self, payload: bytes | None = None) -> None:
            self.payload = payload

        def close(self) -> None:
            pass

        def poll(self, _timeout: float) -> bool:
            return self.payload is not None

        def recv_bytes(self, *, maxlength: int) -> bytes:
            assert maxlength == 32_000_000
            assert self.payload is not None
            return self.payload

    class FakeProcess:
        def __init__(self, *, target: object, args: tuple[object, ...], daemon: bool) -> None:
            assert target is job_worker._child_run
            assert daemon
            self.started = False

        def start(self) -> None:
            self.started = True

        def is_alive(self) -> bool:
            return False

        def join(self, timeout: float) -> None:
            assert timeout == 1

        def close(self) -> None:
            pass

    parent = FakeConnection(child_payload)
    child = FakeConnection()

    class FakeContext:
        @staticmethod
        def Pipe(*, duplex: bool) -> tuple[FakeConnection, FakeConnection]:
            assert not duplex
            return parent, child

        @staticmethod
        def Process(*, target: object, args: tuple[object, ...], daemon: bool) -> FakeProcess:
            return FakeProcess(target=target, args=args, daemon=daemon)

    monkeypatch.setattr(job_worker.multiprocessing, "get_context", lambda _method: FakeContext())
    monkeypatch.setattr(job_worker.time, "monotonic", lambda: 1.0)
    store = JobStore(tmp_path / "malformed-response.sqlite")
    job_id = store.submit(REQUEST, "first")

    assert execute_one_isolated(store, BackendAPI(PROVENANCE), max_wall_seconds=20)

    row = store.get(job_id)
    assert row["status"] == "FAILED"
    assert row["result"]["error"] == {
        "code": "E_INTERNAL",
        "reason": "worker.invalid_response",
    }
    assert "private child bytes" not in json.dumps(row["result"])
