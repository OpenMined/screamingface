"""Tests for the claude-frontend plugin."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig


@pytest.fixture
def proxy_app() -> FastAPI:
    config = AppConfig(
        plugins=["claude-frontend"],
        url4config=None,
        plugin_config={
            "claude-frontend": {
                "upstream_url": "https://api.anthropic.com",
                "api_key_env": "ANTHROPIC_API_KEY",
            }
        },
    )
    with patch("shutil.which", return_value="/usr/bin/claude"):
        return create_app(config)


@pytest.fixture
def proxy_client(proxy_app: FastAPI) -> TestClient:
    return TestClient(proxy_app)


def test_proxy_plugin_discovered(proxy_app: FastAPI) -> None:
    active = proxy_app.state.plugins.active_plugins
    assert "claude-frontend" in active


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


# ---------------------------------------------------------------------------
# url4 enrichment tests
# ---------------------------------------------------------------------------


@pytest.fixture
def proxy_app_with_url4() -> FastAPI:
    config = AppConfig(
        plugins=["claude-frontend"],
        plugin_config={
            "claude-frontend": {
                "upstream_url": "https://api.anthropic.com",
                "api_key_env": "ANTHROPIC_API_KEY",
            }
        },
        url4config="url4://test/rules",
    )
    with patch("shutil.which", return_value="/usr/bin/claude"):
        return create_app(config)


@pytest.fixture
def proxy_client_with_url4(proxy_app_with_url4: FastAPI) -> TestClient:
    return TestClient(proxy_app_with_url4)


def test_proxy_url4_returns_synthetic_response(proxy_client_with_url4: TestClient) -> None:
    """When url4 resolves, proxy returns the result directly as a synthetic response."""
    with patch(
        "screamingface.core.url4.resolve",
        new_callable=AsyncMock,
        return_value="Here is your enriched context.",
    ):
        resp = proxy_client_with_url4.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-4-20250514",
                "messages": [{"role": "user", "content": "Hi"}],
                "system": "Be helpful.",
            },
            headers={"x-api-key": "test-key", "anthropic-version": "2023-06-01"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "message"
    assert data["role"] == "assistant"
    assert data["content"][0]["type"] == "text"
    assert data["content"][0]["text"] == "Here is your enriched context."
    assert data["stop_reason"] == "end_turn"
    assert data["id"].startswith("msg_sf_")


def test_proxy_url4_skips_when_assistant_present(proxy_client_with_url4: TestClient) -> None:
    """url4 enrichment is skipped on follow-up turns (assistant messages present)."""
    mock_response = httpx.Response(200, json={"id": "msg_followup"})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        resp = proxy_client_with_url4.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-4-20250514",
                "messages": [
                    {"role": "user", "content": "Hi"},
                    {"role": "assistant", "content": "Hello!"},
                    {"role": "user", "content": "Follow up"},
                ],
            },
            headers={"x-api-key": "test-key", "anthropic-version": "2023-06-01"},
        )

    assert resp.status_code == 200
    assert resp.json()["id"] == "msg_followup"


def test_proxy_url4_falls_through_on_failure(proxy_client_with_url4: TestClient) -> None:
    """When url4 resolution fails, proxy falls through to Anthropic."""
    mock_response = httpx.Response(200, json={"id": "msg_fallback"})

    with (
        patch(
            "screamingface.core.url4.resolve",
            new_callable=AsyncMock,
            side_effect=Exception("resolve failed"),
        ),
        patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response),
    ):
        resp = proxy_client_with_url4.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-4-20250514",
                "messages": [{"role": "user", "content": "Hi"}],
            },
            headers={"x-api-key": "test-key", "anthropic-version": "2023-06-01"},
        )

    assert resp.status_code == 200
    assert resp.json()["id"] == "msg_fallback"
