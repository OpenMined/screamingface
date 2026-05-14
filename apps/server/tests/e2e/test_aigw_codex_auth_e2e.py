"""End-to-end: SF aigw-codex-backend import flow through a real gateway.

This exercises the local-only Desktop posture without live ChatGPT credentials:
SF starts aigw-runner, the runner migrates and starts apps/aigateway, Codex auth
is imported from a fake file-backed CODEX_HOME, and the Codex handler posts to a
loopback fake responses server.
"""

from __future__ import annotations

import base64
import json
import threading
import time
from collections.abc import Generator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.e2e.infrastructure.server_manager import ServerManager

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(120)]

_AIGATEWAY_DIR = (Path(__file__).resolve().parents[3] / "aigateway").resolve()
_ANONYMOUS_ACCOUNT_ID = "00000000-0000-0000-0000-000000000000"


class _FakeCodexServer:
    def __init__(self) -> None:
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._lock = threading.Lock()
        self.requests: list[dict[str, Any]] = []

    @property
    def responses_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}/responses"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def _handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
                length = int(self.headers.get("content-length", "0") or "0")
                raw_body = self.rfile.read(length).decode()
                with outer._lock:
                    outer.requests.append(
                        {
                            "path": self.path,
                            "headers": dict(self.headers),
                            "body": json.loads(raw_body),
                        }
                    )

                if self.path != "/responses":
                    self.send_response(404)
                    self.end_headers()
                    return

                body = (
                    b'data: {"type":"response.output_text.delta","delta":"codex e2e ok"}\n\n'
                    b'data: {"type":"response.completed","response":{}}\n\n'
                )
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

        return Handler


@pytest.fixture
def fake_codex_server() -> Generator[_FakeCodexServer, None, None]:
    server = _FakeCodexServer()
    server.start()
    try:
        yield server
    finally:
        server.stop()


def _unsigned_jwt(claims: dict[str, Any]) -> str:
    def _segment(data: dict[str, Any]) -> str:
        raw = json.dumps(data, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{_segment({'alg': 'none', 'typ': 'JWT'})}.{_segment(claims)}."


def _write_codex_auth(codex_home: Path) -> None:
    codex_home.mkdir(parents=True, exist_ok=True)
    auth_path = codex_home / "auth.json"
    auth_path.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "OPENAI_API_KEY": None,
                "tokens": {
                    "access_token": _unsigned_jwt({"exp": time.time() + 3600}),
                    "refresh_token": "refresh-token-e2e",
                    "id_token": _unsigned_jwt({"sub": "sub-e2e", "email": "codex-e2e@example.com"}),
                    "account_id": "chatgpt-account-e2e",
                },
            }
        )
    )
    auth_path.chmod(0o600)


@pytest.fixture
def codex_aigw_stack(
    tmp_path: Path, fake_codex_server: _FakeCodexServer
) -> Generator[tuple[ServerManager, str, int, _FakeCodexServer], None, None]:
    if not _AIGATEWAY_DIR.exists():
        pytest.skip(f"apps/aigateway/ not found at {_AIGATEWAY_DIR}")

    internal_port = ServerManager.find_free_port()
    gateway_port = ServerManager.find_free_port()
    codex_home = tmp_path / "codex-home"
    _write_codex_auth(codex_home)

    config = {
        "version": "0.1.0",
        "server": {"host": "127.0.0.1", "port": internal_port, "ssl": False, "reload": False},
        "plugins": [
            "llm-base",
            "backend-api-base",
            "aigw-base",
            "aigw-codex-backend",
            "aigw-runner",
        ],
        "plugin_config": {
            "aigw-codex-backend": {
                "gateway_url": f"http://127.0.0.1:{gateway_port}",
                "auth_profile": "default",
                "default_model": "codex/gpt-5.4-mini",
                "timeout_seconds": 30,
            },
            "aigw-runner": {
                "port": gateway_port,
                "aigateway_dir": str(_AIGATEWAY_DIR),
                "database_path": str(tmp_path / "aigateway" / "aigateway.db"),
                "startup_timeout_seconds": 30.0,
                "migrations_timeout_seconds": 30.0,
                "auth_enabled": False,
                "enabled": True,
            },
        },
    }
    env_extra = {
        "CODEX_HOME": str(codex_home),
        "AIGATEWAY_FAKE_KEYCHAIN": "1",
        "AIGATEWAY_KEYCHAIN_FILE": str(tmp_path / "fake-keychain.json"),
        "AIGATEWAY_FAKE_CODEX_RESPONSES_URL": fake_codex_server.responses_url,
        "AIGATEWAY_ADMIN_PASSWORD": "test-admin-password",
        "AIGATEWAY_JWT_SECRET": "x" * 32,
        "AIGATEWAY_PROVISIONING_TOKEN": "p" * 32,
    }

    manager = ServerManager(config, session_id="e2e-aigw-codex", env_extra=env_extra)
    manager.start(timeout=120)
    try:
        if not ServerManager.wait_for_port(gateway_port, timeout=60):
            last_logs = "\n".join(manager.logs.dump_last()) if manager.logs else "<no logs>"
            pytest.fail(f"aigw-runner did not bring up gateway on {gateway_port}\n{last_logs}")
        yield manager, manager.base_url, gateway_port, fake_codex_server
    finally:
        manager.stop()


def test_codex_import_health_and_backend_call_via_aigw_runner(
    codex_aigw_stack: tuple[ServerManager, str, int, _FakeCodexServer],
) -> None:
    manager, sf_base_url, gateway_port, fake_codex = codex_aigw_stack

    imported = httpx.post(f"{sf_base_url}/codex/auth/import", timeout=10)
    assert imported.status_code == 201, imported.text
    imported_body = imported.json()
    assert imported_body["id"] == f"{_ANONYMOUS_ACCOUNT_ID}:codex:default"
    assert imported_body["state"] == "authenticated"
    assert imported_body["account_label"] == "codex-e2e@example.com"

    status = httpx.get(f"{sf_base_url}/codex/auth/status", timeout=10)
    assert status.status_code == 200, status.text
    assert status.json()["state"] == "authenticated"

    health = httpx.get(f"{sf_base_url}/codex/health", timeout=10)
    assert health.status_code == 200, health.text
    assert health.json()["authenticated"] is True

    run = httpx.post(
        f"{sf_base_url}/codex/run",
        json={"prompt": "Say codex e2e ok.", "model": "codex/gpt-5.4-mini"},
        timeout=30,
    )
    logs = "\n".join(manager.logs.dump_last(2000)) if manager.logs else ""
    assert run.status_code == 200, f"{run.text}\n--- logs ---\n{logs[-5000:]}"
    body = run.json()
    assert body["ec"] == 0
    assert body["so"] == "codex e2e ok"

    assert fake_codex.requests
    request = fake_codex.requests[-1]
    assert request["path"] == "/responses"
    assert request["headers"]["Authorization"].startswith("Bearer ")
    assert request["headers"]["ChatGPT-Account-Id"] == "chatgpt-account-e2e"
    assert request["body"]["model"] == "gpt-5.4-mini"
    assert request["body"]["stream"] is True

    assert "POST /v1/chat/completions" in logs
    gateway_health = httpx.get(f"http://127.0.0.1:{gateway_port}/healthz", timeout=3)
    assert gateway_health.status_code == 200
