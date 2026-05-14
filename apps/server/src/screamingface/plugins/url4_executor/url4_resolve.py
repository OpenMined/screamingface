"""Async resolution for the url4 AST.

Walks a :class:`Url4Node` tree, fetching URLs and dispatching backend
calls. The grammar / parser live in :mod:`.url4_grammar`; the AST
types in :mod:`.url4_ast`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

import httpx

from screamingface.plugins.url4_executor.ensemble_helpers import substitute_env_vars
from screamingface.plugins.url4_executor.scope import Env
from screamingface.plugins.url4_executor.url4_ast import (
    Url4BackendCall,
    Url4Binding,
    Url4ExpandedSource,
    Url4List,
    Url4Node,
    Url4RelUrl,
    Url4Text,
    Url4Url,
)
from screamingface.plugins.url4_executor.url4_grammar import parse

logger = logging.getLogger(__name__)


async def resolve(node: Url4Node, app: Any = None, env: Env | None = None) -> str:
    """Recursively resolve an AST node to a string.

    ``env`` is the DEMO-004 scope chain. It is threaded through every
    recursive call so DEMO-005/006 have a place to put bindings; this
    function does not itself read from ``env`` yet.
    """
    if env is None:
        env = Env.root()
    if isinstance(node, Url4Text):
        return substitute_env_vars(node.value, env)
    if isinstance(node, Url4Url):
        return await _fetch_url(node.value)
    if isinstance(node, Url4RelUrl):
        return await _fetch_relative(app, node.value)
    if isinstance(node, Url4List):
        return await _resolve_list(node, app, env)
    if isinstance(node, Url4BackendCall):
        return await _dispatch_backend_call(node, app, env)
    if isinstance(node, Url4ExpandedSource):
        return await _resolve_expanded_source(node, app, env)
    if isinstance(node, Url4Binding):
        # DEMO-005: bare top-level binding — resolve and return the
        # value. Sibling-visibility registration only applies inside
        # a Url4List frame (see _resolve_list).
        return await resolve(node.value, app, env)
    raise TypeError(f"Unknown node type: {type(node)}")


async def _resolve_list(node: Url4List, app: Any, env: Env) -> str:
    """Resolve a ``Url4List`` with two passes (DEMO-005).

    Pass 1: walk ``Url4Binding`` items in declaration order, sequentially,
            so a later binding can read earlier ones (DEMO-006 ``$name``).
            Each resolved value is written into a child ``Env`` that
            stacks on top of ``env``.
    Pass 2: resolve remaining (non-binding) items in parallel under the
            fully-populated child ``Env``.

    Output preserves source order: each binding's resolved value sits in
    its original slot, joined with ``\\n`` (matching the legacy behaviour
    for non-binding lists).
    """
    items = list(node.items)
    results: list[str | None] = [None] * len(items)
    resolved_bindings: dict[str, Any] = {}

    # Pass 1 — bindings, declaration order, sequential.
    for idx, item in enumerate(items):
        if isinstance(item, Url4Binding):
            current = env.child(**resolved_bindings) if resolved_bindings else env
            value_text = await resolve(item.value, app, current)
            resolved_bindings[item.name] = value_text
            results[idx] = value_text

    # Pass 2 — non-bindings, parallel, under the populated child env.
    child_env = env.child(**resolved_bindings) if resolved_bindings else env
    non_binding_indices = [i for i, it in enumerate(items) if not isinstance(it, Url4Binding)]
    if non_binding_indices:
        gathered = await asyncio.gather(
            *(resolve(items[i], app, child_env) for i in non_binding_indices)
        )
        for i, value in zip(non_binding_indices, gathered, strict=True):
            results[i] = value

    return "\n".join(r for r in results if r is not None)


async def resolve_str(context: str, app: Any = None, env: Env | None = None) -> str:
    """Parse a url4 context string and resolve it to a string."""
    return await resolve(parse(context), app, env)


async def _dispatch_backend_call(node: Url4BackendCall, app: Any, env: Env | None = None) -> str:
    """Dispatch a :class:`Url4BackendCall` through an active plugin.

    Walks ``app.state.plugins.active_plugins`` looking for one whose
    :attr:`backend_call_paths` contains ``node.path``, flattens the
    intent into a plain string, then awaits the plugin's
    ``handle_backend_call(intent, app=app)`` method.
    """
    if app is None:
        raise RuntimeError(
            f"Cannot dispatch backend call {node.path}() without an app "
            "context. Backend-call resolution needs access to the active "
            "plugin registry via app.state.plugins."
        )

    intent_text = "" if node.intent is None else await resolve(node.intent, app, env)
    sources_text = node.packed_context or ""

    from screamingface.core.helpers import get_plugins_registry

    plugins_registry = get_plugins_registry(app)

    known_paths: list[str] = []
    for plugin in plugins_registry.active_plugins.values():
        paths = getattr(plugin, "backend_call_paths", [])
        known_paths.extend(paths)
        if node.path in paths:
            return await plugin.handle_backend_call(intent_text, sources=sources_text, app=app)

    raise RuntimeError(
        f"No active plugin handles the backend call {node.path}(). "
        f"Known backend_call_paths across active plugins: {known_paths!r}. "
        "Activate a plugin that declares this path in its "
        "backend_call_paths attribute."
    )


async def _resolve_expanded_source(
    node: Url4ExpandedSource, app: Any, env: Env | None = None
) -> str:
    """SF-92: Resolve a ``*source`` expansion.

    Fetches ``inner``, parses the body as a collection (JSON array,
    JSONL, or CSV), and joins the items with newlines (matching
    ``Url4List`` behaviour).
    """
    from screamingface.plugins.url4_executor.collection_parser import parse_collection

    body = await resolve(node.inner, app, env)
    items = parse_collection(body)
    if not items:
        return ""
    return "\n".join(items)


def _sanitize_url(url: str) -> str:
    """Re-encode a URL so it's safe for httpx (handles decoded chars like newlines)."""
    parsed = urlparse(url)
    safe_query = quote(parsed.query, safe="=&+%")
    return urlunparse(parsed._replace(query=safe_query))


