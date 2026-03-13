"""Tests for the url-executor plugin — /url4 endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.url_executor.plugin import UrlExecutorSettings

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app_with_executor() -> FastAPI:
    with patch("shutil.which", return_value="/usr/local/bin/claude"):
        config = AppConfig(
            plugins=["url-executor"],
            plugin_config={"url-executor": {}},
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
    assert settings is not None


# ---------------------------------------------------------------------------
# /url4 endpoint tests
# ---------------------------------------------------------------------------


def test_url4_missing_context(client: TestClient) -> None:
    resp = client.get("/url4")
    assert resp.status_code == 400
    assert "context" in resp.json()["detail"].lower()


def test_url4_plain_string(client: TestClient) -> None:
    resp = client.get("/url4?context=hello+world")
    assert resp.status_code == 200
    assert resp.text == "hello world"


def test_url4_list_with_strings(client: TestClient) -> None:
    resp = client.get("/url4?context=(hello, world)")
    assert resp.status_code == 200
    assert resp.text == "hello\nworld"


def test_url4_list_with_url(client: TestClient) -> None:
    with patch(
        "screamingface.core.url4._fetch_url",
        new_callable=AsyncMock,
        return_value="fetched data",
    ):
        resp = client.get("/url4?context=(http://example.com, extra text)")
        assert resp.status_code == 200
        assert "fetched data" in resp.text
        assert "extra text" in resp.text


def test_url4_nested(client: TestClient) -> None:
    with patch(
        "screamingface.core.url4._fetch_url",
        new_callable=AsyncMock,
        return_value="from url",
    ):
        resp = client.get("/url4?context=(outer, (http://a.com, inner))")
        assert resp.status_code == 200
        assert "outer" in resp.text
        assert "from url" in resp.text
        assert "inner" in resp.text
