from __future__ import annotations

import json

import httpx
import pytest
from model_fixtures import MODEL_ROUTES

from screamingface_engine.app import create_app
from screamingface_engine.gateway import GatewayClient
from screamingface_engine.settings import Settings

PUBLIC_MODEL = "gemini/2.5-flash"
GATEWAY_MODEL = "gemini-cli/gemini-2.5-flash"


@pytest.mark.asyncio
async def test_gemini_route_maps_exact_request_and_keeps_calls_independent() -> None:
    upstream: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        upstream.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "explanation": f"Independent call {len(upstream)}.",
                                    "criterion_status": "MET",
                                },
                                separators=(",", ":"),
                            )
                        }
                    }
                ]
            },
        )

    settings = Settings(gateway_url="http://gateway.test")
    gateway = GatewayClient(
        settings.gateway_url,
        timeout=settings.gateway_timeout,
        transport=httpx.MockTransport(handler),
    )
    app = create_app(model_routes=MODEL_ROUTES, settings=settings, gateway=gateway)
    transport = httpx.ASGITransport(app=app)
    expression = (
        "(model_context:0.0:'<criterion>Be correct.</criterion>',"
        "model_result:0.0:/gemini/2.5-flash?temperature=0.2&reasoning=low&max_tokens=4096"
        "&q=($model_context)!'Apply the pinned judge prompt.')!'$model_result'"
    )

    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        registry = (await client.get("/.well-known/screamingface")).json()
        responses = [await client.get("/v1", params={"q": expression}) for _ in range(3)]
    await gateway.aclose()

    model_record = next(model for model in registry["models"] if model["id"] == PUBLIC_MODEL)
    assert model_record == {
        "id": PUBLIC_MODEL,
        "provider": "gemini",
        "supported_tools": [],
        "required_connections": [],
    }
    assert [response.status_code for response in responses] == [200, 200, 200]
    assert [response.headers["content-type"] for response in responses] == [
        "text/plain; charset=utf-8"
    ] * 3
    assert [json.loads(response.text)["explanation"] for response in responses] == [
        "Independent call 1.",
        "Independent call 2.",
        "Independent call 3.",
    ]
    assert (
        upstream
        == [
            {
                "model": GATEWAY_MODEL,
                "messages": [
                    {"role": "system", "content": "Apply the pinned judge prompt."},
                    {"role": "user", "content": "<criterion>Be correct.</criterion>"},
                ],
                "temperature": 0.2,
                "reasoning_effort": "low",
                "max_tokens": 4096,
            }
        ]
        * 3
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outcome", "status", "code", "message"),
    [
        (httpx.Response(404), 500, "model_request_rejected", "AI Gateway returned HTTP 404"),
        (httpx.ConnectError("offline"), 502, "gateway_unavailable", "is unavailable"),
        (httpx.ReadTimeout("slow"), 502, "gateway_timeout", "AI Gateway timed out"),
        (
            httpx.Response(200, text="not-json"),
            502,
            "resolution_failed",
            "AI Gateway returned invalid JSON",
        ),
    ],
)
async def test_gemini_route_maps_gateway_failures_once_as_safe_url4_errors(
    outcome: httpx.Response | Exception,
    status: int,
    code: str,
    message: str,
) -> None:
    calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    settings = Settings(gateway_url="http://gateway.test")
    gateway = GatewayClient(
        settings.gateway_url,
        timeout=settings.gateway_timeout,
        transport=httpx.MockTransport(handler),
    )
    app = create_app(model_routes=MODEL_ROUTES, settings=settings, gateway=gateway)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        response = await client.get(
            f"/{PUBLIC_MODEL}",
            params={"q": "(context)!judge"},
        )
    await gateway.aclose()

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert message in response.json()["error"]["message"]
    assert calls == 1


def test_gemini_catalog_identity_is_an_ordinary_tool_free_model_route() -> None:
    model = next(model for model in MODEL_ROUTES if model.id == PUBLIC_MODEL)

    assert model.gateway_model == GATEWAY_MODEL
    assert model.route == f"/{PUBLIC_MODEL}"
    assert model.tool_capabilities == ()
