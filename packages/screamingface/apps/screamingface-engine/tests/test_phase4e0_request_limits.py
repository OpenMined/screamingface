from __future__ import annotations

import httpx
import pytest
from model_fixtures import MODEL_ROUTES
from url4 import Url4Node

from screamingface_engine.app import create_app
from screamingface_engine.asgi import EngineASGI
from screamingface_engine.gateway import GatewayClient
from screamingface_engine.settings import Settings, SettingsError


def _gateway() -> GatewayClient:
    return GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(lambda _request: httpx.Response(500)),
    )


def test_request_target_limit_has_a_validated_environment_override() -> None:
    assert Settings().max_request_target_bytes == 61440
    assert (
        Settings.from_env(
            {"SCREAMINGFACE_ENGINE_MAX_REQUEST_TARGET_BYTES": "4096"}
        ).max_request_target_bytes
        == 4096
    )

    with pytest.raises(SettingsError, match="MAX_REQUEST_TARGET_BYTES must be at least 1"):
        Settings.from_env({"SCREAMINGFACE_ENGINE_MAX_REQUEST_TARGET_BYTES": "0"})
    with pytest.raises(SettingsError, match="MAX_REQUEST_TARGET_BYTES must not exceed 61440"):
        Settings.from_env({"SCREAMINGFACE_ENGINE_MAX_REQUEST_TARGET_BYTES": "61441"})


@pytest.mark.asyncio
async def test_registry_advertises_the_configured_request_target_limit() -> None:
    app = create_app(model_routes=MODEL_ROUTES, settings=Settings(max_request_target_bytes=4096))
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        response = await client.get("/.well-known/screamingface")

    assert response.json()["limits"] == {"max_request_target_bytes": 4096}


@pytest.mark.asyncio
async def test_engine_enforces_the_exact_encoded_request_target_boundary() -> None:
    node = Url4Node("request-limit")
    node.data("/healthz", "ok")
    gateway = _gateway()
    allowed_target = httpx.URL("/healthz", params={"x": "1"}).raw_path
    app = EngineASGI(
        node,
        gateway,
        max_inflight=1,
        timeout=1,
        max_request_target_bytes=len(allowed_target),
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        allowed = await client.get("/healthz", params={"x": "1"})
        rejected = await client.get("/healthz", params={"x": "12"})

    await gateway.aclose()
    assert allowed.status_code == 200
    assert rejected.status_code == 414
    assert rejected.json() == {
        "error": {
            "code": "request_target_too_large",
            "message": f"request target exceeds {len(allowed_target)} bytes",
        }
    }
