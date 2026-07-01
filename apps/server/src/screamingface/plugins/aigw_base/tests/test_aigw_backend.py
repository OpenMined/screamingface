"""Unit tests for AigwBackend — mocks the gateway via httpx.MockTransport."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from screamingface.plugins.aigw_base.backend import (
    AIGW_ACCOUNT_ACTIVATION_REQUIRED_CODE,
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
async def test_403_account_activation_required_maps_to_auth_error() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "detail": {
                    "code": "account_activation_required",
                    "message": "Activate Google Antigravity for this Google account, then retry.",
                }
            },
        )

    backend = _backend(http_client_factory=_factory(httpx.MockTransport(handler)))
    with pytest.raises(AuthError, match="Activate Google Antigravity"):
        await backend.run(
            [CoreMessage(role="user", content="hi")],
            model="antigravity/gemini-3-flash",
        )


@pytest.mark.anyio
async def test_provider_unavailable_detail_maps_to_backend_error() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            502,
            json={
                "detail": {
                    "code": "provider_unavailable",
                    "message": "Antigravity backend unavailable. Try again later.",
                }
            },
        )

    backend = _backend(http_client_factory=_factory(httpx.MockTransport(handler)))
    with pytest.raises(BackendError) as exc_info:
        await backend.run(
            [CoreMessage(role="user", content="hi")],
            model="antigravity/gemini-3-flash",
        )

    assert type(exc_info.value) is BackendError
    assert exc_info.value.status == 502
    assert (
        str(exc_info.value)
        == "Gateway provider unavailable: Antigravity backend unavailable. Try again later."
    )


@pytest.mark.anyio
async def test_rate_limited_detail_preserves_retry_after() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={"detail": {"code": "rate_limited", "message": "quota reset later"}},
            headers={"retry-after": "30"},
        )

    backend = _backend(http_client_factory=_factory(httpx.MockTransport(handler)))
    with pytest.raises(BackendError) as exc_info:
        await backend.run(
            [CoreMessage(role="user", content="hi")],
            model="antigravity/gemini-3-flash",
        )

    assert exc_info.value.status == 429
    assert exc_info.value.retry_after == 30.0
    assert str(exc_info.value) == "Gateway rate limited: quota reset later"


@pytest.mark.anyio
async def test_gateway_error_fallthrough_preserves_retry_after() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="boom", headers={"retry-after": "5"})

    backend = _backend(http_client_factory=_factory(httpx.MockTransport(handler)))
    with pytest.raises(AigwGatewayError) as exc_info:
        await backend.run(
            [CoreMessage(role="user", content="hi")],
            model="antigravity/gemini-3-flash",
        )

    assert exc_info.value.status == 503
    assert exc_info.value.retry_after == 5.0


@pytest.mark.anyio
async def test_provider_error_403_remains_backend_error_until_gateway_semantics_change() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"detail": {"code": "provider_error", "message": "raw provider forbidden"}},
        )

    backend = _backend(http_client_factory=_factory(httpx.MockTransport(handler)))
    with pytest.raises(BackendError) as exc_info:
        await backend.run(
            [CoreMessage(role="user", content="hi")],
            model="antigravity/gemini-3-flash",
        )

    assert type(exc_info.value) is BackendError
    assert exc_info.value.status == 403
    assert str(exc_info.value) == "Gateway provider error: raw provider forbidden"


def test_account_activation_code_contract_matches_gateway_literal() -> None:
    repo_root = Path(__file__).resolve().parents[7]
    source = (
        repo_root / "apps/aigateway/src/aigateway/plugins/antigravity_provider/chat_handler.py"
    ).read_text()

    assert (
        f'ANTIGRAVITY_ACTIVATION_REQUIRED_CODE = "{AIGW_ACCOUNT_ACTIVATION_REQUIRED_CODE}"'
        in source
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
