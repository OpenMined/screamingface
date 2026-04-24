"""url4 — recursive context resolution protocol (TatSu PEG parser).

A url4 context value is either:
- A plain string (returned as-is)
- An absolute URL (fetched via HTTP GET)
- A relative URL /path (fetched via in-process ASGI)
- A parenthesized list: (item1, item2, item3)

Items in a list can be URLs, raw strings, or nested lists (recursively
resolved). All results are concatenated with newlines. List items are
resolved in parallel.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any
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
        = backend_call
        | expanded_source
        | url
        | relurl
        | text
        ;

    # SF-92: Source expansion — *source expands a collection into
    # individual sources. The * prefix tells the executor to fetch
    # the source, parse it as a collection (JSON/JSONL/CSV), and
    # treat each item as a separate source.
    expanded_source = '*' inner:expandable_atom ;

    # Atoms that can follow * — same as atom minus expanded_source
    # itself (no **source) and minus backend_call (no */claude()).
    expandable_atom
        = url
        | relurl
        | text
        ;

    # Backend-call form: [name:weight:]path(context)!<intent>
    #
    # Recognizes a plugin/backend invocation shorthand where:
    # - ``name:weight:`` is an optional prefix labeling the source
    #   (e.g. ``claude:40:`` for 40% weight). Used by the ensemble
    #   reducer to format weighted responses. (SF-88)
    # - ``/path`` is the backend route (``/claude``, ``/codex``, etc.)
    # - ``(context)`` carries optional inline context (SF-89)
    # - ``!<intent>`` is the LLM instruction for that backend
    #
    # The intent is any atom EXCEPT another backend_call.
    backend_call
        = [ label:source_label ] path:backend_path
          '(' [ packed_context:backend_context ] ')'
          [ '!' intent:atom_no_bc ]
        ;

    # Optional name:weight: prefix for named/weighted fan-out.
    # Format: name:weight: where name is [a-zA-Z_][a-zA-Z0-9_]* and
    # weight is an integer or decimal number.
    # The trailing colon before the path is included so /path is
    # unambiguous (path always starts with /).
    source_label = name:/[a-zA-Z_][a-zA-Z0-9_]*/ ':' weight:/[0-9]+(?:\.[0-9]+)?/ ':' ;

    # Content inside backend call parens. Matches any non-paren chars
    # (including commas, bangs, slashes, etc.) as raw text. Nested parens
    # are NOT supported in context packing Phase 1 — use /data/<key>
    # references for complex content.
    backend_context = /[^()]+/ ;

    # Path prefix for a backend_call: starts with /, continues until
    # the first '(' or ',' or whitespace or '!'. Also excludes URL
    # query/fragment chars ('?', '&', '#') so that URLs like
    # ``/claude?q=()`` don't get captured as backend_call paths — those
    # stay as regular URL fetches (Url4RelUrl).
    backend_path = /\/[^\s,()!?&#]+/ ;

    # atom alternatives used INSIDE a backend_call intent — excludes
    # backend_call itself to avoid ambiguous nesting. ``/claude()!a`` is a
    # single backend_call; ``/claude()!/other()!b`` puts ``/other()!b`` as
    # the intent (a relurl, since intent can't contain another backend_call).
    atom_no_bc
        = url
        | relurl
        | text
        ;

    url = value:/https?:\/\/(?:[^\s,()]|\([^()]*\))+/ ;

    relurl = value:/\/(?:[^\s,()]|\([^()]*\))*/ ;

    text = value:/[^,()]+/ ;
"""

# ---------------------------------------------------------------------------
# Typed AST dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Url4Url:
    value: str


@dataclass(frozen=True)
class Url4RelUrl:
    value: str


@dataclass(frozen=True)
class Url4Text:
    value: str


@dataclass(frozen=True)
class Url4List:
    items: tuple[Url4Node, ...]


@dataclass(frozen=True)
class Url4BackendCall:
    """A backend-invocation node: ``[name:weight:]path(context)!<intent>``.

    This is the shorthand for "invoke the plugin mounted at ``path`` as a
    backend LLM call, passing ``packed_context`` as the sources and
    ``intent`` as the instruction." Distinct from a :class:`Url4RelUrl`,
    which is a URL fetch via in-process ASGI GET.

    ``packed_context`` is the raw text inside the parens (SF-89 context
    packing). Empty string or None means "no inline context."

    ``name`` and ``weight`` are optional labels from the ``name:weight:``
    prefix (SF-88 named + weighted sources). When present, the ensemble
    reducer formats the response with the name and weight so the LLM
    can weight responses proportionally.
    """

    path: str
    packed_context: str | None = None
    intent: Url4Node | None = None
    name: str | None = None
    weight: float | None = None


@dataclass(frozen=True)
class Url4ExpandedSource:
    """SF-92: Source expansion — ``*source`` expands a collection.

    The executor fetches ``inner``, parses it as a collection
    (JSON array, JSONL, or CSV), and treats each item as a separate
    source. The expanded items replace this node in the AST during
    resolution.
    """

    inner: Url4Node


Url4Node = Url4Url | Url4RelUrl | Url4Text | Url4List | Url4BackendCall | Url4ExpandedSource

# ---------------------------------------------------------------------------
# TatSu semantics — transforms raw AST into typed dataclasses
# ---------------------------------------------------------------------------


