from __future__ import annotations

import json
from dataclasses import replace

import httpx
import pytest
from url4 import ResolutionError

from screamingface_engine.tavily import (
    MAX_NORMALIZED_TOOL_BYTES,
    TavilyService,
    _fit,
)
from screamingface_engine.tool_policy import ExtractPolicy, SearchPolicy


def _search_policy(**changes: object) -> SearchPolicy:
    return replace(
        SearchPolicy(
            search_depth="basic",
            chunks_per_source=None,
            max_results=5,
            topic="general",
            time_range=None,
            start_date=None,
            end_date=None,
            include_answer=False,
            include_raw_content=False,
            include_images=False,
            include_image_descriptions=False,
            include_favicon=False,
            include_domains=(),
            exclude_domains=("blocked.example",),
            country=None,
            auto_parameters=False,
            exact_match=False,
            include_usage=False,
            safe_search=False,
        ),
        **changes,
    )


def _extract_policy(**changes: object) -> ExtractPolicy:
    return replace(
        ExtractPolicy(
            extract_depth="basic",
            chunks_per_source=None,
            include_images=False,
            include_favicon=False,
            format="markdown",
            timeout=None,
            include_usage=False,
        ),
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
async def test_search_maps_policy_and_returns_only_normalized_enabled_fields() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/usage":
            return httpx.Response(200, json={"key": {}, "account": {}})
        return httpx.Response(
            200,
            json={
                "answer": "Summary",
                "images": [{"url": "https://img.example/a", "description": "Diagram"}],
                "results": [
                    {
                        "title": "Source",
                        "url": "https://example.org/source",
                        "content": "Evidence",
                        "score": 0.9,
                        "raw_content": "Raw evidence",
                        "favicon": "https://example.org/favicon.ico",
                        "private_unknown": "must disappear",
                    }
                ],
                "usage": {"credits": 2},
                "request_id": "must-disappear",
                "response_time": 9.2,
            },
        )

    policy = _search_policy(
        include_answer="basic",
        include_raw_content="markdown",
        include_images=True,
        include_image_descriptions=True,
        include_favicon=True,
        include_usage=True,
    )
    service = await _connected_service(handler)

    result = await service.search("research question", policy)

    await service.aclose()
    assert requests[1].headers["authorization"] == "Bearer tvly-private"
    assert json.loads(requests[1].content) == policy.request_body("research question")
    assert result == {
        "answer": "Summary",
        "results": [
            {
                "title": "Source",
                "url": "https://example.org/source",
                "content": "Evidence",
                "score": 0.9,
                "raw_content": "Raw evidence",
                "favicon": "https://example.org/favicon.ico",
            }
        ],
        "images": [{"url": "https://img.example/a", "description": "Diagram"}],
        "usage": {"credits": 2},
        "truncated": False,
    }
    assert "request_id" not in json.dumps(result)


@pytest.mark.asyncio
async def test_extract_maps_optional_query_and_bounds_normalized_content() -> None:
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
                ],
                "failed_results": [],
            },
        )

    service = await _connected_service(handler)
    result = await service.extract(
        "https://example.org/long",
        _extract_policy(chunks_per_source=3),
        query="specific evidence",
    )

    await service.aclose()
    assert result["url"] == "https://example.org/long"
    assert result["truncated"] is True
    assert len(json.dumps(result, separators=(",", ":")).encode()) <= MAX_NORMALIZED_TOOL_BYTES


@pytest.mark.asyncio
async def test_transient_tavily_failures_retry_twice_then_succeed() -> None:
    attempts = 0
    sleeps: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.path == "/usage":
            return httpx.Response(200, json={"key": {}, "account": {}})
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, text="private upstream body")
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
async def test_execution_auth_failure_invalidates_key_without_exposing_body() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/usage":
            return httpx.Response(200, json={"key": {}, "account": {}})
        return httpx.Response(401, text="private tvly-private diagnostic")

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
async def test_execution_statuses_become_safe_typed_failures(status: int, code: str) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/usage":
            return httpx.Response(200, json={"key": {}, "account": {}})
        return httpx.Response(status, text="private upstream diagnostic")

    service = await _connected_service(handler)

    with pytest.raises(ResolutionError) as captured:
        await service.search("query", _search_policy())

    await service.aclose()
    assert captured.value.code == code
    assert "private upstream" not in str(captured.value)


