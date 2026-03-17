"""url4 — recursive context resolution protocol (TatSu PEG parser).

A url4 context value is either:
- A plain string (returned as-is)
- A URL (fetched via HTTP GET)
- A parenthesized list: (item1, item2, item3)

Items in a list can be URLs, raw strings, or nested lists (recursively
resolved). All results are concatenated with newlines.

This module has no ScreamingFace-specific dependencies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import quote, urlparse, urlunparse

import httpx
from tatsu import compile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TatSu PEG grammar
# ---------------------------------------------------------------------------

GRAMMAR = r"""
    @@grammar::Url4
    @@whitespace :: //

    start = context $ ;

    context
        = group
        | atom
        ;

    group = '(' elems:','%{ context } ')' ;

    atom
        = url
        | text
        ;

    url = value:/https?:\/\/(?:[^\s,()]|\([^()]*\))+/ ;

    text = value:/[^,()]+/ ;
"""

# ---------------------------------------------------------------------------
# Typed AST dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Url4Url:
    value: str


@dataclass(frozen=True)
class Url4Text:
    value: str


@dataclass(frozen=True)
class Url4List:
    items: tuple[Url4Node, ...]


Url4Node = Url4Url | Url4Text | Url4List

# ---------------------------------------------------------------------------
# TatSu semantics — transforms raw AST into typed dataclasses
# ---------------------------------------------------------------------------


class Url4Semantics:
    def url(self, ast):
        return Url4Url(value=ast.value.strip())

    def text(self, ast):
        return Url4Text(value=ast.value.strip())

    def group(self, ast):
        elems = ast.elems if isinstance(ast.elems, list) else [ast.elems] if ast.elems else []
        # Filter out comma separator tokens from join operator
        nodes = [e for e in elems if isinstance(e, Url4Url | Url4Text | Url4List)]
        return Url4List(items=tuple(nodes))

    def context(self, ast):
        return ast

    def start(self, ast):
        return ast


# ---------------------------------------------------------------------------
# Parser (compiled once at module import)
# ---------------------------------------------------------------------------

_parser = compile(GRAMMAR)


def parse(context: str) -> Url4Node:
    """Parse a url4 context string into a typed AST."""
    return _parser.parse(context.strip(), semantics=Url4Semantics())


# ---------------------------------------------------------------------------
# Async interpreter
# ---------------------------------------------------------------------------


async def resolve(node: Url4Node) -> str:
    """Recursively resolve an AST node to a string."""
    if isinstance(node, Url4Text):
        return node.value
    if isinstance(node, Url4Url):
        return await _fetch_url(node.value)
    if isinstance(node, Url4List):
        results = [await resolve(item) for item in node.items]
        return "\n".join(results)
    raise TypeError(f"Unknown node type: {type(node)}")


async def resolve_str(context: str) -> str:
    """Parse a url4 context string and resolve it to a string."""
    return await resolve(parse(context))


# ---------------------------------------------------------------------------
# HTTP utilities (unchanged)
# ---------------------------------------------------------------------------


def _sanitize_url(url: str) -> str:
    """Re-encode a URL so it's safe for httpx (handles decoded chars like newlines)."""
    parsed = urlparse(url)
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
