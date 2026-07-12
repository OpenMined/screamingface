"""The in-memory, deterministic :class:`~url4.io_layer.IOLayer` adapter.

No network, fully reproducible — the default for tests. Serves static reads
from ``fetch_map``, localhost ``?q=`` expression endpoints from ``routes``,
``@`` / ``@identity`` references from ``holdings``
(:class:`~url4.io_layer.SupportsHoldings`), and declared media types from
``media_types`` (:class:`~url4.io_layer.SupportsFetchEx`). Depends only on the
sub-request codec and the error hierarchy, never on httpx.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from inspect import isawaitable

from url4.errors import ResolutionError
from url4.io_layer import FetchRequest, FetchResult
from url4.subrequest import decode_subrequest

RouteHandler = Callable[[str, str], str | Awaitable[str]]


class StaticIOLayer:
    """An in-memory :class:`~url4.io_layer.IOLayer` — no network, fully deterministic.

    ``fetch_map`` maps an exact URL/path to its content (a static data read).
    ``routes`` maps a localhost path (e.g. ``/claude``) to a handler
    ``(context, intent) -> str`` (sync or async) — invoked when a relative
    expression is fetched as ``/claude?q=(context)!intent``, simulating a
    localhost url4 node. ``holdings`` maps holdings keys to content — ``""``
    for the node's own default holdings (``@``), ``"coll"`` for ``@`` with a
    collection qualifier, ``"name"`` for ``@name``, ``"name/coll"`` for
    ``@name/coll``; omitting it makes this adapter behave like a non-URL4
    source (spec §5.6.6). ``media_types`` maps a target to the media type
    ``fetch_ex`` reports for it. Missing keys raise
    :class:`~url4.errors.ResolutionError`.
    """

    def __init__(
        self,
        fetch_map: dict[str, str] | None = None,
        routes: dict[str, RouteHandler] | None = None,
        *,
        holdings: Mapping[str, str] | None = None,
        media_types: Mapping[str, str] | None = None,
    ) -> None:
        self._fetch = dict(fetch_map or {})
        self._routes = dict(routes or {})
        self._holdings = dict(holdings) if holdings is not None else None
        self._media_types = dict(media_types or {})

    async def fetch(self, target: str, *, relative: bool) -> str:
        path, sep, query = target.partition("?q=")
        if sep and path in self._routes:
            context, intent = decode_subrequest(query)
            result = self._routes[path](context, intent)
            return await result if isawaitable(result) else result
        try:
            return self._fetch[target]
        except KeyError:
            raise ResolutionError(f"no fetch mapping for {target!r}") from None

    async def fetch_ex(self, request: FetchRequest) -> FetchResult:
        body = await self.fetch(request.target, relative=request.relative)
        return FetchResult(body, media_type=self._media_types.get(request.target))

    async def fetch_holdings(self, identity: str | None, collection: str | None) -> str:
        holdings = self._holdings
        if holdings is None:
            # No holdings configured: this adapter is a non-URL4 source in the
            # spec's sense, and @/@identity on one is a permanent error (§5.6.6).
            raise ResolutionError(
                "this adapter serves no holdings — @/@identity requires a URL4-aware node",
                code="self_ref_on_non_url4" if identity is None else "identity_ref_on_non_url4",
                permanent=True,
            )
        key = _holdings_key(identity, collection)
        if key in holdings:
            return holdings[key]
        if identity is not None:
            raise ResolutionError(
                f"unknown identity {identity!r}", code="unknown_identity", permanent=True
            )
        raise ResolutionError(f"no self holdings for collection {collection!r}")


def _holdings_key(identity: str | None, collection: str | None) -> str:
    base = identity or ""
    if collection is None:
        return base
    return f"{base}/{collection}" if base else collection


__all__ = ["RouteHandler", "StaticIOLayer"]
