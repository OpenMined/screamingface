"""Dependency smoke tests for the tracing plugin."""

from __future__ import annotations

import importlib
import multiprocessing
import queue
import socket
import time
import urllib.request


def test_phoenix_imports_with_tracing_dependencies() -> None:
    """Phoenix must import cleanly so the tracing plugin can launch its UI."""
    importlib.import_module("phoenix")


def test_phoenix_launch_serves_ui_root() -> None:
    """Phoenix must serve its UI root, not just bind the port."""
    port = _unused_port()
    grpc_port = _unused_port()
    ctx = multiprocessing.get_context("spawn")
    ready = ctx.Queue()
    proc = ctx.Process(target=_run_phoenix, args=(port, grpc_port, ready), daemon=True)
    proc.start()
    try:
        try:
            status, detail = ready.get(timeout=30)
        except queue.Empty as exc:
            raise AssertionError("Phoenix did not report startup within 30s") from exc
        assert status == "ok", detail

        deadline = time.monotonic() + 30
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
                    assert response.status == 200
                    return
            except Exception as exc:  # noqa: BLE001 - retry until Phoenix finishes booting.
                last_error = exc
                time.sleep(0.5)
        raise AssertionError(f"Phoenix UI root did not return HTTP 200: {last_error!r}")
    finally:
        proc.terminate()
        proc.join(timeout=10)


def _unused_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run_phoenix(port: int, grpc_port: int, ready: multiprocessing.Queue) -> None:
    import os

    os.environ["PHOENIX_PORT"] = str(port)
    os.environ["PHOENIX_GRPC_PORT"] = str(grpc_port)
    try:
        import phoenix as px

        px.launch_app(run_in_thread=True)
    except Exception as exc:  # noqa: BLE001 - forwarded to the parent process assertion.
        ready.put(("error", repr(exc)))
        return
    ready.put(("ok", None))
    while True:
        time.sleep(1)
