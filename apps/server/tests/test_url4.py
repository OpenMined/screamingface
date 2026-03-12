"""Tests for the url4 mock executor and caching."""

from __future__ import annotations

import pytest

from screamingface.core.url4 import clear_cache, resolve_url4_context


@pytest.fixture(autouse=True)
def _clear_url4_cache() -> None:
    clear_cache()


@pytest.mark.anyio
async def test_resolve_returns_string() -> None:
    result = await resolve_url4_context("url4://test/rules")
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.anyio
async def test_resolve_is_cached() -> None:
    first = await resolve_url4_context("url4://test/cached")
    second = await resolve_url4_context("url4://test/cached")
    assert first is second


@pytest.mark.anyio
async def test_resolve_includes_url_in_mock() -> None:
    url = "url4://my-project/context"
    result = await resolve_url4_context(url)
    assert url in result
