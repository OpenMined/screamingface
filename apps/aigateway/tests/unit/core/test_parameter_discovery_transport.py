"""Phase 5 (OME-479 §5.2): bounded, sanitized public-discovery HTTPS transport.

FEATURE: safe dynamic observation transport. These tests pin the safety
envelope BEFORE any provider parser exists: fixed allowlisted origin, no
redirects, JSON-only, bounded bytes/depth/nodes, and failures sanitized to a
stable reason code that never leaks a raw body or exception string.
"""

from __future__ import annotations

import json

import pytest

from aigateway.core.parameter_discovery import (
    DiscoveryError,
    DiscoveryHttpClient,
    DiscoveryLimits,
    RawResponse,
    fetch_discovery_json,
)

_ORIGIN = "https://openrouter.ai"
_URL = "https://openrouter.ai/api/v1/models"
_ALLOWED = frozenset({_ORIGIN})


class _FakeClient(DiscoveryHttpClient):
    """Records the single GET and returns a canned response (or raises)."""

    def __init__(self, response: RawResponse | None = None, *, error: Exception | None = None):
        self._response = response
        self._error = error
        self.calls: list[tuple[str, float, int]] = []

    async def get(self, url: str, *, timeout_s: float, max_bytes: int) -> RawResponse:
        self.calls.append((url, timeout_s, max_bytes))
        if self._error is not None:
            raise self._error
        assert self._response is not None
        return self._response


def _json_response(payload: object, *, content_type: str = "application/json") -> RawResponse:
    return RawResponse(status=200, content_type=content_type, body=json.dumps(payload))


async def _fetch(client: _FakeClient, *, url: str = _URL, limits: DiscoveryLimits | None = None):
    return await fetch_discovery_json(
        url, allowed_origins=_ALLOWED, client=client, limits=limits or DiscoveryLimits()
    )


@pytest.mark.asyncio
async def test_happy_path_returns_parsed_json() -> None:
    client = _FakeClient(_json_response({"data": [{"id": "a/b"}]}))
    result = await _fetch(client)
    assert result == {"data": [{"id": "a/b"}]}
    # bounds were handed to the client (adapter also enforces them)
    (url, timeout_s, max_bytes) = client.calls[0]
    assert url == _URL and timeout_s > 0 and max_bytes > 0


@pytest.mark.asyncio
async def test_non_allowlisted_origin_fails_without_calling_client() -> None:
    client = _FakeClient(_json_response({}))
    with pytest.raises(DiscoveryError) as exc:
        await _fetch(client, url="https://evil.example/api/v1/models")
    assert exc.value.reason == "origin_not_allowed"
    assert client.calls == []  # never dialed a non-allowlisted host


@pytest.mark.asyncio
async def test_non_https_scheme_fails_closed() -> None:
    client = _FakeClient(_json_response({}))
    with pytest.raises(DiscoveryError) as exc:
        await fetch_discovery_json(
            "http://openrouter.ai/api/v1/models",
            allowed_origins=frozenset({"http://openrouter.ai"}),
            client=client,
        )
    assert exc.value.reason == "insecure_scheme"
    assert client.calls == []


@pytest.mark.asyncio
async def test_redirect_status_is_not_followed() -> None:
    client = _FakeClient(RawResponse(status=302, content_type="application/json", body="{}"))
    with pytest.raises(DiscoveryError) as exc:
        await _fetch(client)
    assert exc.value.reason == "bad_status"


@pytest.mark.asyncio
async def test_wrong_content_type_fails() -> None:
    client = _FakeClient(_json_response({}, content_type="text/html"))
    with pytest.raises(DiscoveryError) as exc:
        await _fetch(client)
    assert exc.value.reason == "bad_content_type"


@pytest.mark.asyncio
async def test_charset_suffixed_json_content_type_is_accepted() -> None:
    client = _FakeClient(
        _json_response({"ok": True}, content_type="application/json; charset=utf-8")
    )
    assert await _fetch(client) == {"ok": True}


@pytest.mark.asyncio
async def test_oversized_body_fails() -> None:
    big = {"data": "x" * 5000}
    client = _FakeClient(_json_response(big))
    with pytest.raises(DiscoveryError) as exc:
        await _fetch(client, limits=DiscoveryLimits(max_bytes=1000))
    assert exc.value.reason == "oversized"


@pytest.mark.asyncio
async def test_malformed_json_is_sanitized() -> None:
    secret = "SENSITIVE-UPSTREAM-TOKEN-abc123"
    client = _FakeClient(RawResponse(status=200, content_type="application/json", body=secret))
    with pytest.raises(DiscoveryError) as exc:
        await _fetch(client)
    assert exc.value.reason == "malformed_json"
    # sanitized: the raw body never appears in the error surface
    assert secret not in str(exc.value)


@pytest.mark.asyncio
async def test_json_parser_recursion_failure_is_sanitized() -> None:
    # Parsing happens before the explicit depth walk, so hostile nesting can hit
    # CPython's recursion guard while still fitting comfortably inside the byte cap.
    body = "[" * 10_000 + "]" * 10_000
    client = _FakeClient(RawResponse(status=200, content_type="application/json", body=body))

    with pytest.raises(DiscoveryError) as exc:
        await _fetch(client)

    assert exc.value.reason == "malformed_json"


@pytest.mark.asyncio
async def test_too_deep_json_fails() -> None:
    node: dict = {}
    cur = node
    for _ in range(50):
        cur["child"] = {}
        cur = cur["child"]
    client = _FakeClient(_json_response(node))
    with pytest.raises(DiscoveryError) as exc:
        await _fetch(client, limits=DiscoveryLimits(max_json_depth=8))
    assert exc.value.reason == "too_deep"


@pytest.mark.asyncio
async def test_too_many_nodes_fails() -> None:
    client = _FakeClient(_json_response({"data": list(range(500))}))
    with pytest.raises(DiscoveryError) as exc:
        await _fetch(client, limits=DiscoveryLimits(max_json_nodes=50))
    assert exc.value.reason == "too_many_nodes"


@pytest.mark.asyncio
async def test_client_transport_error_surfaces_sanitized() -> None:
    # The adapter translates network faults into DiscoveryError; a leaked raw
    # exception would violate §5.2. Simulate a pre-sanitized transport failure.
    client = _FakeClient(error=DiscoveryError("unreachable"))
    with pytest.raises(DiscoveryError) as exc:
        await _fetch(client)
    assert exc.value.reason == "unreachable"
