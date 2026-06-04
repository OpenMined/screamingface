"""Tests for the claude-frontend proxy routes.

Inference (``POST /v1/messages``) is now TERMINAL: it synthesizes the Anthropic
response in-process and does NOT forward to the real upstream. The header-forwarding
and env-key tests therefore exercise the ``/v1/{path}`` catchall (which DOES still
forward upstream) instead of the inference route.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.claude_frontend.plugin import ClaudeFrontendSettings
from screamingface.plugins.claude_frontend.proxy import create_router


def test_proxy_non_streaming() -> None:
    """Non-streaming inference synthesizes a response; no upstream inference call.

    With ``get_active_expression()`` returning ``None`` (no active spec), no resolution
    happens and the handler synthesizes an empty Anthropic envelope rather than
    forwarding to ``api.anthropic.com``.
    """
    mock_plugin = MagicMock()
    mock_plugin.get_active_expression.return_value = None
    settings = ClaudeFrontendSettings(
        upstream_url="https://api.anthropic.com", active_spec="test-spec"
    )
    app = FastAPI()
    app.include_router(create_router(settings, plugin=mock_plugin))
    client = TestClient(app)
    with patch("httpx.AsyncClient.post") as mock_post:
        resp = client.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-4-20250514",
                "messages": [{"role": "user", "content": "Hi"}],
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "message"
    assert data["role"] == "assistant"
    assert data["content"][0]["text"] == ""
    assert not mock_post.called


def test_proxy_forwards_headers_on_catchall() -> None:
    """The ``/v1/{path}`` catchall (still upstream-forwarding) preserves auth headers."""
    settings = ClaudeFrontendSettings(upstream_url="https://api.anthropic.com")
    app = FastAPI()
    app.include_router(create_router(settings))
    client = TestClient(app)
    mock_response = httpx.Response(200, json={"data": []})
    with patch(
        "httpx.AsyncClient.request", new_callable=AsyncMock, return_value=mock_response
    ) as mock_req:
        client.get(
            "/v1/models",
            headers={"anthropic-version": "2023-06-01", "authorization": "Bearer test"},
        )
    sent_headers = mock_req.call_args.kwargs.get("headers", {})
    assert sent_headers.get("anthropic-version") == "2023-06-01"
    assert sent_headers.get("authorization") == "Bearer test"


def test_proxy_does_not_inject_env_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """ANTHROPIC_API_KEY must NOT be auto-forwarded as x-api-key on the catchall.

    All Anthropic auth flows through the Claude Code OAuth path served by
    aigateway. If a client sends no auth header, the proxy MUST NOT silently
    paper over it with an env var.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-be-ignored")
    settings = ClaudeFrontendSettings(upstream_url="https://api.anthropic.com")
    app = FastAPI()
    app.include_router(create_router(settings))
    client = TestClient(app)
    mock_response = httpx.Response(200, json={"data": []})
    with patch(
        "httpx.AsyncClient.request", new_callable=AsyncMock, return_value=mock_response
    ) as mock_req:
        client.get("/v1/models")
    sent_headers = mock_req.call_args.kwargs.get("headers", {})
    assert "x-api-key" not in sent_headers
    assert "authorization" not in sent_headers
