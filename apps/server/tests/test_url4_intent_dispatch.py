"""Tests for url4-executor intent dispatch to backend URLs."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FETCH_PATCH = "screamingface.plugins.url4_executor.url4._fetch_url"
_HTTPX_CLIENT = "screamingface.plugins.url4_executor.routes.httpx.AsyncClient"


def _mock_httpx_response(text: str = "", status_code: int = 200) -> httpx.Response:
    """Create a fake httpx.Response."""
    return httpx.Response(status_code=status_code, text=text)


def _mock_async_client(response: httpx.Response) -> AsyncMock:
    """Create a mock httpx.AsyncClient that returns the given response on GET."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app() -> FastAPI:
    config = AppConfig(
        plugins=["url4-executor"],
        plugin_config={},
    )
    return create_app(config)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# No intent (existing behavior unchanged)
# ---------------------------------------------------------------------------


def test_no_intent_plain_text(client: TestClient) -> None:
    resp = client.get("/url4", params={"q": "hello"})
    assert resp.status_code == 200
    assert resp.text == "hello"


def test_empty_intent_no_dispatch(client: TestClient) -> None:
    """q=hello! (empty intent) treated as no intent."""
    resp = client.get("/url4", params={"q": "hello!"})
    assert resp.status_code == 200
    assert resp.text == "hello"


# ---------------------------------------------------------------------------
# Intent must be a URL
# ---------------------------------------------------------------------------


def test_intent_non_url_rejected(client: TestClient) -> None:
    """Plain text intent (not a URL) returns 400."""
    resp = client.get("/url4", params={"q": "hello!summarize"})
    assert resp.status_code == 400
    assert "backend URL" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Intent dispatch to backend URL
# ---------------------------------------------------------------------------


def test_intent_dispatch_to_backend(client: TestClient) -> None:
    """Resolved content dispatched to backend URL with context param."""
    mock_resp = _mock_httpx_response(text="Backend answer")
    mock_client = _mock_async_client(mock_resp)

    with patch(_HTTPX_CLIENT, return_value=mock_client):
        resp = client.get(
            "/url4",
            params={"q": "hello!http://localhost:8000/claude/default?prompt=summarize"},
        )

    assert resp.status_code == 200
    assert resp.text == "Backend answer"

    # Verify the backend was called with context appended
    call_url = mock_client.get.call_args[0][0]
    assert "prompt=summarize" in call_url
    assert "context=hello" in call_url


def test_intent_dispatch_with_fetched_url(client: TestClient) -> None:
    """Fetches resource URL, then dispatches resolved content to backend."""
    mock_resp = _mock_httpx_response(text="Analysis result")
    mock_client = _mock_async_client(mock_resp)

    with (
        patch(_FETCH_PATCH, new_callable=AsyncMock, return_value="fetched docs"),
        patch(_HTTPX_CLIENT, return_value=mock_client),
    ):
        resp = client.get(
            "/url4",
            params={"q": "(http://example.com)!http://localhost:8000/claude/default?prompt=analyze"},
        )

    assert resp.status_code == 200
    assert resp.text == "Analysis result"

    call_url = mock_client.get.call_args[0][0]
    assert "prompt=analyze" in call_url
    assert "context=fetched+docs" in call_url


def test_intent_no_source(client: TestClient) -> None:
    """Empty source with backend URL — dispatches without context."""
    mock_resp = _mock_httpx_response(text="No context response")
    mock_client = _mock_async_client(mock_resp)

    with patch(_HTTPX_CLIENT, return_value=mock_client):
        resp = client.get(
            "/url4",
            params={"q": "!http://localhost:8000/claude/default?prompt=hello"},
        )

    assert resp.status_code == 200
    assert resp.text == "No context response"

    call_url = mock_client.get.call_args[0][0]
    assert "prompt=hello" in call_url
    # No context param since source was empty
    assert "context=" not in call_url


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_intent_backend_error_502(client: TestClient) -> None:
    """Backend returns error status -> HTTP 502."""
    mock_resp = _mock_httpx_response(text="Internal error", status_code=500)
    mock_client = _mock_async_client(mock_resp)

    with patch(_HTTPX_CLIENT, return_value=mock_client):
        resp = client.get(
            "/url4",
            params={"q": "hello!http://localhost:8000/claude/default?prompt=test"},
        )

    assert resp.status_code == 502
    assert "500" in resp.json()["detail"]


def test_intent_backend_timeout_504(client: TestClient) -> None:
    """Backend times out -> HTTP 504."""
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("read timeout"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch(_HTTPX_CLIENT, return_value=mock_client):
        resp = client.get(
            "/url4",
            params={"q": "hello!http://localhost:8000/claude/default?prompt=test"},
        )

    assert resp.status_code == 504
    assert "timed out" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# AST mode
# ---------------------------------------------------------------------------


def test_intent_ast_mode(client: TestClient) -> None:
    """ast=true returns JSON with ast, result, intent, and response."""
    mock_resp = _mock_httpx_response(text="Backend output")
    mock_client = _mock_async_client(mock_resp)

    with patch(_HTTPX_CLIENT, return_value=mock_client):
        resp = client.get(
            "/url4",
            params={
                "q": "hello!http://localhost:8000/claude/default?prompt=test",
                "ast": "true",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["ast"] == {"type": "text", "value": "hello"}
    assert data["result"] == "hello"
    assert data["intent"] == "http://localhost:8000/claude/default?prompt=test"
    assert data["response"] == "Backend output"
