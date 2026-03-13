"""Tests for the url4 spec — TatSu parser + async resolver."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from screamingface.plugins.url4_executor.url4 import (
    Url4List,
    Url4Text,
    Url4Url,
    parse,
    resolve,
    resolve_str,
)

# ---------------------------------------------------------------------------
# Parser tests (synchronous — assert AST node types)
# ---------------------------------------------------------------------------


def test_parse_plain_string() -> None:
    node = parse("hello world")
    assert isinstance(node, Url4Text)
    assert node.value == "hello world"


def test_parse_url() -> None:
    node = parse("http://example.com/data")
    assert isinstance(node, Url4Url)
    assert node.value == "http://example.com/data"


def test_parse_https_url() -> None:
    node = parse("https://example.com/path?q=1")
    assert isinstance(node, Url4Url)
    assert node.value == "https://example.com/path?q=1"


def test_parse_single_item_list() -> None:
    node = parse("(hello)")
    assert isinstance(node, Url4List)
    assert len(node.items) == 1
    assert isinstance(node.items[0], Url4Text)
    assert node.items[0].value == "hello"


def test_parse_multi_item_list() -> None:
    node = parse("(http://a.com, some text, http://b.com)")
    assert isinstance(node, Url4List)
    assert len(node.items) == 3
    assert isinstance(node.items[0], Url4Url)
    assert node.items[0].value == "http://a.com"
    assert isinstance(node.items[1], Url4Text)
    assert node.items[1].value == "some text"
    assert isinstance(node.items[2], Url4Url)
    assert node.items[2].value == "http://b.com"


def test_parse_nested_list() -> None:
    node = parse("(http://a.com, (http://b.com, inner text))")
    assert isinstance(node, Url4List)
    assert len(node.items) == 2
    assert isinstance(node.items[0], Url4Url)
    assert isinstance(node.items[1], Url4List)
    inner = node.items[1]
    assert isinstance(inner, Url4List)
    assert len(inner.items) == 2
    assert isinstance(inner.items[0], Url4Url)
    assert isinstance(inner.items[1], Url4Text)


def test_parse_strips_whitespace() -> None:
    node = parse("  hello world  ")
    assert isinstance(node, Url4Text)
    assert node.value == "hello world"


def test_parse_list_strips_item_whitespace() -> None:
    node = parse("(  http://a.com ,  hello  )")
    assert isinstance(node, Url4List)
    assert node.items[0].value == "http://a.com"
    assert node.items[1].value == "hello"


# ---------------------------------------------------------------------------
# Resolver tests (async — mock _fetch_url)
# ---------------------------------------------------------------------------

PATCH_TARGET = "screamingface.plugins.url4_executor.url4._fetch_url"


@pytest.mark.anyio
async def test_resolve_text_node() -> None:
    node = Url4Text(value="hello world")
    result = await resolve(node)
    assert result == "hello world"


@pytest.mark.anyio
async def test_resolve_url_node() -> None:
    with patch(PATCH_TARGET, new_callable=AsyncMock, return_value="fetched content"):
        node = Url4Url(value="http://example.com/data")
        result = await resolve(node)
        assert result == "fetched content"


@pytest.mark.anyio
async def test_resolve_list_node() -> None:
    with patch(PATCH_TARGET, new_callable=AsyncMock, return_value="from url"):
        node = Url4List(
            items=(
                Url4Url(value="http://example.com"),
                Url4Text(value="raw text here"),
            )
        )
        result = await resolve(node)
        assert result == "from url\nraw text here"


@pytest.mark.anyio
async def test_resolve_nested_list() -> None:
    with patch(PATCH_TARGET, new_callable=AsyncMock, return_value="fetched"):
        node = Url4List(
            items=(
                Url4Text(value="hello"),
                Url4List(
                    items=(
                        Url4Url(value="http://a.com"),
                        Url4Text(value="world"),
                    )
                ),
            )
        )
        result = await resolve(node)
        assert result == "hello\nfetched\nworld"


@pytest.mark.anyio
async def test_resolve_str_plain_string() -> None:
    result = await resolve_str("hello world")
    assert result == "hello world"


@pytest.mark.anyio
async def test_resolve_str_url() -> None:
    with patch(PATCH_TARGET, new_callable=AsyncMock, return_value="fetched content"):
        result = await resolve_str("http://example.com/data")
        assert result == "fetched content"


@pytest.mark.anyio
async def test_resolve_str_list_mixed() -> None:
    with patch(PATCH_TARGET, new_callable=AsyncMock, return_value="from url"):
        result = await resolve_str("(http://example.com, raw text here)")
        assert result == "from url\nraw text here"
