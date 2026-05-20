"""Tests for relative URL parsing and parallel resolution."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.url4_executor import url4_resolve
from screamingface.plugins.url4_executor.url4 import (
    Url4List,
    Url4RelUrl,
    Url4Text,
    Url4Url,
    parse,
    resolve,
    resolve_str,
)

_FETCH_URL = "screamingface.plugins.url4_executor.url4_resolve._fetch_url"
_FETCH_REL = "screamingface.plugins.url4_executor.url4_resolve._fetch_relative"

# ---------------------------------------------------------------------------
# Parsing — Url4RelUrl
# ---------------------------------------------------------------------------


def test_parse_simple_relurl() -> None:
    result = parse("/data/abc")
    assert isinstance(result, Url4RelUrl)
    assert result.value == "/data/abc"


def test_parse_relurl_with_query() -> None:
    result = parse("/claude?q=hello")
    assert isinstance(result, Url4RelUrl)
    assert result.value == "/claude?q=hello"


def test_parse_relurl_with_balanced_parens() -> None:
    result = parse("/claude?q=(a,b,c)")
    assert isinstance(result, Url4RelUrl)
    assert result.value == "/claude?q=(a,b,c)"


def test_parse_relurl_empty_parens() -> None:
    result = parse("/claude?q=()")
    assert isinstance(result, Url4RelUrl)
    assert result.value == "/claude?q=()"


def test_parse_list_of_relurls() -> None:
    result = parse("(/data/a, /data/b, /data/c)")
    assert isinstance(result, Url4List)
    assert len(result.items) == 3
    assert all(isinstance(item, Url4RelUrl) for item in result.items)


def test_parse_mixed_url_and_relurl() -> None:
    result = parse("(https://example.com, /data/abc)")
    assert isinstance(result, Url4List)
    assert isinstance(result.items[0], Url4Url)
    assert isinstance(result.items[1], Url4RelUrl)


def test_parse_mixed_text_and_relurl() -> None:
    result = parse("(hello, /data/abc)")
    assert isinstance(result, Url4List)
    assert isinstance(result.items[0], Url4Text)
    assert isinstance(result.items[1], Url4RelUrl)


# ---------------------------------------------------------------------------
# Resolution — relative URLs
# ---------------------------------------------------------------------------


def test_resolve_relurl_calls_fetch_relative() -> None:
    async def _run():
        with patch(
            _FETCH_REL,
            new_callable=AsyncMock,
            return_value="blob data",
        ) as mock:
            result = await resolve(Url4RelUrl("/data/abc"), app="fake")
        return result, mock

    result, mock = asyncio.run(_run())
    assert result == "blob data"
    mock.assert_called_once_with("fake", "/data/abc")


def test_resolve_relurl_no_app_raises() -> None:
    async def _run():
        await resolve(Url4RelUrl("/data/abc"), app=None)

    with pytest.raises(ValueError, match="without app"):
        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Parallel resolution
# ---------------------------------------------------------------------------


def test_list_resolves_in_parallel() -> None:
    async def slow_fetch(url: str) -> str:
        await asyncio.sleep(0.1)
        return f"result-{url}"

    node = Url4List(
        items=(
            Url4Url("http://a.com"),
            Url4Url("http://b.com"),
            Url4Url("http://c.com"),
        )
    )

    async def _run():
        with patch(_FETCH_URL, side_effect=slow_fetch):
            start = time.monotonic()
            result = await resolve(node)
            elapsed = time.monotonic() - start
        return result, elapsed

    result, elapsed = asyncio.run(_run())
    # 3 items at 0.1s each — sequential ~0.3s, parallel < 0.2s
    assert elapsed < 0.25
    assert "result-http://a.com" in result
    assert "result-http://b.com" in result
    assert "result-http://c.com" in result


# ---------------------------------------------------------------------------
# resolve_str with app parameter
# ---------------------------------------------------------------------------


def test_resolve_str_passes_app() -> None:
    async def _run():
        with patch(
            _FETCH_REL,
            new_callable=AsyncMock,
            return_value="fetched",
        ) as mock:
            result = await resolve_str("/data/abc", app="my_app")
        return result, mock

    result, mock = asyncio.run(_run())
    assert result == "fetched"
    mock.assert_called_once_with("my_app", "/data/abc")


def test_fetch_url_uses_default_tls_verification(monkeypatch) -> None:
    captured_kwargs: dict = {}

    class _Response:
        status_code = 200
        text = "ok"

        def raise_for_status(self) -> None:
            return None

    class _AsyncClient:
        def __init__(self, **kwargs) -> None:
            captured_kwargs.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, _url: str) -> _Response:
            return _Response()

    monkeypatch.setattr(url4_resolve.httpx, "AsyncClient", _AsyncClient)

    result = asyncio.run(url4_resolve._fetch_url("https://example.com"))

    assert result == "ok"
    assert "verify" not in captured_kwargs


# ---------------------------------------------------------------------------
# Integration — /ensemble with data-store blobs
# ---------------------------------------------------------------------------


@pytest.fixture
def app() -> FastAPI:
    config = AppConfig(plugins=["url4-executor", "data-store"], plugin_config={})
    return create_app(config)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_ensemble_with_data_store_blob(client: TestClient) -> None:
    """Store a blob, then resolve it via /ensemble."""
    # Store
    resp = client.post(
        "/data",
        content=b"blob content",
        headers={"content-type": "text/plain"},
    )
    key = resp.json()["key"]

    # Resolve — /ensemble fetches /data/{key} via in-process ASGI
    resp = client.get("/ensemble", params={"q": f"/data/{key}"})
    assert resp.status_code == 200
    assert resp.text == "blob content"
