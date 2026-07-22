from __future__ import annotations

import json
from dataclasses import replace

import httpx
import pytest
from url4 import ResolutionError

from screamingface_engine.tavily import MAX_NORMALIZED_TOOL_BYTES, TavilyService, _fit
from screamingface_engine.tool_policy import FetchPolicy, SearchPolicy


def _search_policy(**changes: object) -> SearchPolicy:
    return replace(
        SearchPolicy(5, (), ("blocked.example",)),
        **changes,
    )


async def _connected_service(handler, *, sleeps: list[float] | None = None) -> TavilyService:
    async def sleep(delay: float) -> None:
        if sleeps is not None:
            sleeps.append(delay)

    service = TavilyService(transport=httpx.MockTransport(handler), sleep=sleep)
    await service.set_api_key("tvly-private")
    return service


@pytest.mark.asyncio
async def test_search_maps_portable_policy_and_normalizes_results() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/usage":
            return httpx.Response(200, json={"key": {}, "account": {}})
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Source",
                        "url": "https://example.org/source",
                        "content": "Evidence",
                        "score": 0.9,
                        "private_unknown": "must disappear",
                    }
                ],
                "request_id": "must disappear",
            },
        )

    policy = _search_policy()
    service = await _connected_service(handler)
    result = await service.search("research question", policy)
    await service.aclose()

    assert requests[1].headers["authorization"] == "Bearer tvly-private"
    assert json.loads(requests[1].content) == policy.tavily_request_body("research question")
    assert result == {
        "answer": None,
        "results": [
            {
                "title": "Source",
                "url": "https://example.org/source",
                "content": "Evidence",
                "score": 0.9,
            }
        ],
        "truncated": False,
    }


@pytest.mark.asyncio
async def test_extract_maps_optional_query_and_bounds_content() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/usage":
            return httpx.Response(200, json={"key": {}, "account": {}})
        assert json.loads(request.content)["query"] == "specific evidence"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://example.org/long",
                        "raw_content": "x" * (MAX_NORMALIZED_TOOL_BYTES + 1000),
                    }
                ]
            },
        )

    service = await _connected_service(handler)
    result = await service.extract(
        "https://example.org/long", FetchPolicy(), query="specific evidence"
    )
    await service.aclose()
    assert result["truncated"] is True
    assert len(json.dumps(result, separators=(",", ":")).encode()) <= MAX_NORMALIZED_TOOL_BYTES


@pytest.mark.asyncio
async def test_transient_failures_retry_twice_then_succeed() -> None:
    attempts = 0
    sleeps: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.path == "/usage":
            return httpx.Response(200, json={"key": {}, "account": {}})
        attempts += 1
        if attempts < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"results": []})

    service = await _connected_service(handler, sleeps=sleeps)
    assert await service.search("query", _search_policy()) == {
        "answer": None,
        "results": [],
        "truncated": False,
    }
    await service.aclose()
    assert attempts == 3
    assert sleeps == [2.0, 4.0]


@pytest.mark.asyncio
async def test_auth_failure_invalidates_key_without_exposing_body() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/usage":
            return httpx.Response(200, json={"key": {}, "account": {}})
        return httpx.Response(401, text="private diagnostic")

    service = await _connected_service(handler)
    with pytest.raises(ResolutionError) as captured:
        await service.search("query", _search_policy())
    assert captured.value.code == "authentication_required"
    assert "private" not in str(captured.value)
    assert (await service.get_public())["status"] == "not_connected"
    await service.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code"),
    [(400, "invalid_tool_request"), (429, "rate_limited"), (503, "provider_unavailable")],
)
async def test_statuses_become_safe_typed_failures(status: int, code: str) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/usage":
            return httpx.Response(200, json={"key": {}, "account": {}})
        return httpx.Response(status, text="private upstream diagnostic")

    service = await _connected_service(handler)
    with pytest.raises(ResolutionError) as captured:
        await service.search("query", _search_policy())
    await service.aclose()
    assert captured.value.code == code
    assert "private" not in str(captured.value)


@pytest.mark.asyncio
async def test_missing_connection_and_network_exhaustion_are_safe() -> None:
    disconnected = TavilyService()
    with pytest.raises(ResolutionError) as missing:
        await disconnected.search("query", _search_policy())
    assert missing.value.code == "authentication_required"
    await disconnected.aclose()

    attempts = 0
    sleeps: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.path == "/usage":
            return httpx.Response(200, json={"key": {}, "account": {}})
        attempts += 1
        raise httpx.ConnectError("private network detail", request=request)

    service = await _connected_service(handler, sleeps=sleeps)
    with pytest.raises(ResolutionError) as exhausted:
        await service.search("query", _search_policy())
    await service.aclose()
    assert exhausted.value.code == "provider_unavailable"
    assert "private" not in str(exhausted.value)
    assert attempts == 3
    assert sleeps == [2.0, 4.0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"results": "bad"},
        {"results": [None]},
        {"results": [{"title": "t", "url": "https://example.org", "content": "c", "score": True}]},
    ],
)
async def test_malformed_search_shapes_fail_closed(payload: dict[str, object]) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/usage":
            return httpx.Response(200, json={"key": {}, "account": {}})
        return httpx.Response(200, json=payload)

    service = await _connected_service(handler)
    with pytest.raises(ResolutionError) as captured:
        await service.search("query", _search_policy())
    await service.aclose()
    assert captured.value.code == "invalid_provider_response"


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"results": "bad"}, {"results": [None]}])
async def test_malformed_extract_shapes_fail_closed(payload: dict[str, object]) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/usage":
            return httpx.Response(200, json={"key": {}, "account": {}})
        return httpx.Response(200, json=payload)

    service = await _connected_service(handler)
    with pytest.raises(ResolutionError) as captured:
        await service.extract("https://example.org", FetchPolicy(), query=None)
    await service.aclose()
    assert captured.value.code == "invalid_provider_response"


def test_normalized_result_fit_rejects_unbounded_core() -> None:
    with pytest.raises(ResolutionError) as captured:
        _fit({"answer": "x" * (MAX_NORMALIZED_TOOL_BYTES + 1)})
    assert captured.value.code == "invalid_provider_response"
