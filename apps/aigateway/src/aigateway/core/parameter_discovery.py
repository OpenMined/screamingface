"""OME-479 §5.2 — bounded, sanitized public-discovery HTTPS transport.

FEATURE: safe dynamic observation transport. Providers (OpenRouter/HF/Gemini)
fetch FIXED public catalogs to enrich the detailed contract with raw support
evidence. This module owns the safety envelope; provider parsers own the shape.

INVARIANT (§5.2): the caller (a provider integration) supplies a FIXED https URL
and its own allowlisted origins — never a caller-supplied or response-derived
URL, never credentials, never a followed redirect. Every failure is raised as a
``DiscoveryError`` carrying ONLY a stable reason code — never a raw body or a
raw exception string (that would leak upstream content into API output).

INVARIANT: nothing here runs on the chat dispatch critical path — discovery
feeds the detailed contract only. Dispatch is authorized by rules alone.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx


class DiscoveryError(Exception):
    """A sanitized discovery failure.

    # INVARIANT: only ``reason`` (a fixed code) is ever exposed; no raw upstream
    # body or raw exception text is attached, so it is safe to surface.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class DiscoveryLimits:
    """Response bounds enforced on every fetch (§5.2)."""

    timeout_s: float = 3.0
    max_bytes: int = 1_000_000
    max_json_depth: int = 16
    max_json_nodes: int = 50_000


@dataclass(frozen=True)
class RawResponse:
    """The minimal, transport-agnostic response the discovery layer inspects."""

    status: int
    content_type: str
    body: str


class DiscoveryHttpClient(Protocol):
    """Injected transport seam — a real httpx adapter in prod, a fake in tests.

    The adapter MUST NOT follow redirects and MUST translate any network/timeout
    fault into a ``DiscoveryError`` (so this module never leaks a raw exception).
    """

    async def get(self, url: str, *, timeout_s: float, max_bytes: int) -> RawResponse: ...


def _origin_of(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    return parts.scheme, f"{parts.scheme}://{parts.netloc}"


def _assert_bounded(data: Any, *, max_depth: int, max_nodes: int) -> None:
    # WHY: a fixed public catalog is normally shallow and small; a pathologically
    # deep or huge document is treated as hostile input, not parsed into memory
    # pressure. Depth is checked BEFORE recursing so the stack is bounded too.
    nodes = 0

    def walk(node: Any, depth: int) -> None:
        nonlocal nodes
        if depth > max_depth:
            raise DiscoveryError("too_deep")
        nodes += 1
        if nodes > max_nodes:
            raise DiscoveryError("too_many_nodes")
        if isinstance(node, dict):
            for value in node.values():
                walk(value, depth + 1)
        elif isinstance(node, list):
            for value in node:
                walk(value, depth + 1)

    walk(data, 0)


async def fetch_discovery_json(
    url: str,
    *,
    allowed_origins: frozenset[str],
    client: DiscoveryHttpClient,
    limits: DiscoveryLimits = DiscoveryLimits(),
) -> Any:
    """Fetch + validate a fixed public JSON catalog, or raise ``DiscoveryError``.

    Order matters: origin/scheme are validated BEFORE the client is dialed, so a
    non-allowlisted or insecure URL never opens a connection.
    """
    scheme, origin = _origin_of(url)
    if scheme != "https":
        raise DiscoveryError("insecure_scheme")
    if origin not in allowed_origins:
        raise DiscoveryError("origin_not_allowed")

    response = await client.get(url, timeout_s=limits.timeout_s, max_bytes=limits.max_bytes)

    # A redirect (3xx) is never followed: any non-200 is a failure, not a hop.
    if response.status != 200:
        raise DiscoveryError("bad_status")
    if response.content_type.split(";")[0].strip().lower() != "application/json":
        raise DiscoveryError("bad_content_type")
    if len(response.body.encode("utf-8")) > limits.max_bytes:
        raise DiscoveryError("oversized")

    try:
        parsed = json.loads(response.body)
    except json.JSONDecodeError:
        # sanitized: the raw body is discarded, only a fixed reason survives.
        raise DiscoveryError("malformed_json") from None

    _assert_bounded(parsed, max_depth=limits.max_json_depth, max_nodes=limits.max_json_nodes)
    return parsed


class HttpxDiscoveryClient:
    """The production ``DiscoveryHttpClient`` over httpx (§5.2).

    # INVARIANT: ``follow_redirects`` is OFF, so a 3xx is returned as-is for
    # ``fetch_discovery_json`` to fail as a bad status — a Location is never
    # chased into an unvetted origin. The read is bounded by ``max_bytes`` so a
    # hostile body cannot exhaust memory before the caller's oversized check.
    # INVARIANT: every httpx fault is translated to ``DiscoveryError`` with a
    # fixed reason and no ``__cause__`` chained out — a raw transport message can
    # carry a host/path, and must never reach API output.
    # AIDEV-NOTE: ``transport`` is injectable ONLY so tests drive it with
    # ``httpx.MockTransport``; production constructs it with no arguments.
    """

    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def get(self, url: str, *, timeout_s: float, max_bytes: int) -> RawResponse:
        try:
            async with httpx.AsyncClient(
                follow_redirects=False,
                timeout=httpx.Timeout(timeout_s),
                transport=self._transport,
            ) as client:
                async with client.stream("GET", url) as response:
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in response.aiter_bytes():
                        chunks.append(chunk)
                        total += len(chunk)
                        if total > max_bytes:
                            break  # stop reading a hostile/oversized body early
                    return RawResponse(
                        status=response.status_code,
                        content_type=response.headers.get("content-type", ""),
                        body=b"".join(chunks).decode("utf-8", errors="replace"),
                    )
        except httpx.HTTPError:
            # sanitized: a stable reason only; the raw exception is dropped.
            raise DiscoveryError("unreachable") from None
