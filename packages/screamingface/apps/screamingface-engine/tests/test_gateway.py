from __future__ import annotations

import json

import httpx
import pytest
from url4 import Request, ResolutionError

from screamingface_engine.catalog import MODEL_ROUTES
from screamingface_engine.gateway import GatewayClient


@pytest.mark.asyncio
async def test_gateway_maps_public_model_and_reuses_one_client() -> None:
    seen: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "answer"}}]})

    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(handler),
    )
    request = Request(
        path="/gemini/2.5",
        context="The question",
        intent="Answer it",
        params={"temperature": "0", "max_tokens": "8", "reasoning": "high"},
    )

    first = await gateway.complete(MODEL_ROUTES[1], request)
    client = gateway._client
    second = await gateway.complete(MODEL_ROUTES[1], request)
    await gateway.aclose()

    assert first == second == "answer"
    assert client is not None
    assert (
        seen
        == [
            {
                "model": "gemini-cli/gemini-2.5-pro",
                "messages": [
                    {"role": "system", "content": "Answer it"},
                    {"role": "user", "content": "The question"},
                ],
                "temperature": 0.0,
                "max_tokens": 8,
                "reasoning_effort": "high",
            }
        ]
        * 2
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"tools": "web_search"}, "unsupported model parameter"),
        ({"temperature": "nan"}, "finite number"),
        ({"temperature": ""}, "finite number"),
        ({"max_tokens": "0"}, "positive integer"),
        ({"max_tokens": "1.5"}, "positive integer"),
        ({"reasoning": "extreme"}, "reasoning must be one of"),
    ],
)
async def test_gateway_rejects_invalid_params_before_http(
    params: dict[str, str], message: str
) -> None:
    calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200)

    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ResolutionError, match=message) as raised:
        await gateway.complete(
            MODEL_ROUTES[0],
            Request("/codex/gpt-5.5", "question", "answer", params),
        )
    await gateway.aclose()

    assert raised.value.code == "malformed_source"
    assert raised.value.permanent is True
    assert calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(503), "HTTP 503"),
        (httpx.Response(200, text="not-json"), "invalid JSON"),
        (httpx.Response(200, json={}), "no first choice"),
        (httpx.Response(200, json={"choices": [{}]}), "no text content"),
    ],
)
async def test_gateway_converts_upstream_protocol_failures(
    response: httpx.Response, message: str
) -> None:
    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(lambda _request: response),
    )

    with pytest.raises(ResolutionError, match=message) as raised:
        await gateway.complete(
            MODEL_ROUTES[0],
            Request("/codex/gpt-5.5", "question", "answer", {}),
        )
    await gateway.aclose()

    assert raised.value.permanent is False


@pytest.mark.asyncio
async def test_gateway_converts_connection_and_timeout_failures() -> None:
    exceptions = [httpx.ConnectError("offline"), httpx.ReadTimeout("slow")]
    for exception in exceptions:

        async def handler(request: httpx.Request, exc: Exception = exception) -> httpx.Response:
            raise exc

        gateway = GatewayClient(
            "http://gateway.test",
            timeout=5,
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(ResolutionError):
            await gateway.complete(
                MODEL_ROUTES[0],
                Request("/codex/gpt-5.5", "question", "answer", {}),
            )
        await gateway.aclose()
