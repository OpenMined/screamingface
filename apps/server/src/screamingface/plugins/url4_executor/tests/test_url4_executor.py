"""Tests for the url4-executor plugin — /ensemble endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app_with_executor() -> FastAPI:
    config = AppConfig(
        plugins=["url4-executor"],
        plugin_config={},
    )
    return create_app(config)


@pytest.fixture
def client(app_with_executor: FastAPI) -> TestClient:
    return TestClient(app_with_executor)


# ---------------------------------------------------------------------------
# Plugin discovery
# ---------------------------------------------------------------------------


def test_plugin_discovered(app_with_executor: FastAPI) -> None:
    active = app_with_executor.state.plugins.active_plugins
    assert "url4-executor" in active


# ---------------------------------------------------------------------------
# /ensemble endpoint tests
# ---------------------------------------------------------------------------


def test_url4_missing_q(client: TestClient) -> None:
    resp = client.get("/ensemble")
    assert resp.status_code == 400
    assert "'q'" in resp.json()["detail"].lower()


def test_url4_plain_string(client: TestClient) -> None:
    resp = client.get("/ensemble?q=hello+world")
    assert resp.status_code == 200
    assert resp.text == "hello world"


def test_url4_list_with_strings(client: TestClient) -> None:
    resp = client.get("/ensemble?q=(hello, world)")
    assert resp.status_code == 200
    assert resp.text == "hello\nworld"


def test_url4_list_with_url(client: TestClient) -> None:
    with patch(
        "screamingface.plugins.url4_executor.url4_resolve._fetch_url",
        new_callable=AsyncMock,
        return_value="fetched data",
    ):
        resp = client.get("/ensemble?q=(http://example.com, extra text)")
        assert resp.status_code == 200
        assert "fetched data" in resp.text
        assert "extra text" in resp.text


def test_url4_nested(client: TestClient) -> None:
    with patch(
        "screamingface.plugins.url4_executor.url4_resolve._fetch_url",
        new_callable=AsyncMock,
        return_value="from url",
    ):
        resp = client.get("/ensemble?q=(outer, (http://a.com, inner))")
        assert resp.status_code == 200
        assert "outer" in resp.text
        assert "from url" in resp.text
        assert "inner" in resp.text


# ---------------------------------------------------------------------------
# ?ast=true tests
# ---------------------------------------------------------------------------


def test_url4_ast_plain_string(client: TestClient) -> None:
    resp = client.get("/ensemble?q=hello+world&ast=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ast"]["type"] == "text"
    assert data["ast"]["value"] == "hello world"
    assert data["result"] == "hello world"


def test_url4_ast_list(client: TestClient) -> None:
    with patch(
        "screamingface.plugins.url4_executor.url4_resolve._fetch_url",
        new_callable=AsyncMock,
        return_value="fetched",
    ):
        resp = client.get("/ensemble?q=(http://a.com, hello)&ast=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ast"]["type"] == "list"
        assert len(data["ast"]["items"]) == 2
        assert data["ast"]["items"][0]["type"] == "url"
        assert data["ast"]["items"][1]["type"] == "text"
        assert "fetched" in data["result"]