async def _fetch_relative(app: Any, path: str) -> str:
    """Fetch a relative path via in-process ASGI transport (no network hop)."""
    from screamingface.plugins.url4_executor._tracing import set_span_attrs, traced

    if not app:
        raise ValueError(f"Cannot resolve relative URL {path!r} without app context")
    with traced("url4.fetch_relative", kind="client"):
        set_span_attrs({"http.method": "GET", "url4.path": path})
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            resp = await client.get(path)
            resp.raise_for_status()
            body = resp.text
            preview = body[:4000]
            if len(body) > 4000:
                preview += f"\n... ({len(body) - 4000} more chars)"
            set_span_attrs(
                {
                    "http.status_code": resp.status_code,
                    "url4.response_length": len(body),
                    "url4.response_body": preview,
                }
            )
            return body


async def _fetch_url(url: str) -> str:
    """Fetch a URL via HTTP GET and return the response body as text."""
    from screamingface.plugins.url4_executor._tracing import set_span_attrs, traced

    safe_url = _sanitize_url(url)
    logger.info("url4: fetching %s", safe_url[:200])
    with traced("url4.fetch", kind="client"):
        set_span_attrs({"http.method": "GET", "http.url": safe_url[:500]})
        timeout = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
            resp = await client.get(safe_url)
            resp.raise_for_status()
            body = resp.text
            preview = body[:4000]
            if len(body) > 4000:
                preview += f"\n... ({len(body) - 4000} more chars)"
            set_span_attrs(
                {
                    "http.status_code": resp.status_code,
                    "url4.response_length": len(body),
                    "url4.response_body": preview,
                }
            )
            return body


__all__ = ["resolve", "resolve_str"]
