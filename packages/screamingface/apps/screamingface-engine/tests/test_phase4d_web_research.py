from __future__ import annotations

import json

import httpx
import pytest
from url4 import ResolutionError

from screamingface_engine.web_research import SearchResult, WebResearchClient


async def _public_address(_host: str) -> tuple[str, ...]:
    return ("93.184.216.34",)


@pytest.mark.asyncio
async def test_search_normalizes_limits_and_filters_unsafe_results() -> None:
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "NVIDIA documentation",
                        "url": "https://docs.nvidia.com/jetson/orin",
                        "content": "Official performance notes",
                    },
                    {
                        "title": "Leaked rubric",
                        "url": "https://huggingface.co/datasets/perplexity-ai/draco/viewer",
                        "content": "Do not expose",
                    },
                    {
                        "title": "Private service",
                        "url": "http://127.0.0.1/secrets",
                        "content": "Do not expose",
                    },
                    {
                        "title": "Second source",
                        "url": "https://example.org/report",
                        "content": "Independent report",
                    },
                ]
            },
        )

    client = WebResearchClient(
        "http://search.test:8080",
        timeout=5,
        max_results=2,
        max_content_chars=2_000,
        max_fetch_bytes=4_000,
        transport=httpx.MockTransport(handler),
        resolver=_public_address,
    )

    results = await client.search("Jetson Orin benchmarks")
    await client.aclose()

    assert results == (
        SearchResult(
            title="NVIDIA documentation",
            url="https://docs.nvidia.com/jetson/orin",
            snippet="Official performance notes",
        ),
        SearchResult(
            title="Second source",
            url="https://example.org/report",
            snippet="Independent report",
        ),
    )
    assert seen[0].url.path == "/search"
    assert seen[0].url.params["q"] == "Jetson Orin benchmarks"
    assert seen[0].url.params["format"] == "json"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(503), "HTTP 503"),
        (httpx.Response(200, text="not-json"), "invalid JSON"),
        (httpx.Response(200, json={}), "results array"),
        (httpx.Response(200, json={"results": ["bad"]}), "result 1"),
    ],
)
async def test_search_rejects_upstream_and_schema_failures(
    response: httpx.Response, message: str
) -> None:
    client = WebResearchClient(
        "http://search.test",
        timeout=5,
        max_results=5,
        max_content_chars=2_000,
        max_fetch_bytes=4_000,
        transport=httpx.MockTransport(lambda _request: response),
        resolver=_public_address,
    )

    with pytest.raises(ResolutionError, match=message):
        await client.search("query")
    await client.aclose()


@pytest.mark.asyncio
async def test_fetch_validates_redirects_and_extracts_bounded_readable_text() -> None:
    requests: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.host == "example.org":
            return httpx.Response(302, headers={"location": "https://docs.example.org/page"})
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=(
                b"<html><head><title>Ignored title</title><script>secret()</script></head>"
                b"<body><h1>Research result</h1><p>Useful evidence and details.</p>"
                b"<style>.hidden{}</style></body></html>"
            ),
        )

    client = WebResearchClient(
        "http://search.test",
        timeout=5,
        max_results=5,
        max_content_chars=35,
        max_fetch_bytes=4_000,
        transport=httpx.MockTransport(handler),
        resolver=_public_address,
    )

    text = await client.fetch("https://example.org/start")
    await client.aclose()

    assert requests == ["https://example.org/start", "https://docs.example.org/page"]
    assert text == "Ignored title Research result Usefu"
    assert "secret" not in text
    assert "hidden" not in text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("file:///etc/passwd", "http or https"),
        ("http://127.0.0.1/admin", "public network"),
        ("http://169.254.169.254/latest/meta-data", "public network"),
        ("https://huggingface.co/datasets/perplexity-ai/draco", "blocked"),
    ],
)
async def test_fetch_rejects_unsafe_targets_before_http(url: str, message: str) -> None:
    calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200)

    client = WebResearchClient(
        "http://search.test",
        timeout=5,
        max_results=5,
        max_content_chars=2_000,
        max_fetch_bytes=4_000,
        transport=httpx.MockTransport(handler),
        resolver=_public_address,
    )

    with pytest.raises(ResolutionError, match=message):
        await client.fetch(url)
    await client.aclose()

    assert calls == 0


@pytest.mark.asyncio
async def test_fetch_rejects_private_dns_content_type_and_oversized_body() -> None:
    async def private_address(_host: str) -> tuple[str, ...]:
        return ("10.0.0.4",)

    private = WebResearchClient(
        "http://search.test",
        timeout=5,
        max_results=5,
        max_content_chars=2_000,
        max_fetch_bytes=4,
        transport=httpx.MockTransport(lambda _request: httpx.Response(200)),
        resolver=private_address,
    )
    with pytest.raises(ResolutionError, match="public network"):
        await private.fetch("https://internal.example/path")
    await private.aclose()

    responses = iter(
        [
            httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"pdf"),
            httpx.Response(200, headers={"content-type": "text/plain"}, content=b"12345"),
        ]
    )
    client = WebResearchClient(
        "http://search.test",
        timeout=5,
        max_results=5,
        max_content_chars=2_000,
        max_fetch_bytes=4,
        transport=httpx.MockTransport(lambda _request: next(responses)),
        resolver=_public_address,
    )
    with pytest.raises(ResolutionError, match="unsupported content type"):
        await client.fetch("https://example.org/file.pdf")
    with pytest.raises(ResolutionError, match="maximum response size"):
        await client.fetch("https://example.org/large.txt")
    await client.aclose()


