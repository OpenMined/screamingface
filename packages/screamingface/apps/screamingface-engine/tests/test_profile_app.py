from __future__ import annotations

import json

import httpx
import pytest

from screamingface_engine.app import create_app
from screamingface_engine.gateway import GatewayClient
from screamingface_engine.settings import Settings


@pytest.mark.asyncio
async def test_profile_serves_only_executable_capability_discovery() -> None:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        health = await client.get("/healthz")
        registry_response = await client.get("/.well-known/screamingface")
        gpqa_response = await client.get("/benchmarks/gpqa@1")
        draco_response = await client.get("/benchmarks/draco@1")

    registry = json.loads(registry_response.text)

    assert health.text == "ok"
    assert registry["schema"] == "screamingface.registry.v1"
    assert registry["models"] == [
        {"id": "codex/gpt-5.5", "provider": "codex", "supported_tools": []},
        {"id": "gemini/2.5", "provider": "gemini", "supported_tools": []},
        {"id": "claude/sonnet-4.6", "provider": "anthropic", "supported_tools": []},
        {
            "id": "gemini/3.1-pro-preview",
            "provider": "gemini",
            "supported_tools": [],
        },
    ]
    assert registry["limits"] == {"max_request_target_bytes": 61440}
    assert set(registry) == {
        "schema",
        "response_schemas",
        "limits",
        "providers",
        "models",
        "reducers",
    }
    assert gpqa_response.status_code == 404
    assert draco_response.status_code == 404
    assert registry_response.headers["content-type"].startswith("text/plain")


@pytest.mark.asyncio
async def test_model_route_and_eval_surface_share_gateway_dispatch() -> None:
    requests: list[dict[str, object]] = []

    async def gateway_handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Four"}}]},
        )

    settings = Settings(gateway_url="http://gateway.test")
    gateway = GatewayClient(
        settings.gateway_url,
        timeout=settings.gateway_timeout,
        transport=httpx.MockTransport(gateway_handler),
    )
    app = create_app(settings=settings, gateway=gateway)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        direct = await client.get(
            "/codex/gpt-5.5",
            params={
                "temperature": "0.2",
                "max_tokens": "12",
                "reasoning": "low",
                "q": "(What is 2 + 2?)!Answer briefly",
            },
        )
        evaluated = await client.get(
            "/v1",
            params={
                "q": (
                    "(question='What is 2 + 2?',"
                    "answer=/codex/gpt-5.5($question)!'Answer briefly',"
                    "{answer:'$answer'})"
                )
            },
        )
    await gateway.aclose()

    assert direct.status_code == 200
    assert direct.text == "Four"
    assert evaluated.status_code == 200
    assert evaluated.json() == {"answer": "Four"}
    assert requests == [
        {
            "model": "codex/gpt-5.5",
            "messages": [
                {"role": "system", "content": "Answer briefly"},
                {"role": "user", "content": "What is 2 + 2?"},
            ],
            "temperature": 0.2,
            "max_tokens": 12,
            "reasoning_effort": "low",
        },
        {
            "model": "codex/gpt-5.5",
            "messages": [
                {"role": "system", "content": "Answer briefly"},
                {"role": "user", "content": "What is 2 + 2?"},
            ],
        },
    ]
