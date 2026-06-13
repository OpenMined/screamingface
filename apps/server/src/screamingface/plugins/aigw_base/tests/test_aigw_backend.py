"""Unit tests for AigwBackend — mocks the gateway via httpx.MockTransport."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from screamingface.plugins.aigw_base.backend import (
    AigwBackend,
    AigwGatewayError,
)
from screamingface.plugins.llm_base.errors import (
    AuthError,
    BackendError,
    CredentialNotFoundError,
)
from screamingface.plugins.llm_base.messages import CoreMessage, TextPart


def _factory(transport: httpx.MockTransport):
    def factory(timeout: float):
        return httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(timeout))

    return factory


def _backend(*, http_client_factory, **kwargs) -> AigwBackend:
    return AigwBackend(
        gateway_provider="test-provider",
        http_client_factory=http_client_factory,
        **kwargs,
    )


def _ok_response(text: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "x",
            "object": "chat.completion",
            "model": "anthropic/claude-haiku-4-5",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
        },
    )


@pytest.mark.anyio
async def test_happy_path_extracts_text() -> None:
    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["headers"] = dict(req.headers)
        captured["body"] = json.loads(req.content.decode())
        return _ok_response("pong")

    backend = _backend(
        gateway_url="http://127.0.0.1:9105",
        profile_name="default",
        http_client_factory=_factory(httpx.MockTransport(handler)),
    )
    result = await backend.run(
        [CoreMessage(role="user", content=[TextPart(text="hi")])],
        model="anthropic/claude-haiku-4-5",
        system="be terse",
        max_tokens=10,
    )
    assert isinstance(result, CoreMessage)
    assert isinstance(result.content, list)
    assert result.content[0].text == "pong"  # type: ignore[union-attr]

    assert captured["url"] == "http://127.0.0.1:9105/v1/chat/completions"
    assert captured["headers"]["x-profile"] == "default"
    assert captured["body"]["model"] == "anthropic/claude-haiku-4-5"
    assert captured["body"]["messages"][0] == {"role": "system", "content": "be terse"}
    assert captured["body"]["messages"][1] == {"role": "user", "content": "hi"}
    assert captured["body"]["max_tokens"] == 10


@pytest.mark.anyio
async def test_string_content_passes_through() -> None:
    """CoreMessage.content can be a bare string; that should round-trip too."""

    def handler(_req: httpx.Request) -> httpx.Response:
        return _ok_response("ok")

    backend = _backend(http_client_factory=_factory(httpx.MockTransport(handler)))
    await backend.run(
        [CoreMessage(role="user", content="bare string")],
        model="anthropic/claude-haiku-4-5",
    )


@pytest.mark.anyio
async def test_404_profile_not_found_maps_to_credential_not_found() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={"detail": {"code": "profile_not_found", "provider": "anthropic", "name": "x"}},
        )

    backend = _backend(profile_name="x", http_client_factory=_factory(httpx.MockTransport(handler)))
    with pytest.raises(CredentialNotFoundError, match="not found"):
        await backend.run(
            [CoreMessage(role="user", content="hi")],
            model="anthropic/claude-haiku-4-5",
        )


@pytest.mark.anyio
async def test_409_pending_auth_maps_to_auth_error() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": {"code": "profile_pending_auth"}})

    backend = _backend(http_client_factory=_factory(httpx.MockTransport(handler)))
    with pytest.raises(AuthError, match="awaiting OAuth"):
        await backend.run(
            [CoreMessage(role="user", content="hi")],
            model="anthropic/claude-haiku-4-5",
        )


@pytest.mark.anyio
async def test_401_auth_required_maps_to_auth_error() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"detail": {"code": "auth_required", "message": "refresh failed"}},
        )

    backend = _backend(http_client_factory=_factory(httpx.MockTransport(handler)))
    with pytest.raises(AuthError, match="refresh failed"):
        await backend.run(
            [CoreMessage(role="user", content="hi")],
            model="anthropic/claude-haiku-4-5",
        )


@pytest.mark.anyio
async def test_500_raises_aigw_gateway_error() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    backend = _backend(http_client_factory=_factory(httpx.MockTransport(handler)))
    with pytest.raises(AigwGatewayError):
        await backend.run(
            [CoreMessage(role="user", content="hi")],
            model="anthropic/claude-haiku-4-5",
        )


@pytest.mark.anyio
async def test_unreachable_raises_backend_error() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    backend = _backend(http_client_factory=_factory(httpx.MockTransport(handler)))
    with pytest.raises(BackendError, match="unreachable"):
        await backend.run(
            [CoreMessage(role="user", content="hi")],
            model="anthropic/claude-haiku-4-5",
        )


# ----------------------------------------------------------------------------
# SF-278: gateway client span + W3C traceparent propagation
# ----------------------------------------------------------------------------


@pytest.mark.anyio
async def test_request_injects_traceparent_and_emits_span() -> None:
    """`_request` opens an `llm.POST aigw` span and injects W3C traceparent.

    A locally-instrumented gateway can then link into this trace; remote
    gateways simply ignore the header.
    """
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    if not isinstance(provider, TracerProvider):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    exporter.clear()

    captured: dict[str, Any] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(req.headers)
        return _ok_response("pong")

    backend = _backend(
        gateway_url="http://127.0.0.1:9105",
        profile_name="default",
        http_client_factory=_factory(httpx.MockTransport(handler)),
    )

    # An active recording span is required for inject() to produce traceparent.
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("root"):
        await backend.run(
            [CoreMessage(role="user", content=[TextPart(text="hi")])],
            model="anthropic/claude-haiku-4-5",
        )

    assert "traceparent" in captured["headers"], (
        f"traceparent not propagated to gateway. Headers: {sorted(captured['headers'])}"
    )

    aigw_spans = [s for s in exporter.get_finished_spans() if s.name == "llm.POST aigw"]
    assert len(aigw_spans) == 1
    attrs = dict(aigw_spans[0].attributes or {})
    assert attrs["http.status_code"] == 200
    assert attrs["aigw.provider"] == "test-provider"
    assert attrs["aigw.profile"] == "default"