def test_search_results_serialize_as_stable_tool_content() -> None:
    result = SearchResult("Title", "https://example.org", "Snippet")

    assert json.loads(result.to_json()) == {
        "title": "Title",
        "url": "https://example.org",
        "snippet": "Snippet",
    }


@pytest.mark.asyncio
async def test_search_validates_input_and_converts_transport_failures() -> None:
    blank = WebResearchClient(
        "http://search.test",
        timeout=5,
        max_results=5,
        max_content_chars=2_000,
        max_fetch_bytes=4_000,
    )
    await blank.start()
    with pytest.raises(ResolutionError, match="non-empty query"):
        await blank.search("  ")
    await blank.aclose()

    for failure, message in (("timeout", "timed out"), ("connect", "request failed")):

        async def handler(request: httpx.Request, kind: str = failure) -> httpx.Response:
            if kind == "timeout":
                raise httpx.ReadTimeout("slow", request=request)
            raise httpx.ConnectError("offline", request=request)

        client = WebResearchClient(
            "http://search.test",
            timeout=5,
            max_results=5,
            max_content_chars=2_000,
            max_fetch_bytes=4_000,
            transport=httpx.MockTransport(handler),
        )
        with pytest.raises(ResolutionError, match=message):
            await client.search("query")
        await client.aclose()

    invalid = WebResearchClient(
        "http://search.test",
        timeout=5,
        max_results=5,
        max_content_chars=2_000,
        max_fetch_bytes=4_000,
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=[])),
    )
    with pytest.raises(ResolutionError, match="invalid response"):
        await invalid.search("query")
    await invalid.aclose()


@pytest.mark.asyncio
async def test_fetch_converts_redirect_status_transport_and_length_failures() -> None:
    scenarios: tuple[tuple[httpx.AsyncBaseTransport, str], ...] = (
        (
            httpx.MockTransport(lambda _request: httpx.Response(302)),
            "redirect has no location",
        ),
        (
            httpx.MockTransport(
                lambda _request: httpx.Response(302, headers={"location": "/again"})
            ),
            "redirect limit",
        ),
        (httpx.MockTransport(lambda _request: httpx.Response(404)), "HTTP 404"),
        (
            httpx.MockTransport(
                lambda _request: httpx.Response(
                    200,
                    headers={
                        "content-type": "text/plain",
                        "content-length": "not-a-number",
                    },
                    content=b"text",
                )
            ),
            "invalid content length",
        ),
    )
    for transport, message in scenarios:
        client = WebResearchClient(
            "http://search.test",
            timeout=5,
            max_results=5,
            max_content_chars=2_000,
            max_fetch_bytes=4_000,
            transport=transport,
            resolver=_public_address,
        )
        with pytest.raises(ResolutionError, match=message):
            await client.fetch("https://example.org/start")
        await client.aclose()

    async def offline(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    failed = WebResearchClient(
        "http://search.test",
        timeout=5,
        max_results=5,
        max_content_chars=2_000,
        max_fetch_bytes=4_000,
        transport=httpx.MockTransport(offline),
        resolver=_public_address,
    )
    with pytest.raises(ResolutionError, match="request failed"):
        await failed.fetch("https://example.org")
    await failed.aclose()

    plain = WebResearchClient(
        "http://search.test",
        timeout=5,
        max_results=5,
        max_content_chars=2_000,
        max_fetch_bytes=4_000,
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                content=b"  useful\n text  ",
            )
        ),
        resolver=_public_address,
    )
    assert await plain.fetch("https://example.org") == "useful text"
    await plain.aclose()


@pytest.mark.asyncio
async def test_fetch_rejects_credentials_invalid_ports_and_resolution_failures() -> None:
    for url, message in (
        ("https://user:secret@example.org", "credentials"),
        ("https://example.org:99999", "invalid port"),
    ):
        client = WebResearchClient(
            "http://search.test",
            timeout=5,
            max_results=5,
            max_content_chars=2_000,
            max_fetch_bytes=4_000,
            resolver=_public_address,
        )
        with pytest.raises(ResolutionError, match=message):
            await client.fetch(url)
        await client.aclose()

    async def resolver_error(_host: str) -> tuple[str, ...]:
        raise OSError("DNS unavailable")

    async def resolver_empty(_host: str) -> tuple[str, ...]:
        return ()

    async def resolver_invalid(_host: str) -> tuple[str, ...]:
        return ("not-an-address",)

    for resolver, message in (
        (resolver_error, "could not resolve"),
        (resolver_empty, "could not resolve"),
        (resolver_invalid, "public network"),
    ):
        client = WebResearchClient(
            "http://search.test",
            timeout=5,
            max_results=5,
            max_content_chars=2_000,
            max_fetch_bytes=4_000,
            resolver=resolver,
        )
        with pytest.raises(ResolutionError, match=message):
            await client.fetch("https://example.org")
        await client.aclose()
