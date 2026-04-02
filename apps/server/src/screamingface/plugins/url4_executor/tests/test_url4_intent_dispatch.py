"""Tests for url4-executor intent handling via Url4Interpreter."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FETCH_PATCH = "screamingface.plugins.url4_executor.url4._fetch_url"
_INTENT_FETCH_PATCH = "screamingface.plugins.url4_executor.interpreter._fetch_url"


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
    resp = client.get("/ensemble", params={"q": "hello"})
    assert resp.status_code == 200
    assert resp.text == "hello"


def test_empty_intent_no_dispatch(client: TestClient) -> None:
    """q=hello! (empty intent) treated as no intent."""
    resp = client.get("/ensemble", params={"q": "hello!"})
    assert resp.status_code == 200
    assert resp.text == "hello"


# ---------------------------------------------------------------------------
# Text intent — combines intent + sources
# ---------------------------------------------------------------------------


def test_intent_text_returns_combined(client: TestClient) -> None:
    """Plain text intent returns intent + resolved sources."""
    resp = client.get("/ensemble", params={"q": "hello!summarize"})
    assert resp.status_code == 200
    assert "summarize" in resp.text
    assert "hello" in resp.text


def test_intent_text_with_fetched_source(client: TestClient) -> None:
    """Text intent with fetched source URL."""
    with patch(_FETCH_PATCH, new_callable=AsyncMock, return_value="fetched docs"):
        resp = client.get(
            "/ensemble",
            params={"q": "(http://example.com)!summarize this"},
        )
    assert resp.status_code == 200
    assert "summarize this" in resp.text
    assert "fetched docs" in resp.text


def test_intent_quoted_text(client: TestClient) -> None:
    """Quoted text intent has quotes stripped."""
    resp = client.get("/ensemble", params={"q": "hello!\"summarize\""})
    assert resp.status_code == 200
    assert "summarize" in resp.text
    assert '"' not in resp.text


# ---------------------------------------------------------------------------
# URL intent — fetches the URL
# ---------------------------------------------------------------------------


def test_intent_http_url_fetches(client: TestClient) -> None:
    """HTTP URL intent is fetched and returned."""
    with (
        patch(_FETCH_PATCH, new_callable=AsyncMock, return_value="source text"),
        patch(_INTENT_FETCH_PATCH, new_callable=AsyncMock, return_value="backend answer"),
    ):
        resp = client.get(
            "/ensemble",
            params={"q": "hello!http://localhost:8000/claude/default?prompt=test"},
        )
    assert resp.status_code == 200
    assert "backend answer" in resp.text


def test_intent_http_url_with_sources(client: TestClient) -> None:
    """HTTP URL intent combined with resolved sources."""
    with (
        patch(_FETCH_PATCH, new_callable=AsyncMock, return_value="fetched docs"),
        patch(_INTENT_FETCH_PATCH, new_callable=AsyncMock, return_value="backend result"),
    ):
        resp = client.get(
            "/ensemble",
            params={"q": "(http://example.com)!http://backend.com/api"},
        )
    assert resp.status_code == 200
    assert "backend result" in resp.text
    assert "fetched docs" in resp.text


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_intent_fetch_error_502(client: TestClient) -> None:
    """Failed URL fetch → 502."""
    with patch(
        _INTENT_FETCH_PATCH,
        new_callable=AsyncMock,
        side_effect=Exception("connection refused"),
    ):
        resp = client.get(
            "/ensemble",
            params={"q": "hello!http://localhost:8000/bad-endpoint"},
        )
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# AST mode
# ---------------------------------------------------------------------------


def test_ast_mode_with_text_intent(client: TestClient) -> None:
    """ast=true returns JSON with ast and result."""
    resp = client.get(
        "/ensemble",
        params={"q": "hello!summarize", "ast": "true"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ast"] == {"type": "text", "value": "hello"}
    assert "summarize" in data["result"]
    assert "hello" in data["result"]