@pytest.mark.asyncio
async def test_malformed_success_aborts_without_retry() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if request.url.path == "/usage":
            return httpx.Response(200, json={"key": {}, "account": {}})
        calls += 1
        return httpx.Response(200, json={"results": "not-a-list"})

    service = await _connected_service(handler)

    with pytest.raises(ResolutionError) as captured:
        await service.search("query", _search_policy())

    await service.aclose()
    assert captured.value.code == "invalid_provider_response"
    assert calls == 1


@pytest.mark.asyncio
async def test_missing_connection_and_network_exhaustion_are_safe() -> None:
    service = TavilyService()
    with pytest.raises(ResolutionError) as missing:
        await service.search("query", _search_policy())
    assert missing.value.code == "authentication_required"
    await service.aclose()

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
    ("payload", "policy"),
    [
        ({"results": [None]}, _search_policy()),
        (
            {
                "results": [
                    {"title": "t", "url": "https://example.org", "content": "c", "score": True}
                ]
            },
            _search_policy(),
        ),
        ({"results": [], "images": "bad"}, _search_policy(include_images=True)),
        ({"results": [], "images": [None]}, _search_policy(include_images=True)),
        ({"results": [], "usage": None}, _search_policy(include_usage=True)),
        ({"results": [], "usage": {"credits": True}}, _search_policy(include_usage=True)),
        (
            {"results": [{"url": "https://example.org", "content": "c", "score": 0.1}]},
            _search_policy(),
        ),
        (
            {
                "results": [
                    {
                        "title": "t",
                        "url": "https://example.org",
                        "content": "c",
                        "score": 0.1,
                        "raw_content": 7,
                    }
                ]
            },
            _search_policy(include_raw_content=True),
        ),
    ],
)
async def test_malformed_search_shapes_fail_closed(
    payload: dict[str, object], policy: SearchPolicy
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/usage":
            return httpx.Response(200, json={"key": {}, "account": {}})
        return httpx.Response(200, json=payload)

    service = await _connected_service(handler)
    with pytest.raises(ResolutionError) as captured:
        await service.search("query", policy)
    await service.aclose()
    assert captured.value.code == "invalid_provider_response"


@pytest.mark.asyncio
async def test_search_caps_results_and_extract_keeps_enabled_enrichment() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/usage":
            return httpx.Response(200, json={"key": {}, "account": {}})
        if request.url.path == "/search":
            item = {"title": "t", "url": "https://example.org", "content": "c", "score": 0.5}
            return httpx.Response(200, json={"results": [item, item]})
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://example.org",
                        "raw_content": "evidence",
                        "images": [{"url": "https://example.org/image.png"}],
                        "favicon": "https://example.org/favicon.ico",
                    }
                ],
                "usage": {"credits": 1},
            },
        )

    service = await _connected_service(handler)
    search = await service.search("query", _search_policy(max_results=1))
    extracted = await service.extract(
        "https://example.org",
        _extract_policy(include_images=True, include_favicon=True, include_usage=True),
        query=None,
    )
    await service.aclose()
    results = search["results"]
    assert isinstance(results, list)
    assert len(results) == 1
    assert search["truncated"] is True
    assert extracted == {
        "url": "https://example.org",
        "content": "evidence",
        "images": [{"url": "https://example.org/image.png"}],
        "favicon": "https://example.org/favicon.ico",
        "usage": {"credits": 1},
        "truncated": False,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"results": "bad"}, {"results": [None]}])
async def test_malformed_extract_shapes_fail_closed(payload: dict[str, object]) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/usage":
            return httpx.Response(200, json={"key": {}, "account": {}})
        return httpx.Response(200, json=payload)

    service = await _connected_service(handler)
    with pytest.raises(ResolutionError) as captured:
        await service.extract("https://example.org", _extract_policy(), query=None)
    await service.aclose()
    assert captured.value.code == "invalid_provider_response"


def test_normalized_result_fit_drops_enrichment_then_rejects_unbounded_core() -> None:
    payload: dict[str, object] = {
        "images": [{"url": "x" * MAX_NORMALIZED_TOOL_BYTES}],
        "results": [{"raw_content": "x" * MAX_NORMALIZED_TOOL_BYTES, "favicon": "icon"}],
    }
    assert _fit(payload) == {"results": [{}], "truncated": True}

    with pytest.raises(ResolutionError) as captured:
        _fit({"answer": "x" * (MAX_NORMALIZED_TOOL_BYTES + 1)})
    assert captured.value.code == "invalid_provider_response"
