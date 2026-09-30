"""One explicit local queue step, suitable for supervision by a process host."""

import multiprocessing
import time
from multiprocessing.connection import Connection

import rfc8785

from .analytic_compile import CompileProvenance
from .backend_api import BackendAPI, error_response
from .canonical import parse_json
from .job_store import JobStore


def execute_one(store: JobStore, api: BackendAPI) -> bool:
    store.recover_expired()
    claim = store.claim()
    if claim is None:
        return False
    try:
        result = api.handle_json(claim.request)
    except Exception as error:
        # Persist a real failed job; do not expose request data or local paths.
        store.finish(claim, error_response("E_INTERNAL", type(error).__name__), failed=True)
        raise
    store.finish(claim, result, failed=not result["ok"])
    return True


def _child_run(send: Connection, request: bytes, provenance: CompileProvenance) -> None:
    try:
        result = BackendAPI(provenance).handle_json(request)
    except Exception as error:
        result = error_response("E_INTERNAL", type(error).__name__)
    try:
        payload = rfc8785.dumps(result)
        if len(payload) > 32_000_000:
            payload = rfc8785.dumps(error_response("E_STORAGE_LIMIT", "worker.result_size"))
        send.send_bytes(payload)
    finally:
        send.close()


def execute_one_isolated(store: JobStore, api: BackendAPI, *, max_wall_seconds: float) -> bool:
    """Watchdog/cancellation are operational failures, never solver infeasibility."""
    if not 0 < max_wall_seconds < store.lease_seconds:
        raise ValueError("worker.watchdog_must_fit_lease")
    store.recover_expired()
    claim = store.claim()
    if claim is None:
        return False
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    process = context.Process(
        target=_child_run, args=(send, claim.request, api.provenance), daemon=True
    )
    deadline = time.monotonic() + max_wall_seconds
    started = False
    try:
        try:
            process.start()
            started = True
        except (OSError, RuntimeError) as error:
            store.finish(
                claim,
                error_response("E_INTERNAL", f"worker.start_failed.{type(error).__name__}"),
                failed=True,
            )
            return True
        finally:
            send.close()
        while True:
            if time.monotonic() >= deadline:
                store.finish(
                    claim,
                    error_response("E_SEARCH_BUDGET", "worker.watchdog_interrupted"),
                    failed=True,
                )
                return True
            state = store.get(claim.job_id)["status"]
            if state not in {"RUNNING", "CANCEL_REQUESTED"}:
                return True
            if state == "CANCEL_REQUESTED":
                store.finish(claim, error_response("E_CANCELLED", "worker.cancelled"), failed=True)
                return True
            if receive.poll(min(0.05, max(0.0, deadline - time.monotonic()))):
                try:
                    payload = receive.recv_bytes(maxlength=32_000_000)
                except (EOFError, OSError):
                    store.finish(
                        claim, error_response("E_INTERNAL", "worker.child_interrupted"), failed=True
                    )
                    return True
                try:
                    value = parse_json(payload)
                except (RecursionError, TypeError, ValueError):
                    store.finish(
                        claim, error_response("E_INTERNAL", "worker.invalid_response"), failed=True
                    )
                    return True
                if not isinstance(value, dict) or type(value.get("ok")) is not bool:
                    store.finish(
                        claim, error_response("E_INTERNAL", "worker.invalid_response"), failed=True
                    )
                    return True
                store.finish(claim, value, failed=not value["ok"])
                return True
    finally:
        send.close()
        receive.close()
        if started:
            if process.is_alive():
                process.terminate()
            process.join(timeout=1)
            if process.is_alive():
                process.kill()
                process.join(timeout=1)
        process.close()