class Url4Semantics:
    def url(self, ast):
        return Url4Url(value=ast.value.strip())

    def relurl(self, ast):
        return Url4RelUrl(value=ast.value.strip())

    def text(self, ast):
        return Url4Text(value=ast.value.strip())

    def backend_call(self, ast):
        # ast.label is the source_label semantics result (a dict with
        # name + weight), or None when no prefix was present.
        # ast.path is the backend_path rule's matched value.
        # ast.packed_context is the raw text inside the parens (SF-89).
        # ast.intent is the intent node or None.
        packed = getattr(ast, "packed_context", None)
        if isinstance(packed, str):
            packed = packed.strip() or None

        label = getattr(ast, "label", None)
        name = None
        weight = None
        if label and isinstance(label, dict):
            name = label.get("name")
            weight_str = label.get("weight")
            if weight_str is not None:
                try:
                    weight = float(weight_str)
                except (ValueError, TypeError):
                    weight = None

        return Url4BackendCall(
            path=ast.path.strip(),
            packed_context=packed,
            intent=ast.intent,
            name=name,
            weight=weight,
        )

    def source_label(self, ast):
        # TatSu gives us an AST object with .name and .weight attrs
        # from the regex captures.
        return {"name": ast.name, "weight": ast.weight}

    def expanded_source(self, ast):
        return Url4ExpandedSource(inner=ast.inner)

    def expandable_atom(self, ast):
        return ast

    def backend_context(self, ast):
        # TatSu returns the matched string directly for a regex rule.
        return ast

    def backend_path(self, ast):
        # TatSu returns the matched string directly for a regex rule
        return ast

    def group(self, ast):
        elems = ast.elems if isinstance(ast.elems, list) else [ast.elems] if ast.elems else []
        # Filter out comma separator tokens from join operator
        nodes = [
            e
            for e in elems
            if isinstance(
                e,
                Url4Url | Url4RelUrl | Url4Text | Url4List | Url4BackendCall | Url4ExpandedSource,
            )
        ]
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


async def resolve(node: Url4Node, app: Any = None) -> str:
    """Recursively resolve an AST node to a string."""
    if isinstance(node, Url4Text):
        return node.value
    if isinstance(node, Url4Url):
        return await _fetch_url(node.value)
    if isinstance(node, Url4RelUrl):
        return await _fetch_relative(app, node.value)
    if isinstance(node, Url4List):
        results = list(await asyncio.gather(*[resolve(item, app) for item in node.items]))
        return "\n".join(results)
    if isinstance(node, Url4BackendCall):
        return await _dispatch_backend_call(node, app)
    if isinstance(node, Url4ExpandedSource):
        return await _resolve_expanded_source(node, app)
    raise TypeError(f"Unknown node type: {type(node)}")


async def _dispatch_backend_call(node: Url4BackendCall, app: Any) -> str:
    """Dispatch a :class:`Url4BackendCall` through an active plugin.

    Walks ``app.state.plugins.active_plugins`` looking for one whose
    :attr:`backend_call_paths` contains ``node.path``, flattens the
    intent into a plain string, then awaits the plugin's
    ``handle_backend_call(intent, app=app)`` method.

    Error modes:

    - No *app* available (e.g. resolver called without a FastAPI context)
      → raises :class:`RuntimeError`.
    - No active plugin handles ``node.path`` → raises :class:`RuntimeError`
      with the list of known backend_call_paths so the user knows what's
      available.
    - Target plugin has no ``handle_backend_call`` override → raises
      whatever the plugin base's default raises (``NotImplementedError``).
    - Target plugin raises during dispatch → propagated unchanged so the
      ensemble layer above can catch provider-specific errors.
    """
    if app is None:
        raise RuntimeError(
            f"Cannot dispatch backend call {node.path}() without an app "
            "context. Backend-call resolution needs access to the active "
            "plugin registry via app.state.plugins."
        )

    # Flatten the intent node to a string. For a text intent this is a
    # no-op; for a relurl intent this fetches the blob body; for a URL
    # intent this fetches the remote URL.
    if node.intent is None:
        intent_text = ""
    else:
        intent_text = await resolve(node.intent, app)

    # SF-89 context packing: if the backend call had non-empty parens,
    # the packed_context becomes the "sources" argument. The backend's
    # interpreter.process(sources, intent) uses both.
    sources_text = node.packed_context or ""

    # Find the plugin that registered this path.
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


async def _resolve_expanded_source(node: Url4ExpandedSource, app: Any) -> str:
    """SF-92: Resolve a ``*source`` expansion.

    1. Resolve the inner source node to a string (fetch URL/blob body).
    2. Parse the body as a collection (JSON array, JSONL, or CSV).
    3. Each item becomes a ``Url4Text`` node.
    4. Resolve all items (they're just text), join with newlines.

    The expansion converts ``*source`` into the equivalent of writing
    out each item manually: ``(item1, item2, item3, ...)``.
    """
    from screamingface.plugins.url4_executor.collection_parser import parse_collection

    # Fetch the inner source
    body = await resolve(node.inner, app)

    # Parse as collection
    items = parse_collection(body)
    if not items:
        return ""

    # Each item becomes a resolved text value — join with newlines
    # (same as Url4List resolution behavior)
    return "\n".join(items)


async def resolve_str(context: str, app: Any = None) -> str:
    """Parse a url4 context string and resolve it to a string."""
    return await resolve(parse(context), app)


# ---------------------------------------------------------------------------
# HTTP utilities (unchanged)
# ---------------------------------------------------------------------------


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
        # verify=False for self-signed certs on localhost
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
