"""Tests for the claude-frontend proxy routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.plugins.claude_frontend.plugin import ClaudeFrontendSettings
from screamingface.plugins.claude_frontend.proxy import create_router


@pytest.fixture
def proxy_app() -> FastAPI:
    """Create a standalone FastAPI app with the proxy router (no full server startup)."""
    settings = ClaudeFrontendSettings(
        upstream_url="https://api.anthropic.com",
        api_key_env="ANTHROPIC_API_KEY",
    )
    app = FastAPI()
    router = create_router(settings)
    app.include_router(router)
    return app


@pytest.fixture
def proxy_client(proxy_app: FastAPI) -> TestClient:
    return TestClient(proxy_app)


def test_proxy_non_streaming(proxy_client: TestClient) -> None:
    mock_response = httpx.Response(
        200,
        json={"id": "msg_123", "content": [{"type": "text", "text": "Hello"}]},
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        resp = proxy_client.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-4-20250514",
                "messages": [{"role": "user", "content": "Hi"}],
            },
            headers={"x-api-key": "test-key", "anthropic-version": "2023-06-01"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "msg_123"


def test_proxy_forwards_headers(proxy_client: TestClient) -> None:
    mock_response = httpx.Response(200, json={"id": "msg_456"})

    with patch(
        "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
    ) as mock_post:
        proxy_client.post(
            "/v1/messages",
            json={"model": "claude-sonnet-4-20250514", "messages": []},
            headers={
                "x-api-key": "sk-test",
                "anthropic-version": "2023-06-01",
                "anthropic-beta": "messages-2024-01-01",
            },
        )

    call_kwargs = mock_post.call_args
    sent_headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
    assert sent_headers["x-api-key"] == "sk-test"
    assert sent_headers["anthropic-version"] == "2023-06-01"
    assert sent_headers["anthropic-beta"] == "messages-2024-01-01"


def test_proxy_auth_fallback(proxy_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env")
    mock_response = httpx.Response(200, json={"id": "msg_789"})

    with patch(
        "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
    ) as mock_post:
        proxy_client.post(
            "/v1/messages",
            json={"model": "claude-sonnet-4-20250514", "messages": []},
            # No x-api-key or authorization header
        )

    call_kwargs = mock_post.call_args
    sent_headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
    assert sent_headers["x-api-key"] == "sk-from-env"
