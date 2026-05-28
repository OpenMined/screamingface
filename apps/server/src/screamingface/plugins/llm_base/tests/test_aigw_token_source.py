"""Unit tests for AigwTokenSource — token fetch, cache, refresh, error paths."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from screamingface.plugins.llm_base.aigw_token_source import (
    AigwAuthError,
    AigwTokenError,
    AigwTokenSource,
)


def _ok_payload(*, access_token: str = "tok-1", ttl_seconds: int = 3600) -> dict:
    return {
        "access_token": access_token,
        "expires_at": (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat(),
    }


def _mk_source(handler, *, jwt: str = "jwt-A") -> AigwTokenSource:
    async def jwt_provider() -> str:
        return jwt

    transport = httpx.MockTransport(handler)
    return AigwTokenSource(
        connection_id="conn-1",
        aigw_url="http://aigw.test",
        aigw_jwt_provider=jwt_provider,
        http_transport=transport,
    )


@pytest.mark.asyncio
async def test_fetches_and_returns_access_token():
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/v1/oauth/connections/conn-1/token"
        assert req.headers["authorization"] == "Bearer jwt-A"
        return httpx.Response(200, json=_ok_payload(access_token="tok-A"))

    src = _mk_source(handler)
    assert await src.fetch_token() == "tok-A"


@pytest.mark.asyncio
async def test_caches_until_near_expiry():
    calls = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_ok_payload(access_token=f"tok-{calls}"))

    src = _mk_source(handler)
    tokens = [await src.fetch_token() for _ in range(100)]
    assert tokens == ["tok-1"] * 100
    assert calls == 1


@pytest.mark.asyncio
async def test_refetches_after_expiry():
    calls = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        ttl = 0 if calls == 1 else 3600
        return httpx.Response(200, json=_ok_payload(access_token=f"tok-{calls}", ttl_seconds=ttl))

    src = _mk_source(handler)
    assert await src.fetch_token() == "tok-1"
    assert await src.fetch_token() == "tok-2"
    assert calls == 2


@pytest.mark.asyncio
async def test_401_raises_auth_error():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "jwt expired"})

    src = _mk_source(handler)
    with pytest.raises(AigwAuthError) as exc_info:
        await src.fetch_token()
    assert "re-login" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_404_raises_token_error_with_connection_id():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "connection_not_found"})

    src = _mk_source(handler)
    with pytest.raises(AigwTokenError) as exc_info:
        await src.fetch_token()
    assert "conn-1" in str(exc_info.value)


@pytest.mark.asyncio
async def test_503_raises_token_error():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream refresh failed")

    src = _mk_source(handler)
    with pytest.raises(AigwTokenError):
        await src.fetch_token()


@pytest.mark.asyncio
async def test_transport_error_raises_token_error():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("aigw unreachable")

    src = _mk_source(handler)
    with pytest.raises(AigwTokenError) as exc_info:
        await src.fetch_token()
    assert "aigw" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_concurrent_callers_share_one_fetch():
    calls = 0

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_ok_payload(access_token=f"tok-{calls}"))

    src = _mk_source(handler)
    tokens = await asyncio.gather(*[src.fetch_token() for _ in range(20)])
    assert len(set(tokens)) == 1
    assert calls == 1


@pytest.mark.asyncio
async def test_jwt_provider_called_each_fetch_attempt():
    jwt_calls = 0

    async def jwt_provider() -> str:
        nonlocal jwt_calls
        jwt_calls += 1
        return f"jwt-{jwt_calls}"

    sent_headers: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        sent_headers.append(req.headers["authorization"])
        return httpx.Response(200, json=_ok_payload(ttl_seconds=0))

    transport = httpx.MockTransport(handler)
    src = AigwTokenSource(
        connection_id="conn-1",
        aigw_url="http://aigw.test",
        aigw_jwt_provider=jwt_provider,
        http_transport=transport,
    )
    await src.fetch_token()
    await src.fetch_token()
    assert sent_headers == ["Bearer jwt-1", "Bearer jwt-2"]
