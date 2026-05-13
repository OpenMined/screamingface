"""End-to-end: SF subprocess with state + eval-runs plugins.

Spawns a real `sf run` subprocess, hits the two read endpoints over HTTP, and
verifies the schema-bootstrap path works in a fresh process. This is the
minimal e2e coverage for DEMO-014; richer scenarios land with DEMO-017 when
runs are actually created end-to-end via the orchestrator.
"""

from __future__ import annotations

import socket
import uuid
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from tests.e2e.infrastructure.server_manager import ServerManager

pytestmark = pytest.mark.e2e


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(tmp_path: Path) -> Iterator[tuple[ServerManager, int]]:
    port = _free_port()
    config = {
        "version": "0.1.0",
        "server": {
            "host": "127.0.0.1",
            "port": port,
            "ssl": False,
            "reload": False,
        },
        "plugins": ["state", "eval-runs"],
    }
    mgr = ServerManager(
        config,
        session_id="e2e-eval-runs",
        env_extra={"SF_STATE__PATH": str(tmp_path / "state.db")},
    )
    mgr.start(timeout=60)
    if not ServerManager.wait_for_port(port, timeout=30):
        last_logs = "\n".join(mgr.logs.dump_last()) if mgr.logs else "<no logs>"
        mgr.stop()
        raise RuntimeError(
            f"eval-runs server not listening on port {port}\nLast server log lines:\n{last_logs}"
        )
    try:
        yield mgr, port
    finally:
        mgr.stop()


@pytest.mark.timeout(60)
def test_list_runs_empty(server: tuple[ServerManager, int]) -> None:
    mgr, port = server
    r = httpx.get(f"http://127.0.0.1:{port}/eval_runs", timeout=10)
    if r.status_code != 200:
        logs = "\n".join(mgr.logs.dump_last(100)) if mgr.logs else "<no logs>"
        raise AssertionError(f"GET /eval_runs -> {r.status_code} {r.text}\nLOGS:\n{logs}")
    assert r.json() == []


@pytest.mark.timeout(60)
def test_get_unknown_run_returns_404(server: tuple[ServerManager, int]) -> None:
    _, port = server
    r = httpx.get(f"http://127.0.0.1:{port}/eval_runs/{uuid.uuid4()}", timeout=10)
    assert r.status_code == 404
    assert r.json() == {"detail": "run not found"}


@pytest.mark.timeout(60)
def test_sqlite_file_created_under_state_path(
    server: tuple[ServerManager, int], tmp_path: Path
) -> None:
    # The fixture sets SF_STATE__PATH to tmp_path/state.db; hitting any endpoint
    # forces Tortoise to be active, which means generate_schemas has run.
    _, port = server
    r = httpx.get(f"http://127.0.0.1:{port}/eval_runs", timeout=10)
    assert r.status_code == 200
    assert (tmp_path / "state.db").exists()
