"""Phase 6b (OME-479 §5.2): the concrete httpx discovery transport adapter.

FEATURE: safe dynamic observation transport — production adapter. Uses
httpx.MockTransport so the boundary is proven deterministically, with no live
network: no redirect is followed, status/content-type/body pass through, and any
transport fault is translated to a sanitized DiscoveryError (never leaked raw).
"""

from __future__ import annotations

import asyncio
import gzip
import time
from collections.abc import AsyncIterator

import httpx
import pytest

from aigateway.core.parameter_discovery import (
    DiscoveryError,
    HttpxDiscoveryClient,
    RawResponse,
)

_URL = "https://openrouter.ai/api/v1/models"


async def _get(client: HttpxDiscoveryClient) -> RawResponse:
    return await client.get(_URL, timeout_s=3.0, max_bytes=1_000_000)


@pytest.mark.asyncio
async def test_happy_path_passes_status_content_type_body_through() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == _URL
        return httpx.Response(200, json={"data": []}, headers={"content-type": "application/json"})

    client = HttpxDiscoveryClient(transport=httpx.MockTransport(handler))
    resp = await _get(client)
    assert resp.status == 200
    assert resp.content_type.split(";")[0] == "application/json"
    assert '"data"' in resp.body


@pytest.mark.asyncio
async def test_redirect_is_not_followed() -> None:
    # A 3xx is returned as-is (follow_redirects=False) so the caller fails it as a
    # bad status — the adapter never chases a Location into an unvetted origin.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://evil.example/x"})

    client = HttpxDiscoveryClient(transport=httpx.MockTransport(handler))
    resp = await _get(client)
    assert resp.status == 302


@pytest.mark.asyncio
async def test_transport_error_is_sanitized_to_discovery_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns boom: secret-host-internal")

    client = HttpxDiscoveryClient(transport=httpx.MockTransport(handler))
    with pytest.raises(DiscoveryError) as exc:
        await _get(client)
    assert exc.value.reason == "unreachable"
    # sanitized: the raw transport message never reaches the error surface.
    assert "secret-host-internal" not in str(exc.value)


# --- OME-604: max_bytes and timeout_s are enforced BY THIS ADAPTER ----------------------


def _client(handler) -> HttpxDiscoveryClient:
    return HttpxDiscoveryClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_oversized_body_is_rejected_not_truncated() -> None:
    # INVARIANT: the adapter's buffer never exceeds max_bytes. Returning a truncated
    # body instead would leave the limit to a downstream re-measure of bytes we
    # already chose to keep.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"x" * 5_000, headers={"content-type": "application/json"}
        )

    with pytest.raises(DiscoveryError) as exc:
        await _client(handler).get(_URL, timeout_s=3.0, max_bytes=1_000)
    assert exc.value.reason == "oversized"


@pytest.mark.asyncio
async def test_body_exactly_at_the_cap_is_accepted() -> None:
    # The boundary is ">", not ">=" — pinned so a later "tidy-up" cannot silently
    # start rejecting a body that fits.
    body = b"y" * 1_000

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    resp = await _client(handler).get(_URL, timeout_s=3.0, max_bytes=1_000)
    assert len(resp.body.encode("utf-8")) == 1_000


@pytest.mark.asyncio
async def test_identity_encoding_is_requested() -> None:
    # WHY: max_bytes must mean ONE thing. Asking for identity makes wire bytes,
    # buffered bytes and parsed bytes the same number.
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["accept-encoding"] = request.headers.get("accept-encoding", "")
        return httpx.Response(200, json={"data": []}, headers={"content-type": "application/json"})

    await _get(_client(handler))
    assert seen["accept-encoding"] == "identity"


@pytest.mark.asyncio
async def test_compressed_response_is_refused_rather_than_decoded() -> None:
    # A source that compresses despite the identity request would put the byte cap
    # back on post-expansion bytes, so it is failed instead of decoded.
    payload = gzip.compress(b'{"data": []}' * 100)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=payload,
            headers={"content-type": "application/json", "content-encoding": "gzip"},
        )

    with pytest.raises(DiscoveryError) as exc:
        await _get(_client(handler))
    assert exc.value.reason == "unsupported_encoding"


@pytest.mark.asyncio
async def test_slow_drip_stream_hits_the_total_deadline() -> None:
    # INVARIANT: timeout_s is a TOTAL wall-clock budget. httpx's own Timeout is a set
    # of per-interval budgets, each of which this stream resets forever by staying
    # busy — so without an outer deadline the fetch never ends.
    async def drip() -> AsyncIterator[bytes]:
        while True:
            yield b" "
            await asyncio.sleep(0.01)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=drip(), headers={"content-type": "application/json"})

    started = time.monotonic()
    with pytest.raises(DiscoveryError) as exc:
        await _client(handler).get(_URL, timeout_s=0.25, max_bytes=1_000_000)
    elapsed = time.monotonic() - started

    assert exc.value.reason == "timeout"
    assert elapsed < 3.0  # bounded; without the deadline this stream runs forever
