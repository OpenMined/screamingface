from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from screamingface.plugins.aigw_base.client import (
    AigwGatewayClient,
    AigwGatewayUnavailable,
    clear_gateway_session,
)


def _app() -> SimpleNamespace:
    return SimpleNamespace(
        state=SimpleNamespace(
            config=SimpleNamespace(
                plugin_config={
                    "aigw-base": {
                        "mode": "local_managed",
                        "gateway_url": "http://gateway",
                    }
                }
            ),
            plugins=SimpleNamespace(active_plugins={}),
        )
    )


def test_sync_request_tolerates_missing_app_state() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/profiles"
        return httpx.Response(200, json={"ok": True})

    def factory(timeout: float) -> httpx.Client:
        return httpx.Client(
            transport=httpx.MockTransport(handler),
            timeout=httpx.Timeout(timeout),
        )

    response = AigwGatewayClient(None, sync_http_client_factory=factory).request_sync(
        "GET",
        "/profiles",
    )

    assert response.json() == {"ok": True}


@pytest.mark.anyio
async def test_logout_cancels_in_flight_gateway_request() -> None:
    app = _app()
    started = asyncio.Event()

    async def handler(_req: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.sleep(10)
        return httpx.Response(200)

    def factory(timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            timeout=httpx.Timeout(timeout),
        )

    task = asyncio.create_task(
        AigwGatewayClient(app, http_client_factory=factory).request(
            "GET",
            "/slow",
            timeout_seconds=10,
        )
    )
    await started.wait()
    clear_gateway_session(app)

    with pytest.raises(AigwGatewayUnavailable):
        await task


@pytest.mark.anyio
async def test_runner_disabled_cancels_in_flight_gateway_request(monkeypatch) -> None:
    monkeypatch.delenv("SF_AIGW_RUNNER_DISABLED", raising=False)
    app = _app()
    started = asyncio.Event()

    async def handler(_req: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.sleep(10)
        return httpx.Response(200)

    def factory(timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            timeout=httpx.Timeout(timeout),
        )

    task = asyncio.create_task(
        AigwGatewayClient(app, http_client_factory=factory).request(
            "GET",
            "/slow",
            timeout_seconds=10,
        )
    )
    await started.wait()
    monkeypatch.setenv("SF_AIGW_RUNNER_DISABLED", "1")

    with pytest.raises(AigwGatewayUnavailable):
        await asyncio.wait_for(task, timeout=2)
