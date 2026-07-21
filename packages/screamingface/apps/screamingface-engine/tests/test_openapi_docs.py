from __future__ import annotations

import asyncio
from collections.abc import MutableMapping
from typing import Any

import httpx
import pytest
from model_fixtures import MODEL_ROUTES

from screamingface_engine.app import create_app
from screamingface_engine.catalog import GatewayModel
from screamingface_engine.docs import openapi_document
from screamingface_engine.gateway import GatewayClient
from screamingface_engine.settings import Settings


def test_openapi_document_covers_http_and_url4_contracts() -> None:
    document = openapi_document(MODEL_ROUTES, max_request_target_bytes=61_440)

    assert document["openapi"] == "3.1.0"
    assert document["info"]["version"] == "0.1.0"
    assert set(document["paths"]) >= {
        "/healthz",
        "/.well-known/screamingface",
        "/openapi.json",
        "/docs",
        "/v1",
        "/v1/connections",
        "/v1/connections/{provider}",
        "/v1/connections/{provider}/oauth",
        "/v1/connections/{provider}/api-key",
        "/auth/callback",
        "/oauth2callback",
        "/callback",
        "/codex/gpt-5.5",
        "/gemini/2.5-flash",
        "/claude/sonnet-4.6",
        "/benchmarks/gpqa/1/cases",
        "/reducers/majority-vote/1",
        "/graders/exact-choice/1",
        "/aggregators/mean/1",
    }
    assert document["x-screamingface-architecture"]["sdk_calls_ai_gateway"] is False
    assert document["x-screamingface-architecture"]["primary_transport"] == "GET /v1?q=…"
    assert document["x-screamingface-status"]["draco"]["executable"] is False
    assert document["x-screamingface-status"]["draco"]["blocking_capability"]
    assert document["x-screamingface-url4"]["limits"]["max_request_target_bytes"] == 61_440

    model_operation = document["paths"]["/codex/gpt-5.5"]["get"]
    assert model_operation["x-screamingface-url4-route"] == "model"
    assert any(parameter["name"] == "q" for parameter in model_operation["parameters"])
    assert any(parameter["name"] == "temperature" for parameter in model_operation["parameters"])


@pytest.mark.asyncio
async def test_docs_and_openapi_are_served_by_the_engine() -> None:
    app = create_app(model_routes=MODEL_ROUTES)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        docs = await client.get("/docs")
        document = await client.get("/openapi.json")
        rejected = await client.post("/openapi.json")

    assert docs.status_code == 200
    assert docs.headers["content-type"].startswith("text/html")
    assert "ScreamingFace engine" in docs.text
    assert "OpenAPI 3.1" in docs.text
    assert 'id="capabilities"' in docs.text
    assert 'id="schemas"' in docs.text
    assert "border-radius" not in docs.text
    assert document.status_code == 200
    assert document.headers["content-type"].startswith("application/json")
    assert document.json()["paths"]["/codex/gpt-5.5"]["get"]["operationId"] == (
        "invoke_codex_gpt_5_5"
    )
    assert rejected.status_code == 405
    assert rejected.json() == {
        "error": {"code": "method_not_allowed", "message": "Documentation routes are GET-only."}
    }


@pytest.mark.asyncio
async def test_runtime_openapi_uses_the_same_gateway_model_snapshot_as_the_node() -> None:
    async def gateway_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/models":
            return httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {
                            "id": "huggingface/Qwen/Qwen3:novita",
                            "object": "model",
                            "owned_by": "huggingface",
                        }
                    ],
                },
            )
        return httpx.Response(200, json={"connections": []})

    settings = Settings(gateway_url="http://gateway.test")
    gateway = GatewayClient(
        settings.gateway_url,
        timeout=settings.gateway_timeout,
        transport=httpx.MockTransport(gateway_handler),
    )
    app = create_app(settings=settings, gateway=gateway)
    receive: asyncio.Queue[MutableMapping[str, Any]] = asyncio.Queue()
    sent: asyncio.Queue[MutableMapping[str, Any]] = asyncio.Queue()
    lifespan = asyncio.create_task(app({"type": "lifespan"}, receive.get, sent.put))

    await receive.put({"type": "lifespan.startup"})
    assert await sent.get() == {"type": "lifespan.startup.complete"}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        document = (await client.get("/openapi.json")).json()
        registry = (await client.get("/.well-known/screamingface")).json()
    await receive.put({"type": "lifespan.shutdown"})
    assert await sent.get() == {"type": "lifespan.shutdown.complete"}
    await lifespan

    assert "/huggingface/Qwen/Qwen3~novita" in document["paths"]
    assert [model["id"] for model in registry["models"]] == ["huggingface/Qwen/Qwen3~novita"]


def test_openapi_rejects_an_empty_model_catalog() -> None:
    with pytest.raises(ValueError, match="at least one model route"):
        openapi_document((), max_request_target_bytes=61_440)


def test_openapi_dynamic_model_ids_are_validated_by_catalog_types() -> None:
    route = GatewayModel("codex/gpt-5.5", "codex")
    assert route.id == "codex/gpt-5.5"
