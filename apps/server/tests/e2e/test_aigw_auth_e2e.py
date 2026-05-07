"""End-to-end: SF aigw-claude-backend auth-proxy <-> real aigateway subprocess.

Boots a real aigateway with:
- a fake JSON-file-backed credential store (no real OS keychain)
- a fake Anthropic OAuth provider via httpx MockTransport injected
  through ``app.state.anthropic_http_factory``

Drives the full OAuth cycle through the SF endpoints and asserts that
the SF auth-proxy + gateway combination behaves as documented in
docs/superpowers/specs/2026-05-07-aigw-backend-oauth-authenticate-button-design.md.

This test does NOT open a browser; it simulates the browser by issuing
the callback request directly to the gateway, which is exactly what
the real Electron flow does (the browser hits the gateway's callback
URL directly -- the SF server is never on the OAuth callback path).
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.aigw_claude_backend.plugin import (
    AigwClaudeBackendPlugin,
    AigwClaudeBackendSettings,
)

pytestmark = pytest.mark.e2e


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _aigateway_dir() -> Path:
    # apps/server/tests/e2e/<this_file>.py -> apps/aigateway
    return Path(__file__).resolve().parents[3] / "aigateway"


def _boot_gateway(
    extra_env: dict[str, str], tmp_path: Path
) -> tuple[int, subprocess.Popen[str]]:
    port = _free_port()
    env = os.environ.copy()
    env["AIGATEWAY_FAKE_KEYCHAIN"] = "1"
    env["AIGATEWAY_KEYCHAIN_FILE"] = str(tmp_path / "fake-kc.json")
    env["AIGATEWAY_FAKE_ANTHROPIC_OAUTH"] = "1"
    env.update(extra_env)
    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "--directory",
            str(_aigateway_dir()),
            "uvicorn",
            "aigateway.main:app",
            "--port",
            str(port),
            "--host",
            "127.0.0.1",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            output = proc.stdout.read() if proc.stdout else ""
            raise RuntimeError(
                f"aigateway exited early (rc={proc.returncode}); output:\n{output}"
            )
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=1)
            if r.status_code == 200:
                return port, proc
        except httpx.RequestError:
            time.sleep(0.2)
    proc.terminate()
    output = ""
    try:
        output = proc.stdout.read() if proc.stdout else ""
    except Exception:
        pass
    raise RuntimeError(f"aigateway failed to start within 30s; output:\n{output}")


def _terminate(proc: subprocess.Popen[str]) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
def aigw(tmp_path: Path) -> Iterator[dict]:
    port, proc = _boot_gateway({}, tmp_path)
    try:
        yield {"port": port, "proc": proc}
    finally:
        _terminate(proc)


@pytest.fixture
def aigw_failing_oauth(tmp_path: Path) -> Iterator[dict]:
    port, proc = _boot_gateway({"AIGATEWAY_FAKE_ANTHROPIC_OAUTH_FAIL": "1"}, tmp_path)
    try:
        yield {"port": port, "proc": proc}
    finally:
        _terminate(proc)


def _sf_client(gateway_port: int) -> TestClient:
    settings = AigwClaudeBackendSettings(gateway_url=f"http://127.0.0.1:{gateway_port}")
    app = FastAPI()
    app.include_router(AigwClaudeBackendPlugin.create_router(settings, app=app))
    return TestClient(app)


# ---------------------------------------------------------------------------
# Scenario 1: happy-path full cycle
# ---------------------------------------------------------------------------


def test_full_oauth_cycle_via_sf_auth_proxy(aigw: dict) -> None:
    """SF /claude/auth/start -> gateway PENDING -> simulated callback ->
    SF /claude/auth/status -> AUTHENTICATED -> SF /claude/health green."""
    gw_port = aigw["port"]
    sf = _sf_client(gw_port)

    resp = sf.post("/claude/auth/start")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["profile_id"] == "anthropic:default"
    assert body["authorize_url"].startswith("https://")
    state = body["state"]

    s = sf.get("/claude/auth/status").json()
    assert s["state"] == "pending"

    cb = httpx.get(
        f"http://127.0.0.1:{gw_port}/v1/auth/anthropic/callback",
        params={"code": "fake-code", "state": state},
    )
    assert cb.status_code == 200, cb.text

    s = sf.get("/claude/auth/status").json()
    assert s["state"] == "authenticated"

    h = sf.get("/claude/health")
    assert h.status_code == 200
    assert h.json()["authenticated"] is True


# ---------------------------------------------------------------------------
# Scenario 2: idempotent re-start of an already-authenticated profile
# ---------------------------------------------------------------------------


def test_restart_authenticated_profile_yields_fresh_authorize_url(aigw: dict) -> None:
    gw_port = aigw["port"]
    sf = _sf_client(gw_port)

    state = sf.post("/claude/auth/start").json()["state"]
    cb = httpx.get(
        f"http://127.0.0.1:{gw_port}/v1/auth/anthropic/callback",
        params={"code": "c1", "state": state},
    )
    assert cb.status_code == 200, cb.text
    assert sf.get("/claude/auth/status").json()["state"] == "authenticated"

    body = sf.post("/claude/auth/start").json()
    assert body["state"] != state
    assert sf.get("/claude/auth/status").json()["state"] == "pending"


# ---------------------------------------------------------------------------
# Scenario 3: callback with wrong state is rejected
# ---------------------------------------------------------------------------


def test_callback_with_wrong_state_does_not_authenticate(aigw: dict) -> None:
    gw_port = aigw["port"]
    sf = _sf_client(gw_port)

    sf.post("/claude/auth/start")
    cb = httpx.get(
        f"http://127.0.0.1:{gw_port}/v1/auth/anthropic/callback",
        params={"code": "c", "state": "definitely-wrong"},
    )
    assert cb.status_code == 400
    assert sf.get("/claude/auth/status").json()["state"] == "pending"


# ---------------------------------------------------------------------------
# Scenario 4: token-exchange fails at upstream
# ---------------------------------------------------------------------------


def test_callback_when_token_exchange_fails_marks_profile_non_authenticated(
    aigw_failing_oauth: dict,
) -> None:
    gw_port = aigw_failing_oauth["port"]
    sf = _sf_client(gw_port)

    state = sf.post("/claude/auth/start").json()["state"]
    cb = httpx.get(
        f"http://127.0.0.1:{gw_port}/v1/auth/anthropic/callback",
        params={"code": "c", "state": state},
    )
    assert cb.status_code >= 400
    s = sf.get("/claude/auth/status").json()
    # The gateway may either leave the profile in PENDING or mark it ERROR;
    # either way it must not be AUTHENTICATED.
    assert s["state"] in ("pending", "error")
    assert s["state"] != "authenticated"


# ---------------------------------------------------------------------------
# Scenario 5: gateway down at start
# ---------------------------------------------------------------------------


def test_start_when_gateway_is_down_returns_502() -> None:
    port = _free_port()  # Nothing listening
    sf = _sf_client(port)

    resp = sf.post("/claude/auth/start")
    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "gateway_unreachable"


# ---------------------------------------------------------------------------
# Scenario 6: profile not yet created
# ---------------------------------------------------------------------------


def test_status_before_first_start_returns_404(aigw: dict) -> None:
    gw_port = aigw["port"]
    sf = _sf_client(gw_port)

    s = sf.get("/claude/auth/status")
    assert s.status_code == 404

    h = sf.get("/claude/health")
    assert h.status_code == 503
    assert h.json()["authenticated"] is False
