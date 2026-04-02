"""Tests for the data-store plugin — blob storage and retrieval."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.data_store.routes import get_blob, store_blob

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app() -> FastAPI:
    config = AppConfig(plugins=["data-store"], plugin_config={})
    return create_app(config)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# In-process API (store_blob / get_blob)
# ---------------------------------------------------------------------------


def test_store_blob_returns_key() -> None:
    key = store_blob(b"hello world")
    assert isinstance(key, str)
    assert len(key) == 16


def test_store_blob_content_addressed() -> None:
    k1 = store_blob(b"same content")
    k2 = store_blob(b"same content")
    assert k1 == k2


def test_store_blob_different_content() -> None:
    k1 = store_blob(b"aaa")
    k2 = store_blob(b"bbb")
    assert k1 != k2


def test_get_blob_returns_data() -> None:
    key = store_blob(b"test data", "text/plain")
    result = get_blob(key)
    assert result is not None
    data, ct = result
    assert data == b"test data"
    assert ct == "text/plain"


def test_get_blob_missing_key() -> None:
    assert get_blob("nonexistent_key_") is None


# ---------------------------------------------------------------------------
# HTTP endpoints
# ---------------------------------------------------------------------------


def test_post_data_creates_blob(client: TestClient) -> None:
    resp = client.post(
        "/data",
        content=b"hello from test",
        headers={"content-type": "text/plain"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "key" in data
    assert "url" in data
    assert data["url"].startswith("/data/")


def test_post_data_empty_body_400(client: TestClient) -> None:
    resp = client.post("/data", content=b"")
    assert resp.status_code == 400
    assert "Empty" in resp.json()["detail"]


def test_get_data_retrieves_blob(client: TestClient) -> None:
    # Store
    resp = client.post(
        "/data",
        content=b"retrieve me",
        headers={"content-type": "text/plain; charset=utf-8"},
    )
    key = resp.json()["key"]

    # Retrieve
    resp = client.get(f"/data/{key}")
    assert resp.status_code == 200
    assert resp.text == "retrieve me"
    assert "text/plain" in resp.headers["content-type"]


def test_get_data_not_found(client: TestClient) -> None:
    resp = client.get("/data/0000000000000000")
    assert resp.status_code == 404


def test_roundtrip_binary(client: TestClient) -> None:
    binary = bytes(range(256))
    resp = client.post(
        "/data",
        content=binary,
        headers={"content-type": "application/octet-stream"},
    )
    key = resp.json()["key"]

    resp = client.get(f"/data/{key}")
    assert resp.status_code == 200
    assert resp.content == binary


def test_plugin_discovered(app: FastAPI) -> None:
    assert "data-store" in app.state.plugins.active_plugins
