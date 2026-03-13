"""url4 — recursive context resolution protocol.

A url4 context value is either:
- A plain string (returned as-is)
- A parenthesized list: (item1, item2, item3)

Items in a list can be URLs (fetched via GET), raw strings, or nested
lists (recursively resolved). All results are concatenated with newlines.

This module has no ScreamingFace-specific dependencies.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import quote, urlparse, urlunparse

import httpx

logger = logging.getLogger(__name__)

_URL_PATTERN = re.compile(r"^https?://")


def parse_context(value: str) -> list[str] | str:
    """Parse a url4 context value into a list of items or a plain string.

    If the value is wrapped in parentheses, parse it as a comma-separated
    list of items (handling nested parentheses). Otherwise return as-is.
    """
    stripped = value.strip()
    if not stripped.startswith("(") or not stripped.endswith(")"):
        return stripped

    # Strip outer parens and parse items respecting nested parens
    inner = stripped[1:-1]
    items: list[str] = []
    depth = 0
    current: list[str] = []

    for char in inner:
        if char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            item = "".join(current).strip()
            if item:
                items.append(item)
            current = []
        else:
            current.append(char)

    # Last item
    item = "".join(current).strip()
    if item:
        items.append(item)

    return items


def is_url(item: str) -> bool:
    """Check if an item looks like an HTTP(S) URL."""
    return bool(_URL_PATTERN.match(item.strip()))


async def resolve(context: str) -> str:
    """Resolve a url4 context value to a string.

    - Plain string → returned as-is
    - Parenthesized list → each item resolved and concatenated

    Items that are URLs are fetched via HTTP GET.
    Items that are plain strings are included as-is.
    Nested lists are recursively resolved.
    """
    parsed = parse_context(context)

    if isinstance(parsed, str):
        # Not a list — check if it's a URL to fetch, otherwise return as-is
        if is_url(parsed):
            return await _fetch_url(parsed)
        return parsed

    # It's a list — resolve each item and concatenate
    results: list[str] = []
    for item in parsed:
        resolved = await resolve(item)
        results.append(resolved)

    return "\n".join(results)


def _sanitize_url(url: str) -> str:
    """Re-encode a URL so it's safe for httpx (handles decoded chars like newlines)."""
    parsed = urlparse(url)
    # Re-encode the query string — quote everything except safe URL chars
    safe_query = quote(parsed.query, safe="=&+%")
    return urlunparse(parsed._replace(query=safe_query))


async def _fetch_url(url: str) -> str:
    """Fetch a URL via HTTP GET and return the response body as text."""
    safe_url = _sanitize_url(url)
    logger.info("url4: fetching %s", safe_url[:200])
    timeout = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
    # verify=False for self-signed certs on localhost
    async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
        resp = await client.get(safe_url)
        resp.raise_for_status()
        return resp.text
