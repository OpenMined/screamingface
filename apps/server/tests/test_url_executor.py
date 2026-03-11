"""Tests for the url-executor plugin."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.url_executor.decoder import (
    build_dispatch_body,
    decode_prompt,
    parse_list,
)
from screamingface.plugins.url_executor.plugin import UrlExecutorSettings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mock_process(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> AsyncMock:
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.returncode = returncode
    proc.stdin = MagicMock()
    proc.stdin.write = MagicMock()
    proc.stdin.drain = AsyncMock()
    proc.stdin.close = MagicMock()
    proc.stdout = MagicMock()
    proc.stderr = MagicMock()
    proc.stderr.read = AsyncMock(return_value=stderr)
    proc.wait = AsyncMock()
    proc.kill = MagicMock()
    return proc


@pytest.fixture
def app_with_executor() -> FastAPI:
    with patch("shutil.which", return_value="/usr/local/bin/claude"):
        config = AppConfig(
            plugins=["claude-cli", "claude-proxy", "url-executor"],
            plugin_config={
                "claude-cli": {},
                "claude-proxy": {},
                "url-executor": {},
            },
        )
        return create_app(config)


@pytest.fixture
def client(app_with_executor: FastAPI) -> TestClient:
    return TestClient(app_with_executor)


# ---------------------------------------------------------------------------
# Plugin discovery & settings
# ---------------------------------------------------------------------------


def test_plugin_discovered(app_with_executor: FastAPI) -> None:
    active = app_with_executor.state.plugins.active_plugins
    assert "url-executor" in active


def test_settings_defaults() -> None:
    settings = UrlExecutorSettings()
    assert settings.max_prompt_length == 10_000
    assert settings.require_execute_header is True
    assert settings.show_preview_html is True


# ---------------------------------------------------------------------------
# Decoder unit tests
# ---------------------------------------------------------------------------


def test_decode_prompt_plain() -> None:
    assert decode_prompt({"p": "hello world"}, 10_000) == "hello world"


def test_decode_prompt_base64url() -> None:
    # "hello\nworld" in base64url without padding
    raw = "hello\nworld"
    encoded = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
    assert decode_prompt({"pb": encoded}, 10_000) == raw


def test_decode_prompt_pb_wins() -> None:
    raw = "from pb"
    encoded = base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")
    result = decode_prompt({"p": "from p", "pb": encoded}, 10_000)
    assert result == "from pb"


def test_decode_prompt_missing() -> None:
    with pytest.raises(ValueError, match="Missing prompt"):
        decode_prompt({}, 10_000)


def test_decode_prompt_too_long() -> None:
    with pytest.raises(ValueError, match="exceeds maximum length"):
        decode_prompt({"p": "x" * 101}, 100)


def test_parse_list() -> None:
    assert parse_list("bash,read,write") == ["bash", "read", "write"]
    assert parse_list("single") == ["single"]
    assert parse_list("") is None
    assert parse_list(None) is None


def test_build_dispatch_body() -> None:
    params = {"p": "hello", "m": "claude-sonnet-4-20250514", "e": "high", "t": "bash,read"}
    body = build_dispatch_body(params, "hello")
    assert body["p"] == "hello"
    assert body["m"] == "claude-sonnet-4-20250514"
    assert body["e"] == "high"
    assert body["t"] == ["bash", "read"]


# ---------------------------------------------------------------------------
# Route integration tests
# ---------------------------------------------------------------------------


def test_cli_dispatch(client: TestClient) -> None:
    proc = _mock_process(stdout=b"result text", stderr=b"")
    with patch(
        "screamingface.plugins.claude_cli.runner.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=proc,
    ):
        resp = client.get(
            "/x/cli?p=hello",
            headers={"Accept": "application/json", "X-SF-Execute": "true"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["ec"] == 0
    assert data["so"] == "result text"


def test_proxy_dispatch(client: TestClient) -> None:
    """Test /x/proxy dispatches to /v1/messages."""
    import httpx

    mock_response = httpx.Response(
        200,
        json={"id": "msg_123", "content": [{"type": "text", "text": "hi"}]},
    )
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        resp = client.get(
            "/x/proxy?p=hello&m=claude-sonnet-4-20250514",
            headers={"Accept": "application/json", "X-SF-Execute": "true"},
        )

    # The proxy dispatches internally; the response depends on the proxy plugin behavior
    assert resp.status_code == 200


def test_unknown_backend(client: TestClient) -> None:
    resp = client.get(
        "/x/unknown?p=hello",
        headers={"Accept": "application/json", "X-SF-Execute": "true"},
    )
    assert resp.status_code == 404


def test_prompt_too_long(client: TestClient) -> None:
    long_prompt = "x" * 10_001
    resp = client.get(
        f"/x/cli?p={long_prompt}",
        headers={"Accept": "application/json", "X-SF-Execute": "true"},
    )
    assert resp.status_code == 400
    assert "exceeds" in resp.json()["detail"].lower()


def test_browser_preview(client: TestClient) -> None:
    resp = client.get("/x/cli?p=hello", headers={"Accept": "text/html"})
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Execute" in resp.text
    assert "hello" in resp.text


def test_execute_header(client: TestClient) -> None:
    """X-SF-Execute: true bypasses preview even with Accept: text/html."""
    proc = _mock_process(stdout=b"executed", stderr=b"")
    with patch(
        "screamingface.plugins.claude_cli.runner.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=proc,
    ):
        resp = client.get(
            "/x/cli?p=hello",
            headers={"Accept": "text/html", "X-SF-Execute": "true"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["ec"] == 0


def test_stream_passthrough(client: TestClient) -> None:
    async def fake_stdout_iter():
        for line in [b'{"type":"text","text":"hi"}\n']:
            yield line

    proc = _mock_process()
    proc.stdout.__aiter__ = lambda self: fake_stdout_iter()
    proc.stderr.read = AsyncMock(return_value=b"")

    with patch(
        "screamingface.plugins.claude_cli.runner.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=proc,
    ):
        resp = client.get(
            "/x/cli?p=hello&stream=1",
            headers={"Accept": "application/json", "X-SF-Execute": "true"},
        )

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]


def test_default_action(client: TestClient) -> None:
    """``/x/cli?p=...`` and ``/x/cli/run?p=...`` should behave identically."""
    proc = _mock_process(stdout=b"same", stderr=b"")
    with patch(
        "screamingface.plugins.claude_cli.runner.asyncio.create_subprocess_exec",
        new_callable=AsyncMock,
        return_value=proc,
    ):
        resp1 = client.get(
            "/x/cli?p=hello",
            headers={"Accept": "application/json", "X-SF-Execute": "true"},
        )
        resp2 = client.get(
            "/x/cli/run?p=hello",
            headers={"Accept": "application/json", "X-SF-Execute": "true"},
        )

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json() == resp2.json()
