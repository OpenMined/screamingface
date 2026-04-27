"""Tests for the data-store plugin — blob storage and retrieval."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.data_store.storage import BlobStore

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
# In-process API — BlobStore class is used directly. The data-store
# plugin attaches a single instance to ``app.state.blob_store`` which
# is exercised via the HTTP route tests below.
# ---------------------------------------------------------------------------


def test_blobstore_returns_key() -> None:
    store = BlobStore()
    key = store.store(b"hello world")
    assert isinstance(key, str)
    assert len(key) == 16


def test_blobstore_content_addressed() -> None:
    store = BlobStore()
    assert store.store(b"same content") == store.store(b"same content")


def test_blobstore_different_content() -> None:
    store = BlobStore()
    assert store.store(b"aaa") != store.store(b"bbb")


def test_blobstore_get_returns_data() -> None:
    store = BlobStore()
    key = store.store(b"test data", "text/plain")
    result = store.get(key)
    assert result == (b"test data", "text/plain")


def test_blobstore_get_missing_key() -> None:
    assert BlobStore().get("nonexistent_key_") is None


def test_plugin_attaches_blob_store_to_app_state(app: FastAPI) -> None:
    assert isinstance(app.state.blob_store, BlobStore)


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
