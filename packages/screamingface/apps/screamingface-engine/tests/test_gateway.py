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
        path="/gemini/2.5-flash",
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
                "model": "gemini-cli/gemini-2.5-flash",
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "detail_code", "expected_code", "permanent"),
    [
        (401, "auth_required", "connection_needs_reauth", True),
        (404, "profile_not_found", "connection_needs_reauth", True),
        (403, "access_denied", "provider_access_denied", True),
        (400, "bad_request", "invalid_model_request", True),
        (429, "rate_limited", "rate_limited", False),
        (503, "provider_unavailable", "provider_unavailable", False),
    ],
)
async def test_gateway_normalizes_safe_model_failure_codes_without_upstream_detail(
    status: int,
    detail_code: str,
    expected_code: str,
    permanent: bool,
) -> None:
    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                status,
                json={
                    "detail": {
                        "code": detail_code,
                        "message": "private provider detail bearer-secret-123",
                    }
                },
            )
        ),
    )

    with pytest.raises(ResolutionError) as captured:
        await gateway.complete(
            MODEL_ROUTES[1],
            Request("/gemini/2.5-flash", "question", "answer", {}),
        )
    await gateway.aclose()

    assert captured.value.code == expected_code
    assert captured.value.permanent is permanent
    assert "gemini/2.5-flash" in str(captured.value)
    assert "bearer-secret-123" not in str(captured.value)


@pytest.mark.asyncio
async def test_gateway_malformed_failure_falls_back_to_safe_status_classification() -> None:
    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(502, text="private non-json upstream response")
        ),
    )

    with pytest.raises(ResolutionError) as captured:
        await gateway.complete(
            MODEL_ROUTES[1],
            Request("/gemini/2.5-flash", "question", "answer", {}),
        )
    await gateway.aclose()

    assert captured.value.code == "provider_unavailable"
    assert captured.value.permanent is False
    assert "private non-json" not in str(captured.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("private_message", "safe_reason"),
    [
        ("Gemini Code Assist setup unreachable: private-host", "provider setup unreachable"),
        (
            "Gemini Code Assist setup did not return cloudaicompanionProject",
            "provider setup incomplete",
        ),
        ("Gemini Code Assist request unreachable: private-host", "provider request unreachable"),
        ("Gemini Code Assist response is not JSON", "invalid provider response"),
        ("Gemini response missing candidates", "provider response missing candidates"),
    ],
)
async def test_gateway_surfaces_only_whitelisted_safe_provider_reason(
    private_message: str,
    safe_reason: str,
) -> None:
    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                502,
                json={
                    "detail": {
                        "code": "provider_unavailable",
                        "message": private_message,
                    }
                },
            )
        ),
    )

    with pytest.raises(ResolutionError) as captured:
        await gateway.complete(
            MODEL_ROUTES[1],
            Request("/gemini/2.5-flash", "question", "answer", {}),
        )
    await gateway.aclose()

    assert safe_reason in str(captured.value)
    assert "private-host" not in str(captured.value)


@pytest.mark.asyncio
async def test_gateway_omits_unrecognized_provider_failure_detail() -> None:
    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                502,
                json={
                    "detail": {
                        "code": "provider_unavailable",
                        "message": "unrecognized private provider diagnostic",
                    }
                },
            )
        ),
    )

    with pytest.raises(ResolutionError) as captured:
        await gateway.complete(
            MODEL_ROUTES[1],
            Request("/gemini/2.5-flash", "question", "answer", {}),
        )
    await gateway.aclose()

    assert "unrecognized private" not in str(captured.value)


@pytest.mark.asyncio
async def test_gateway_classifies_retired_provider_model_without_exposing_detail() -> None:
    gateway = GatewayClient(
        "http://gateway.test",
        timeout=5,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                404,
                json={
                    "detail": {
                        "code": "provider_error",
                        "message": (
                            "This model models/gemini-old is no longer available to new users. "
                            "private provider detail"
                        ),
                    }
                },
            )
        ),
    )

    with pytest.raises(ResolutionError) as captured:
        await gateway.complete(
            MODEL_ROUTES[1],
            Request("/gemini/2.5-flash", "question", "answer", {}),
        )
    await gateway.aclose()

    assert captured.value.code == "model_unavailable"
    assert captured.value.permanent is True
    assert "model unavailable" in str(captured.value)
    assert "private provider detail" not in str(captured.value)
