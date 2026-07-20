from __future__ import annotations

import json

import httpx
import pytest

from screamingface_engine.app import create_app
from screamingface_engine.catalog import MODEL_ROUTES
from screamingface_engine.gateway import GatewayClient
from screamingface_engine.settings import Settings

PUBLIC_JUDGE = "gemini/3.1-pro-preview"
GATEWAY_JUDGE = "gemini-cli/gemini-3.1-pro-preview"


@pytest.mark.asyncio
async def test_judge_route_maps_exact_request_and_keeps_passes_independent() -> None:
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
                                    "explanation": f"Independent pass {len(upstream)}.",
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
    app = create_app(settings=settings, gateway=gateway)
    transport = httpx.ASGITransport(app=app)
    expression = (
        "(model_context='<criterion>Be correct.</criterion>',"
        "/gemini/3.1-pro-preview?temperature=0.2&reasoning=low&max_tokens=4096"
        "&q=($model_context)!'Apply the pinned judge prompt.')"
    )

    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        registry = (await client.get("/.well-known/screamingface")).json()
        responses = [await client.get("/v1", params={"q": expression}) for _ in range(3)]
    await gateway.aclose()

    judge_record = next(model for model in registry["models"] if model["id"] == PUBLIC_JUDGE)
    assert judge_record == {"id": PUBLIC_JUDGE, "provider": "gemini", "supported_tools": []}
    assert [response.status_code for response in responses] == [200, 200, 200]
    assert [response.headers["content-type"] for response in responses] == [
        "text/plain; charset=utf-8"
    ] * 3
    assert [json.loads(response.text)["explanation"] for response in responses] == [
        "Independent pass 1.",
        "Independent pass 2.",
        "Independent pass 3.",
    ]
    assert (
        upstream
        == [
            {
                "model": GATEWAY_JUDGE,
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
async def test_judge_route_maps_gateway_failures_once_as_safe_url4_errors(
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
    app = create_app(settings=settings, gateway=gateway)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://engine.test") as client:
        response = await client.get(
            f"/{PUBLIC_JUDGE}",
            params={"q": "(context)!judge"},
        )
    await gateway.aclose()

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert message in response.json()["error"]["message"]
    assert calls == 1


def test_judge_catalog_identity_is_an_ordinary_tool_free_model_route() -> None:
    judge = next(model for model in MODEL_ROUTES if model.id == PUBLIC_JUDGE)

    assert judge.gateway_model == GATEWAY_JUDGE
    assert judge.route == f"/{PUBLIC_JUDGE}"
    assert judge.tool_capabilities == ()
