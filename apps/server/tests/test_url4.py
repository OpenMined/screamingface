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


# ---------------------------------------------------------------------------
# Parse tests for the 10 url4 examples
# ---------------------------------------------------------------------------


def test_parse_example_1() -> None:
    """(url, url) — two plain URLs."""
    node = parse("(https://docs.company.com/api, https://docs.company.com/faq)")
    assert isinstance(node, Url4List)
    assert len(node.items) == 2
    assert isinstance(node.items[0], Url4Url)
    assert node.items[0].value == "https://docs.company.com/api"
    assert isinstance(node.items[1], Url4Url)
    assert node.items[1].value == "https://docs.company.com/faq"


def test_parse_example_2() -> None:
    """(text, url) — text prompt + URL."""
    node = parse(
        "(You are an expert Python developer.,"
        " https://raw.githubusercontent.com/org/repo/main/README.md)"
    )
    assert isinstance(node, Url4List)
    assert len(node.items) == 2
    assert isinstance(node.items[0], Url4Text)
    assert node.items[0].value == "You are an expert Python developer."
    assert isinstance(node.items[1], Url4Url)
    assert node.items[1].value == "https://raw.githubusercontent.com/org/repo/main/README.md"


def test_parse_example_3() -> None:
    """(text, url, url) — text + two URLs."""
    node = parse(
        "(Summarize the following:,"
        " https://docs.company.com/changelog,"
        " https://docs.company.com/migration-guide)"
    )
    assert isinstance(node, Url4List)
    assert len(node.items) == 3
    assert isinstance(node.items[0], Url4Text)
    assert node.items[0].value == "Summarize the following:"
    assert isinstance(node.items[1], Url4Url)
    assert node.items[1].value == "https://docs.company.com/changelog"
    assert isinstance(node.items[2], Url4Url)
    assert node.items[2].value == "https://docs.company.com/migration-guide"


def test_parse_example_4() -> None:
    """(url4_url, url4_url) — nested url4 URLs with balanced parens."""
    node = parse(
        "(https://localhost:8000/url4?context=(https://docs.a.com, https://docs.b.com),"
        " https://localhost:8000/url4?context=(https://docs.c.com, https://docs.d.com))"
    )
    assert isinstance(node, Url4List)
    assert len(node.items) == 2
    assert isinstance(node.items[0], Url4Url)
    assert (
        node.items[0].value
        == "https://localhost:8000/url4?context=(https://docs.a.com, https://docs.b.com)"
    )
    assert isinstance(node.items[1], Url4Url)
    assert (
        node.items[1].value
        == "https://localhost:8000/url4?context=(https://docs.c.com, https://docs.d.com)"
    )


def test_parse_example_5() -> None:
    """(text, url, url) — code review prompt."""
    node = parse(
        "(Review this code for security issues:,"
        " https://raw.githubusercontent.com/org/repo/main/src/auth.py,"
        " https://raw.githubusercontent.com/org/repo/main/src/session.py)"
    )
    assert isinstance(node, Url4List)
    assert len(node.items) == 3
    assert isinstance(node.items[0], Url4Text)
    assert node.items[0].value == "Review this code for security issues:"
    assert isinstance(node.items[1], Url4Url)
    assert node.items[1].value == "https://raw.githubusercontent.com/org/repo/main/src/auth.py"
    assert isinstance(node.items[2], Url4Url)
    assert node.items[2].value == "https://raw.githubusercontent.com/org/repo/main/src/session.py"


def test_parse_example_6() -> None:
    """(text, url, text) — text + URL + text."""
    node = parse(
        "(Follow these coding standards:, https://company.com/style-guide, Always use type hints.)"
    )
    assert isinstance(node, Url4List)
    assert len(node.items) == 3
    assert isinstance(node.items[0], Url4Text)
    assert node.items[0].value == "Follow these coding standards:"
    assert isinstance(node.items[1], Url4Url)
    assert node.items[1].value == "https://company.com/style-guide"
    assert isinstance(node.items[2], Url4Text)
    assert node.items[2].value == "Always use type hints."


def test_parse_example_7() -> None:
    """(url?query, url?query) — URLs with query params."""
    node = parse(
        "(https://api.github.com/repos/org/repo/releases/latest,"
        " https://api.github.com/repos/org/repo/issues?state=open)"
    )
    assert isinstance(node, Url4List)
    assert len(node.items) == 2
    assert isinstance(node.items[0], Url4Url)
    assert node.items[0].value == "https://api.github.com/repos/org/repo/releases/latest"
    assert isinstance(node.items[1], Url4Url)
    assert node.items[1].value == "https://api.github.com/repos/org/repo/issues?state=open"


