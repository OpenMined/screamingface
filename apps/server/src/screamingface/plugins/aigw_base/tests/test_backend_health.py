"""Unit tests for AigwBackend.health() — gateway profile-state probe.

We mock the upstream gateway with httpx.MockTransport. Each test asserts
that a given gateway response maps to the documented HealthStatus.
"""

from __future__ import annotations

import httpx
import pytest

from screamingface.plugins.aigw_base.backend import AigwBackend


def _backend(handler) -> AigwBackend:
    transport = httpx.MockTransport(handler)

    def factory(timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, timeout=timeout)

    return AigwBackend(
        gateway_url="http://gateway",
        profile_name="default",
        gateway_provider="anthropic",
        http_client_factory=factory,
    )


@pytest.mark.anyio
async def test_health_authenticated_when_profile_is_authenticated() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        # Health probes the gateway's *anthropic* profile by default
        assert "/v1/auth/anthropic/profiles/default/status" in str(req.url)
        return httpx.Response(
            200,
            json={"state": "authenticated", "account_label": None, "last_refreshed_at": None},
        )

    status = await _backend(handler).health()
    assert status.authenticated is True
    assert status.error is None


@pytest.mark.anyio
async def test_health_not_authenticated_when_profile_is_pending() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"state": "pending"})

    status = await _backend(handler).health()
    assert status.authenticated is False
    assert "OAuth in progress" in (status.error or "")


@pytest.mark.anyio
async def test_health_not_authenticated_when_profile_is_error() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"state": "error"})

    status = await _backend(handler).health()
    assert status.authenticated is False
    assert "error" in (status.error or "").lower()


@pytest.mark.anyio
async def test_health_not_authenticated_when_profile_404() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": "profile_not_found"})

    status = await _backend(handler).health()
    assert status.authenticated is False
    assert "not yet created" in (status.error or "").lower()


@pytest.mark.anyio
async def test_health_not_authenticated_when_gateway_unreachable() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=req)

    status = await _backend(handler).health()
    assert status.authenticated is False
    assert "unreachable" in (status.error or "").lower()
