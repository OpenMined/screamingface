from __future__ import annotations

import json

import httpx
import pytest
from screamingface import Case

from screamingface_engine.app import create_app
from screamingface_engine.gateway import GatewayClient
from screamingface_engine.settings import Settings


@pytest.mark.asyncio
async def test_profile_serves_registry_manifests_and_normalized_cases_as_plaintext() -> None:
    app = create_app(case_loaders={"gpqa@1": lambda: (Case("q1", "Question", reference="A"),)})
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        health = await client.get("/healthz")
        registry_response = await client.get("/.well-known/screamingface")
        manifest_response = await client.get("/benchmarks/gpqa@1")
        cases_response = await client.get("/benchmarks/gpqa@1/cases")
        draco_response = await client.get("/benchmarks/draco@1")

    registry = json.loads(registry_response.text)
    manifest = json.loads(manifest_response.text)
    cases = [json.loads(line) for line in cases_response.text.splitlines()]

    assert health.text == "ok"
    assert registry["schema"] == "screamingface.registry.v1"
    assert registry["models"] == [
        {"id": "codex/gpt-5.5", "supported_tools": []},
        {"id": "gemini/2.5", "supported_tools": []},
        {"id": "claude/sonnet-4.6", "supported_tools": []},
    ]
    assert registry["benchmarks"] == [
        {"id": "gpqa@1", "manifest": "/benchmarks/gpqa@1", "tools": []}
    ]
    assert manifest["grader"]["type"] == "exact_choice"
    assert cases == [
        {
            "id": "q1",
            "input": "Question",
            "reference": "A",
            "metadata": {},
        }
    ]
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
