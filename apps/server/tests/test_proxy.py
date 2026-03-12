"""Tests for the claude-proxy plugin."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.core.url4 import clear_cache as clear_url4_cache


@pytest.fixture
def proxy_app() -> FastAPI:
    config = AppConfig(
        plugins=["claude-proxy"],
        plugin_config={
            "claude-proxy": {
                "upstream_url": "https://api.anthropic.com",
                "api_key_env": "ANTHROPIC_API_KEY",
            }
        },
    )
    return create_app(config)


@pytest.fixture
def proxy_client(proxy_app: FastAPI) -> TestClient:
    return TestClient(proxy_app)


def test_proxy_plugin_discovered(proxy_app: FastAPI) -> None:
    active = proxy_app.state.plugins.active_plugins
    assert "claude-proxy" in active


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
        plugins=["claude-proxy"],
        plugin_config={
            "claude-proxy": {
                "upstream_url": "https://api.anthropic.com",
                "api_key_env": "ANTHROPIC_API_KEY",
            }
        },
        url4config="url4://test/rules",
    )
    return create_app(config)


@pytest.fixture
def proxy_client_with_url4(proxy_app_with_url4: FastAPI) -> TestClient:
    clear_url4_cache()
    return TestClient(proxy_app_with_url4)


def test_proxy_url4_enrichment_string_system(proxy_client_with_url4: TestClient) -> None:
    mock_response = httpx.Response(200, json={"id": "msg_u4_1"})

    with patch(
        "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
    ) as mock_post:
        proxy_client_with_url4.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-4-20250514",
                "messages": [{"role": "user", "content": "Hi"}],
                "system": "Be helpful.",
            },
            headers={"x-api-key": "test-key", "anthropic-version": "2023-06-01"},
        )

    sent_body = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1]["json"]
    system = sent_body["system"]
    assert isinstance(system, str)
    assert "url4://test/rules" in system
    assert system.endswith("Be helpful.")


def test_proxy_url4_enrichment_array_system(proxy_client_with_url4: TestClient) -> None:
    mock_response = httpx.Response(200, json={"id": "msg_u4_2"})

    with patch(
        "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
    ) as mock_post:
        proxy_client_with_url4.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-4-20250514",
                "messages": [{"role": "user", "content": "Hi"}],
                "system": [{"type": "text", "text": "Be helpful."}],
            },
            headers={"x-api-key": "test-key", "anthropic-version": "2023-06-01"},
        )

    sent_body = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1]["json"]
    system = sent_body["system"]
    assert isinstance(system, list)
    assert len(system) == 2
    assert system[0]["type"] == "text"
    assert "url4://test/rules" in system[0]["text"]
    assert system[1]["text"] == "Be helpful."


def test_proxy_url4_enrichment_no_system(proxy_client_with_url4: TestClient) -> None:
    mock_response = httpx.Response(200, json={"id": "msg_u4_3"})

    with patch(
        "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
    ) as mock_post:
        proxy_client_with_url4.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-4-20250514",
                "messages": [{"role": "user", "content": "Hi"}],
            },
            headers={"x-api-key": "test-key", "anthropic-version": "2023-06-01"},
        )

    sent_body = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1]["json"]
    system = sent_body["system"]
    assert isinstance(system, str)
    assert "url4://test/rules" in system
