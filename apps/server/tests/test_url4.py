"""Tests for the url4 spec — parsing and resolution."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from screamingface.core.url4 import is_url, parse_context, resolve

# ---------------------------------------------------------------------------
# parse_context tests
# ---------------------------------------------------------------------------


def test_parse_plain_string() -> None:
    assert parse_context("hello world") == "hello world"


def test_parse_plain_string_no_parens() -> None:
    assert parse_context("just a string") == "just a string"


def test_parse_single_item_list() -> None:
    result = parse_context("(hello)")
    assert result == ["hello"]


def test_parse_multi_item_list() -> None:
    result = parse_context("(http://a.com, some text, http://b.com)")
    assert result == ["http://a.com", "some text", "http://b.com"]


def test_parse_nested_list() -> None:
    result = parse_context("(http://a.com, (http://b.com, inner text))")
    assert result == ["http://a.com", "(http://b.com, inner text)"]


def test_parse_strips_whitespace() -> None:
    result = parse_context("(  http://a.com ,  hello  )")
    assert result == ["http://a.com", "hello"]


def test_parse_empty_parens() -> None:
    result = parse_context("()")
    assert result == []


# ---------------------------------------------------------------------------
# is_url tests
# ---------------------------------------------------------------------------


def test_is_url_http() -> None:
    assert is_url("http://example.com") is True


def test_is_url_https() -> None:
    assert is_url("https://example.com/path?q=1") is True


def test_is_url_plain_string() -> None:
    assert is_url("just a string") is False


def test_is_url_nested_parens() -> None:
    assert is_url("(http://a.com, http://b.com)") is False


# ---------------------------------------------------------------------------
# resolve tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_resolve_plain_string() -> None:
    result = await resolve("hello world")
    assert result == "hello world"


@pytest.mark.anyio
async def test_resolve_url_fetches() -> None:
    with patch(
        "screamingface.core.url4._fetch_url",
        new_callable=AsyncMock,
        return_value="fetched content",
    ):
        result = await resolve("http://example.com/data")
        assert result == "fetched content"


@pytest.mark.anyio
async def test_resolve_list_mixed() -> None:
    with patch(
        "screamingface.core.url4._fetch_url",
        new_callable=AsyncMock,
        return_value="from url",
    ):
        result = await resolve("(http://example.com, raw text here)")
        assert result == "from url\nraw text here"


@pytest.mark.anyio
async def test_resolve_nested_list() -> None:
    with patch(
        "screamingface.core.url4._fetch_url",
        new_callable=AsyncMock,
        return_value="fetched",
    ):
        result = await resolve("(hello, (http://a.com, world))")
        assert result == "hello\nfetched\nworld"
