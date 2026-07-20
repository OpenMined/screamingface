from __future__ import annotations

import httpx
import pytest
from model_fixtures import MODEL_ROUTES

from screamingface_engine.app import create_app
from screamingface_engine.gateway import GatewayClient
from screamingface_engine.settings import Settings


@pytest.mark.asyncio
async def test_engine_preserves_safe_gateway_code_without_private_detail() -> None:
    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                503,
                json={
                    "detail": {
                        "code": "provider_unavailable",
                        "message": "private bearer-secret-123",
                    }
                },
            )
        ),
    )
    app = create_app(model_routes=MODEL_ROUTES, settings=Settings(), gateway=gateway)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://engine.test"
    ) as client:
        response = await client.get(
            "/gemini/2.5-flash",
            params={"q": "(Question)!Answer"},
        )
    await gateway.aclose()

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "provider_unavailable",
            "message": "AI Gateway returned HTTP 503 (provider_unavailable) for 'gemini/2.5-flash'",
        }
    }
    assert "bearer-secret-123" not in response.text
