"""End-to-end: SF aigw-codex-backend auth-proxy <-> real aigateway subprocess.

This mirrors the Claude auth E2E shape but exercises the Codex provider-owned
OAuth exchange path. It does not contact OpenAI: the gateway subprocess is
started with test-only fake keychain and fake Codex token endpoint hooks.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.aigw_codex_backend.plugin import (
    AigwCodexBackendPlugin,
    AigwCodexBackendSettings,
)

pytestmark = pytest.mark.e2e

_ANONYMOUS_ACCOUNT_ID = "00000000-0000-0000-0000-000000000000"


def _reserve_loopback_socket(*, listen: bool) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    if listen:
        sock.listen()
    sock.set_inheritable(True)
    return sock


def _aigateway_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "aigateway"


def _boot_gateway(extra_env: dict[str, str], tmp_path: Path) -> tuple[int, subprocess.Popen[str]]:
    sock = _reserve_loopback_socket(listen=True)
    port = sock.getsockname()[1]
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    env["AIGW_PORT"] = str(port)
    env["AIGATEWAY_FAKE_KEYCHAIN"] = "1"
    env["AIGATEWAY_KEYCHAIN_FILE"] = str(tmp_path / "fake-kc.json")
    env["AIGATEWAY_FAKE_CODEX_OAUTH"] = "1"
    env["AIGATEWAY_DATABASE_URL"] = f"sqlite://{tmp_path / 'aigateway.sqlite3'}"
    env["AIGATEWAY_AUTH_ENABLED"] = "0"
    env["AIGATEWAY_ADMIN_PASSWORD"] = "test-admin-password"
    env["AIGATEWAY_JWT_SECRET"] = "x" * 32
    env["AIGATEWAY_PROVISIONING_TOKEN"] = "p" * 32
    env.update(extra_env)
    try:
        subprocess.run(
            [
                "uv",
                "run",
                "--directory",
                str(_aigateway_dir()),
                "python",
                "-m",
                "tortoise",
                "-c",
                "aigateway.db.TORTOISE_CONFIG",
                "migrate",
            ],
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        proc = subprocess.Popen(
            [
                "uv",
                "run",
                "--directory",
                str(_aigateway_dir()),
                "uvicorn",
                "aigateway.main:app",
                "--fd",
                str(sock.fileno()),
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            pass_fds=(sock.fileno(),),
        )
    finally:
        sock.close()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            output = proc.stdout.read() if proc.stdout else ""
            raise RuntimeError(f"aigateway exited early (rc={proc.returncode}); output:\n{output}")
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
    port, proc = _boot_gateway({"AIGATEWAY_FAKE_CODEX_OAUTH_FAIL": "1"}, tmp_path)
    try:
        yield {"port": port, "proc": proc}
    finally:
        _terminate(proc)


def _sf_client(gateway_port: int) -> TestClient:
    settings = AigwCodexBackendSettings(gateway_url=f"http://127.0.0.1:{gateway_port}")
    app = FastAPI()
    app.include_router(AigwCodexBackendPlugin.create_router(settings, app=app))
    return TestClient(app)


def _callback_url_from_authorize_url(authorize_url: str) -> str:
    query = parse_qs(urlparse(authorize_url).query)
    redirect_uri = query["redirect_uri"][0]
    parsed = urlparse(redirect_uri)
    return f"http://127.0.0.1:{parsed.port}{parsed.path}"


def test_full_codex_oauth_cycle_via_sf_auth_proxy(aigw: dict) -> None:
    gw_port = aigw["port"]
    sf = _sf_client(gw_port)

    resp = sf.post("/codex/auth/start")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["profile_id"] == f"{_ANONYMOUS_ACCOUNT_ID}:codex:default"
    assert body["authorize_url"].startswith("https://auth.openai.com/oauth/authorize")
    redirect_uri = parse_qs(urlparse(body["authorize_url"]).query)["redirect_uri"][0]
    assert redirect_uri in {
        "http://localhost:1455/auth/callback",
        "http://localhost:1457/auth/callback",
    }
    state = body["state"]

    pending = sf.get("/codex/auth/status")
    assert pending.status_code == 200
    assert pending.json()["state"] == "pending"

    cb = httpx.get(
        _callback_url_from_authorize_url(body["authorize_url"]),
        params={"code": "fake-codex-code", "state": state},
        timeout=5,
    )
    assert cb.status_code == 200, cb.text

    status = sf.get("/codex/auth/status")
    assert status.status_code == 200
    assert status.json()["state"] == "authenticated"
    assert status.json()["account_label"] == "codex-user@example.com"

    health = sf.get("/codex/health")
    assert health.status_code == 200
    assert health.json()["authenticated"] is True


def test_codex_import_route_is_not_exposed(aigw: dict) -> None:
    sf = _sf_client(aigw["port"])

    resp = sf.post("/codex/auth/import")

    assert resp.status_code == 404


def test_callback_with_wrong_state_does_not_authenticate(aigw: dict) -> None:
    sf = _sf_client(aigw["port"])

    start = sf.post("/codex/auth/start").json()
    cb = httpx.get(
        _callback_url_from_authorize_url(start["authorize_url"]),
        params={"code": "fake-codex-code", "state": "definitely-wrong"},
        timeout=5,
    )
    assert cb.status_code == 400
    assert sf.get("/codex/auth/status").json()["state"] == "pending"


def test_callback_when_token_exchange_fails_marks_profile_non_authenticated(
    aigw_failing_oauth: dict,
) -> None:
    sf = _sf_client(aigw_failing_oauth["port"])

    start = sf.post("/codex/auth/start").json()
    cb = httpx.get(
        _callback_url_from_authorize_url(start["authorize_url"]),
        params={"code": "fake-codex-code", "state": start["state"]},
        timeout=5,
    )
    assert cb.status_code >= 400
    status = sf.get("/codex/auth/status").json()
    assert status["state"] in ("pending", "error")
    assert status["state"] != "authenticated"


def test_start_when_gateway_is_down_returns_502() -> None:
    with _reserve_loopback_socket(listen=False) as sock:
        sf = _sf_client(sock.getsockname()[1])

        resp = sf.post("/codex/auth/start")

    assert resp.status_code == 502
    assert resp.json()["detail"]["code"] == "gateway_unreachable"