def test_parse_example_8() -> None:
    """(text, url, url) — debugging context."""
    node = parse(
        "(You are debugging a production outage.,"
        " https://grafana.internal/api/dashboards/export,"
        " https://logs.internal/api/recent-errors)"
    )
    assert isinstance(node, Url4List)
    assert len(node.items) == 3
    assert isinstance(node.items[0], Url4Text)
    assert node.items[0].value == "You are debugging a production outage."
    assert isinstance(node.items[1], Url4Url)
    assert node.items[1].value == "https://grafana.internal/api/dashboards/export"
    assert isinstance(node.items[2], Url4Url)
    assert node.items[2].value == "https://logs.internal/api/recent-errors"


def test_parse_example_9() -> None:
    """(text, url, url, text) — project context with prompt placeholder."""
    node = parse(
        "(Project context:,"
        " https://raw.githubusercontent.com/org/repo/main/README.md,"
        " https://raw.githubusercontent.com/org/repo/main/ARCHITECTURE.md,"
        " Current task: {prompt})"
    )
    assert isinstance(node, Url4List)
    assert len(node.items) == 4
    assert isinstance(node.items[0], Url4Text)
    assert node.items[0].value == "Project context:"
    assert isinstance(node.items[1], Url4Url)
    assert node.items[1].value == "https://raw.githubusercontent.com/org/repo/main/README.md"
    assert isinstance(node.items[2], Url4Url)
    assert node.items[2].value == "https://raw.githubusercontent.com/org/repo/main/ARCHITECTURE.md"
    assert isinstance(node.items[3], Url4Text)
    assert node.items[3].value == "Current task: {prompt}"


def test_parse_example_10() -> None:
    """(url4_url, url4_url) — nested url4 URLs with text inside balanced parens."""
    node = parse(
        "(https://localhost:8000/url4?context=(Background:, https://wiki.internal/project-overview),"
        " https://localhost:8000/url4?context=(Recent changes:, https://api.github.com/repos/org/repo/commits))"
    )
    assert isinstance(node, Url4List)
    assert len(node.items) == 2
    assert isinstance(node.items[0], Url4Url)
    assert (
        node.items[0].value
        == "https://localhost:8000/url4?context=(Background:, https://wiki.internal/project-overview)"
    )
    assert isinstance(node.items[1], Url4Url)
    assert (
        node.items[1].value
        == "https://localhost:8000/url4?context=(Recent changes:, https://api.github.com/repos/org/repo/commits)"
    )


def test_parse_strips_whitespace() -> None:
    node = parse("  hello world  ")
    assert isinstance(node, Url4Text)
    assert node.value == "hello world"


def test_parse_list_strips_item_whitespace() -> None:
    node = parse("(  http://a.com ,  hello  )")
    assert isinstance(node, Url4List)
    url_item = node.items[0]
    text_item = node.items[1]
    assert isinstance(url_item, Url4Url)
    assert url_item.value == "http://a.com"
    assert isinstance(text_item, Url4Text)
    assert text_item.value == "hello"


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


@pytest.mark.anyio
async def test_resolve_str_example_4() -> None:
    """Nested url4 URLs resolve as single URL fetches."""
    responses = {
        "https://localhost:8000/url4?context="
        "(https://docs.a.com, https://docs.b.com)": "content-ab",
        "https://localhost:8000/url4?context="
        "(https://docs.c.com, https://docs.d.com)": "content-cd",
    }

    async def mock_fetch(url: str) -> str:
        return responses[url]

    with patch(PATCH_TARGET, side_effect=mock_fetch):
        result = await resolve_str(
            "(https://localhost:8000/url4?context=(https://docs.a.com, https://docs.b.com),"
            " https://localhost:8000/url4?context=(https://docs.c.com, https://docs.d.com))"
        )
        assert result == "content-ab\ncontent-cd"


@pytest.mark.anyio
async def test_resolve_str_example_10() -> None:
    """Nested url4 URLs with text inside balanced parens resolve correctly."""
    responses = {
        "https://localhost:8000/url4?context="
        "(Background:, https://wiki.internal/project-overview)": "bg-content",
        "https://localhost:8000/url4?context="
        "(Recent changes:, https://api.github.com/repos/org/repo/commits)": "changes-content",
    }

    async def mock_fetch(url: str) -> str:
        return responses[url]

    with patch(PATCH_TARGET, side_effect=mock_fetch):
        result = await resolve_str(
            "(https://localhost:8000/url4?context=(Background:, https://wiki.internal/project-overview),"
            " https://localhost:8000/url4?context=(Recent changes:, https://api.github.com/repos/org/repo/commits))"
        )
        assert result == "bg-content\nchanges-content"
