"""Phase 6b (OME-479 §5.2): the concrete httpx discovery transport adapter.

FEATURE: safe dynamic observation transport — production adapter. Uses
httpx.MockTransport so the boundary is proven deterministically, with no live
network: no redirect is followed, status/content-type/body pass through, and any
transport fault is translated to a sanitized DiscoveryError (never leaked raw).
"""

from __future__ import annotations

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
