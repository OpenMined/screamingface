"""The httpx-backed :class:`~url4.io_layer.IOLayer` adapter (the ``run`` default).

The only module in the package that imports httpx. It owns a single, lazily
created :class:`httpx.AsyncClient` so the many fetches of one expression (a
fan-out's N sources plus its reducer) share one connection pool via keep-alive,
instead of paying a fresh TCP+TLS handshake per fetch.
"""

from __future__ import annotations

import httpx

from url4.errors import ResolutionError
from url4.io_layer import FetchRequest, FetchResult


class HttpIOLayer:
    """A batteries-included :class:`~url4.io_layer.IOLayer` over httpx.

    :meth:`fetch` issues ``GET target`` (or ``GET base_url + target`` for a
    relative ``/path``) and returns the response body. A relative expression
    arrives already encoded as ``/claude?q=(ctx)!intent``, so a model backend is
    just a ``GET base_url/claude?q=…`` against the localhost node. A
    ``url4://`` target is translated to ``https://`` for transport (spec §3.5 —
    the URL4 scheme rides HTTPS on the wire). :meth:`fetch_ex` additionally
    reports the response's media type so collection parsing can be
    Content-Type-driven (spec §5.3.7).

    A single :class:`httpx.AsyncClient` is created on the first fetch and reused
    for the adapter's lifetime, so pooling / keep-alive apply across a fan-out.
    Call :meth:`aclose` (or use the adapter as an async context manager) to
    release it; :func:`~url4.run` closes the default adapter it creates. Pass
    your own ``client`` to control pooling, auth, or to inject a test transport —
    an injected client is used as-is and never closed here. Any HTTP failure
    surfaces as :class:`~url4.errors.ResolutionError`.
    """

    def __init__(
        self,
        base_url: str = "",
        *,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = client
        self._owned: httpx.AsyncClient | None = None  # lazily created when no client is injected

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        if self._owned is None:
            # follow_redirects: a source that 301/302s (http->https, trailing
            # slash, auth bounce) must resolve to the real body, not the empty
            # redirect response — raise_for_status never fires on a 3xx.
            self._owned = httpx.AsyncClient(timeout=self._timeout, follow_redirects=True)
        return self._owned

    async def fetch(self, target: str, *, relative: bool) -> str:
        response = await self._get(self._transport_url(target, relative))
        return response.text

    async def fetch_ex(self, request: FetchRequest) -> FetchResult:
        response = await self._get(self._transport_url(request.target, request.relative))
        content_type = response.headers.get("content-type", "")
        media_type = content_type.split(";", 1)[0].strip().lower() or None
        return FetchResult(response.text, media_type=media_type)

    def _transport_url(self, target: str, relative: bool) -> str:
        url = f"{self._base_url}{target}" if relative else target
        if url.startswith("url4://"):
            return "https://" + url.removeprefix("url4://")
        return url

    async def _get(self, url: str) -> httpx.Response:
        try:
            response = await self._get_client().get(url)
            response.raise_for_status()
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            # httpx.InvalidURL is not an HTTPError subclass; catch it too so a
            # malformed target (e.g. control chars in a reducer query) still
            # surfaces as ResolutionError rather than a raw httpx exception.
            raise ResolutionError(f"GET {url!r} failed: {exc}") from exc
        return response

    async def aclose(self) -> None:
        """Close the internally created client, if any (an injected client is left alone)."""
        if self._owned is not None:
            await self._owned.aclose()
            self._owned = None

    async def __aenter__(self) -> HttpIOLayer:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()


__all__ = ["HttpIOLayer"]
