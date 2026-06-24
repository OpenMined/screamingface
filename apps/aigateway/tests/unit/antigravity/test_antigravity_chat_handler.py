"""Unit 4 — Antigravity chat transport (generateContent-first, MockTransport).

Covers the Antigravity Code Assist body shape (U14: userAgent/requestId, NOT
gemini's user_prompt_id/session_id; systemInstruction as an object-with-parts;
role="model"), the two-layer caller-auth header strip (U4: superset
CLIENT_AUTH_HEADER_NAMES, gateway headers set LAST, negative-by-value scan),
the daily→prod host fallback (U12), per-credential session caching + invalidate,
and pre-stream error mapping (U6: 401/403/429/5xx, NO in-band 429).
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from litellm.llms.custom_llm import CustomLLMError
from litellm.types.utils import ModelResponse

from aigateway.plugins.antigravity_provider.auth import ANTIGRAVITY_PROFILE_HEADER
from aigateway.plugins.antigravity_provider.chat_handler import (
    CLIENT_AUTH_HEADER_NAMES,
    AntigravityCustomLLM,
    _merge_stream_generate_content_sse,
    _should_try_stream_generate_content,
)
from aigateway.plugins.antigravity_provider.message_adapter import (
    build_generate_content_body,
    model_response_from_antigravity,
)
from aigateway.plugins.antigravity_provider.settings import AntigravityPluginSettings

_SETTINGS = AntigravityPluginSettings()
_API_VERSION = _SETTINGS.code_assist_api_version
_PRIMARY = _SETTINGS.code_assist_endpoint
_FALLBACK = _SETTINGS.code_assist_fallback_endpoint


def _http_factory(transport: httpx.MockTransport):
    def factory():
        return httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(5.0))

    return factory


def _antigravity_response(text: str) -> dict[str, Any]:
    return {
        "candidates": [
            {"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}
        ],
        "usageMetadata": {
            "promptTokenCount": 3,
            "candidatesTokenCount": 2,
            "totalTokenCount": 5,
        },
        "responseId": "resp-1",
    }


async def _complete(custom: AntigravityCustomLLM, **kwargs: Any) -> ModelResponse:
    defaults: dict[str, Any] = {
        "model": "antigravity/gemini-3-flash",
        "messages": [{"role": "user", "content": "ping"}],
        "api_base": None,
        "custom_prompt_dict": {},
        "model_response": ModelResponse(),
        "print_verbose": lambda *_a, **_k: None,
        "encoding": None,
        "api_key": "ya29.oauth",
        "logging_obj": None,
        "optional_params": {},
    }
    defaults.update(kwargs)
    return await custom.acompletion(**defaults)


# --- message adapter (U14) -------------------------------------------------


def test_build_body_uses_antigravity_shape() -> None:
    body = build_generate_content_body(
        [
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "yo"},
        ],
        {"max_tokens": 7},
    )
    # systemInstruction is an object with parts (string would 400).
    assert body["systemInstruction"] == {"parts": [{"text": "be terse"}]}
    # role="model" for assistant turns (NOT "assistant").
    roles = [c["role"] for c in body["contents"]]
    assert roles == ["user", "model"]
    assert body["generationConfig"] == {"maxOutputTokens": 7}


def test_model_response_unwraps_role_model() -> None:
    resp = model_response_from_antigravity(
        {"response": _antigravity_response("hello")}, "antigravity/gemini-3-flash"
    )
    assert resp.choices[0].message.content == "hello"
    assert resp.choices[0].finish_reason == "stop"
    assert resp.model_dump()["usage"]["total_tokens"] == 5


# --- oauth generateContent-first path --------------------------------------


@pytest.mark.asyncio
async def test_oauth_path_setup_and_generate_content_body() -> None:
    calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        calls.append(
            {
                "url": str(request.url),
                "headers": dict(request.headers),
                "payload": json.loads(request.content.decode()),
            }
        )
        if str(request.url).endswith(f"{_API_VERSION}:loadCodeAssist"):
            return httpx.Response(200, json={"cloudaicompanionProject": "project-123"})
        return httpx.Response(200, json={"response": _antigravity_response("hi there")})

    custom = AntigravityCustomLLM(
        settings=_SETTINGS, http_client_factory=_http_factory(httpx.MockTransport(handler))
    )
    response = await _complete(
        custom,
        headers={ANTIGRAVITY_PROFILE_HEADER: "acct:default"},
        optional_params={"max_tokens": 7},
    )

    assert calls[0]["url"] == f"{_PRIMARY}/{_API_VERSION}:loadCodeAssist"
    assert calls[1]["url"] == f"{_PRIMARY}/{_API_VERSION}:generateContent"
    assert calls[0]["payload"] == {
        "metadata": {
            "ideType": "ANTIGRAVITY",
            "platform": "PLATFORM_UNSPECIFIED",
            "pluginType": "GEMINI",
        }
    }
    body = calls[1]["payload"]
    # Antigravity outer body (U14): userAgent + requestId, NOT user_prompt_id/session_id.
    assert body["project"] == "project-123"
    assert body["model"] == "gemini-3-flash"
    # userAgent defaults to the proven-working community-spec value "antigravity"
    # (overridable via settings); review #3 / architect ruling.
    assert body["userAgent"] == "antigravity"
    assert "requestType" not in body
    assert "requestId" in body
    assert "user_prompt_id" not in body
    assert "session_id" not in body.get("request", {})
    assert body["request"]["contents"] == [{"role": "user", "parts": [{"text": "ping"}]}]
    assert response.choices[0].message.content == "hi there"


@pytest.mark.asyncio
async def test_generate_content_falls_back_to_stream_generate_content_sse() -> None:
    calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(
            {
                "url": str(request.url),
                "payload": json.loads(request.content.decode()),
            }
        )
        if str(request.url).endswith(f"{_API_VERSION}:loadCodeAssist"):
            return httpx.Response(200, json={"cloudaicompanionProject": "project-123"})
        if ":generateContent" in str(request.url):
            return httpx.Response(404, json={"error": "method not found"})
        assert str(request.url).endswith(f"{_API_VERSION}:streamGenerateContent?alt=sse")
        return httpx.Response(
            200,
            text=(
                'data: {"response":{"candidates":[{"content":{"role":"model",'
                '"parts":[{"text":"hello "}]}}]}}\n\n'
                'data: {"response":{"candidates":[{"content":{"role":"model",'
                '"parts":[{"text":"from sse"}]},"finishReason":"STOP"}],'
                '"usageMetadata":{"promptTokenCount":1,"candidatesTokenCount":2,'
                '"totalTokenCount":3},"responseId":"stream-resp"}}\n\n'
            ),
            headers={"content-type": "text/event-stream"},
        )

    custom = AntigravityCustomLLM(
        settings=_SETTINGS, http_client_factory=_http_factory(httpx.MockTransport(handler))
    )
    response = await _complete(custom, headers={ANTIGRAVITY_PROFILE_HEADER: "acct:default"})

    assert calls[1]["url"] == f"{_PRIMARY}/{_API_VERSION}:generateContent"
    assert calls[2]["url"] == f"{_FALLBACK}/{_API_VERSION}:generateContent"
    assert calls[3]["url"] == f"{_PRIMARY}/{_API_VERSION}:streamGenerateContent?alt=sse"
    assert "requestType" not in calls[3]["payload"]
    assert response.choices[0].message.content == "hello from sse"
    assert response.model_dump()["usage"]["total_tokens"] == 3


# --- two-layer caller-auth strip (U4) --------------------------------------


@pytest.mark.asyncio
async def test_caller_auth_headers_stripped_by_value() -> None:
    calls: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.headers))
        if str(request.url).endswith(f"{_API_VERSION}:loadCodeAssist"):
            return httpx.Response(200, json={"cloudaicompanionProject": "p"})
        return httpx.Response(200, json={"response": _antigravity_response("safe")})

    custom = AntigravityCustomLLM(
        settings=_SETTINGS, http_client_factory=_http_factory(httpx.MockTransport(handler))
    )
    attacker_values = {
        "authorization": "Bearer attacker",
        "x-goog-api-key": "bad-key",
        "x-goog-user-project": "attacker-project",
        "x-goog-authuser": "7",
        "x-goog-iam-authorization-token": "iam-token",
        "x-goog-quota-user": "attacker-quota",
        "x-goog-fieldmask": "attacker-fieldmask",
        "x-goog-request-params": "attacker-request-params",
        "x-goog-api-client": "attacker-api-client",
        "cookie": "session=evil",
    }
    await _complete(
        custom,
        api_key="ya29.real",
        headers={
            ANTIGRAVITY_PROFILE_HEADER: "acct:default",
            "content-type": "text/plain",
            "X-Request-Trace": "ok",
            **attacker_values,
        },
    )

    for headers in calls:
        # Gateway-owned values win.
        assert headers["authorization"] == "Bearer ya29.real"
        assert headers["content-type"] == "application/json"
        # Benign passthrough survives.
        assert headers["x-request-trace"] == "ok"
        # Negative-by-VALUE scan: no attacker value survives in ANY header.
        joined = " ".join(headers.values())
        for value in attacker_values.values():
            assert value not in joined


@pytest.mark.asyncio
async def test_caller_cannot_override_user_agent_via_lowercase() -> None:
    """A caller-supplied lowercase `user-agent` must not survive to upstream.

    httpx merges headers case-insensitively, so a leaked caller `user-agent`
    would ride alongside (or override) the gateway UA. The gateway UA must be
    the only one present (findings review #4).
    """
    calls: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.headers))
        if str(request.url).endswith(f"{_API_VERSION}:loadCodeAssist"):
            return httpx.Response(200, json={"cloudaicompanionProject": "p"})
        return httpx.Response(200, json={"response": _antigravity_response("safe")})

    custom = AntigravityCustomLLM(
        settings=_SETTINGS, http_client_factory=_http_factory(httpx.MockTransport(handler))
    )
    await _complete(
        custom,
        api_key="ya29.real",
        headers={
            ANTIGRAVITY_PROFILE_HEADER: "p1",
            "user-agent": "attacker-ua",  # lowercase — must still be stripped
        },
    )

    assert calls
    for headers in calls:
        # httpx normalizes header keys to lowercase; exactly the gateway UA, no attacker UA.
        assert headers["user-agent"] == _SETTINGS.user_agent
        assert "attacker-ua" not in " ".join(headers.values())


def test_user_agent_is_in_client_auth_header_names() -> None:
    # user-agent must be stripped at BOTH layers (prepare_chat_body + handler).
    assert "user-agent" in CLIENT_AUTH_HEADER_NAMES


def test_client_auth_header_names_is_superset() -> None:
    # U4: superset adds the Code-Assist-surface names on top of gemini's set.
    for name in (
        "authorization",
        "content-type",
        "x-aigw-antigravity-profile",
        "x-goog-api-key",
        "x-goog-user-project",
        "x-goog-authuser",
        "x-goog-iam-authorization-token",
        "cookie",
    ):
        assert name in CLIENT_AUTH_HEADER_NAMES


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("request_timeout", "expected_timeout"),
    [(None, httpx.Timeout(5.0).as_dict()), (httpx.Timeout(1.5), httpx.Timeout(1.5).as_dict())],
)
async def test_request_timeout_preserves_client_default_when_absent(
    request_timeout: httpx.Timeout | None, expected_timeout: dict[str, float | None]
) -> None:
    seen_timeouts: list[dict[str, float | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_timeouts.append(request.extensions["timeout"])
        if str(request.url).endswith(f"{_API_VERSION}:loadCodeAssist"):
            return httpx.Response(200, json={"cloudaicompanionProject": "p"})
        return httpx.Response(200, json={"response": _antigravity_response("safe")})

    transport = httpx.MockTransport(handler)
    custom = AntigravityCustomLLM(
        settings=_SETTINGS,
        http_client_factory=lambda: httpx.AsyncClient(
            transport=transport, timeout=httpx.Timeout(5.0)
        ),
    )
    kwargs: dict[str, Any] = {"headers": {ANTIGRAVITY_PROFILE_HEADER: "p1"}}
    if request_timeout is not None:
        kwargs["timeout"] = request_timeout
    await _complete(custom, **kwargs)

    assert seen_timeouts
    assert seen_timeouts == [expected_timeout for _ in seen_timeouts]


# --- daily -> prod host fallback (U12) -------------------------------------


@pytest.mark.asyncio
async def test_falls_back_to_prod_host_on_daily_404() -> None:
    seen_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        seen_hosts.append(host)
        if "daily-" in host:
            return httpx.Response(404, json={"error": "not found"})
        if str(request.url).endswith(f"{_API_VERSION}:loadCodeAssist"):
            return httpx.Response(200, json={"cloudaicompanionProject": "p"})
        return httpx.Response(200, json={"response": _antigravity_response("from prod")})

    custom = AntigravityCustomLLM(
        settings=_SETTINGS, http_client_factory=_http_factory(httpx.MockTransport(handler))
    )
    response = await _complete(custom, headers={ANTIGRAVITY_PROFILE_HEADER: "p1"})
    assert any("daily-" in h for h in seen_hosts)
    assert any(h == httpx.URL(_FALLBACK).host for h in seen_hosts)
    assert response.choices[0].message.content == "from prod"


# --- error mapping (U6) ----------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected"),
    [(401, 401), (403, 403), (429, 429), (500, 502), (503, 502)],
)
async def test_pre_stream_error_mapping(status: int, expected: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith(f"{_API_VERSION}:loadCodeAssist"):
            return httpx.Response(200, json={"cloudaicompanionProject": "p"})
        return httpx.Response(status, json={"error": "boom"})

    custom = AntigravityCustomLLM(
        settings=_SETTINGS, http_client_factory=_http_factory(httpx.MockTransport(handler))
    )
    with pytest.raises(CustomLLMError) as exc_info:
        await _complete(custom, headers={ANTIGRAVITY_PROFILE_HEADER: "p1"})
    assert exc_info.value.status_code == expected


@pytest.mark.asyncio
async def test_429_carries_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith(f"{_API_VERSION}:loadCodeAssist"):
            return httpx.Response(200, json={"cloudaicompanionProject": "p"})
        return httpx.Response(
            429,
            text='{"error":{"message":"quota will reset after 1m30s."}}',
        )

    custom = AntigravityCustomLLM(
        settings=_SETTINGS, http_client_factory=_http_factory(httpx.MockTransport(handler))
    )
    with pytest.raises(CustomLLMError) as exc_info:
        await _complete(custom, headers={ANTIGRAVITY_PROFILE_HEADER: "p1"})
    assert exc_info.value.status_code == 429
    assert getattr(exc_info.value, "retry_after", None) == 90.0


@pytest.mark.asyncio
async def test_requires_oauth_credentials() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": _antigravity_response("x")})

    custom = AntigravityCustomLLM(
        settings=_SETTINGS, http_client_factory=_http_factory(httpx.MockTransport(handler))
    )
    with pytest.raises(CustomLLMError) as exc_info:
        await _complete(custom, api_key=None)
    assert exc_info.value.status_code == 401


# --- session caching + invalidate ------------------------------------------


@pytest.mark.asyncio
async def test_setup_cached_per_profile_and_invalidate() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith(f"{_API_VERSION}:loadCodeAssist"):
            return httpx.Response(200, json={"cloudaicompanionProject": "p"})
        return httpx.Response(200, json={"response": _antigravity_response("ok")})

    custom = AntigravityCustomLLM(
        settings=_SETTINGS, http_client_factory=_http_factory(httpx.MockTransport(handler))
    )
    setup_calls: list[str] = []

    def counting_handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith(f"{_API_VERSION}:loadCodeAssist"):
            setup_calls.append("setup")
            return httpx.Response(200, json={"cloudaicompanionProject": "p"})
        return httpx.Response(200, json={"response": _antigravity_response("ok")})

    custom = AntigravityCustomLLM(
        settings=_SETTINGS,
        http_client_factory=_http_factory(httpx.MockTransport(counting_handler)),
    )
    await _complete(custom, headers={ANTIGRAVITY_PROFILE_HEADER: "p1"})
    await _complete(custom, headers={ANTIGRAVITY_PROFILE_HEADER: "p1"})
    assert len(setup_calls) == 1  # cached after first
    custom.invalidate_session("p1")
    await _complete(custom, headers={ANTIGRAVITY_PROFILE_HEADER: "p1"})
    assert len(setup_calls) == 2  # re-setup after invalidate


# --- SSE aggregation: no false "stop" (review round 2, finding B) ----------


def _sse(*events: dict[str, Any]) -> str:
    import json as _json

    return "".join(f"data: {_json.dumps(e)}\n\n" for e in events)


def test_sse_aggregates_clean_stop() -> None:
    text = _sse(
        {"response": {"candidates": [{"content": {"role": "model", "parts": [{"text": "hi"}]}}]}},
        {
            "response": {
                "candidates": [
                    {
                        "content": {"role": "model", "parts": [{"text": " there"}]},
                        "finishReason": "STOP",
                    }
                ]
            }
        },
    )
    data = _merge_stream_generate_content_sse(text)
    resp = model_response_from_antigravity(data, "antigravity/gemini-3-flash")
    assert resp.choices[0].message.content == "hi there"
    assert resp.choices[0].finish_reason == "stop"


def test_sse_truncated_stream_without_finish_reason_raises() -> None:
    # Parts arrive but the stream never sends a terminal finishReason → that is
    # truncation, NOT a successful stop. Must raise, never yield finish="stop".
    text = _sse(
        {
            "response": {
                "candidates": [{"content": {"role": "model", "parts": [{"text": "partial"}]}}]
            }
        },
    )
    with pytest.raises(CustomLLMError):
        _merge_stream_generate_content_sse(text)


def test_sse_block_reason_with_partial_content_raises() -> None:
    # A promptFeedback.blockReason means the response was blocked; even with
    # partial content it must raise, not return a false "stop".
    text = _sse(
        {"response": {"candidates": [{"content": {"role": "model", "parts": [{"text": "par"}]}}]}},
        {"response": {"promptFeedback": {"blockReason": "SAFETY"}}},
    )
    with pytest.raises(CustomLLMError):
        _merge_stream_generate_content_sse(text)


def test_sse_error_frame_with_partial_content_raises_with_provider_message() -> None:
    text = _sse(
        {"response": {"candidates": [{"content": {"role": "model", "parts": [{"text": "par"}]}}]}},
        {"error": {"code": 503, "message": "MODEL_CAPACITY_EXHAUSTED"}},
    )
    with pytest.raises(CustomLLMError, match="MODEL_CAPACITY_EXHAUSTED"):
        _merge_stream_generate_content_sse(text)


def test_sse_error_frame_after_stop_still_raises() -> None:
    # Some SSE transports can deliver a terminal-looking candidate before a
    # provider error frame. The error wins; never return a false successful stop.
    text = _sse(
        {
            "response": {
                "candidates": [
                    {
                        "content": {"role": "model", "parts": [{"text": "done"}]},
                        "finishReason": "STOP",
                    }
                ]
            }
        },
        {"error": {"code": 503, "message": "MODEL_CAPACITY_EXHAUSTED"}},
    )
    with pytest.raises(CustomLLMError, match="MODEL_CAPACITY_EXHAUSTED"):
        _merge_stream_generate_content_sse(text)


def test_sse_safety_finish_reason_does_not_become_stop() -> None:
    # A SAFETY terminal finishReason must NOT map to "stop".
    text = _sse(
        {
            "response": {
                "candidates": [
                    {
                        "content": {"role": "model", "parts": [{"text": "x"}]},
                        "finishReason": "SAFETY",
                    }
                ]
            }
        },
    )
    data = _merge_stream_generate_content_sse(text)
    resp = model_response_from_antigravity(data, "antigravity/gemini-3-flash")
    assert resp.choices[0].finish_reason != "stop"
    assert resp.choices[0].finish_reason == "content_filter"


def test_sse_max_tokens_maps_to_length_not_stop() -> None:
    text = _sse(
        {
            "response": {
                "candidates": [
                    {
                        "content": {"role": "model", "parts": [{"text": "x"}]},
                        "finishReason": "MAX_TOKENS",
                    }
                ]
            }
        },
    )
    data = _merge_stream_generate_content_sse(text)
    resp = model_response_from_antigravity(data, "antigravity/gemini-3-flash")
    assert resp.choices[0].finish_reason == "length"


def test_sse_reads_finish_reason_from_later_candidate() -> None:
    text = _sse(
        {
            "response": {
                "candidates": [
                    {"content": {"role": "model", "parts": [{"text": "x"}]}},
                    {"finishReason": "STOP"},
                ]
            }
        },
    )

    data = _merge_stream_generate_content_sse(text)
    resp = model_response_from_antigravity(data, "antigravity/gemini-3-flash")

    assert resp.choices[0].message.content == "x"
    assert resp.choices[0].finish_reason == "stop"


# --- SSE fallback gating: only verb-unsupported 404/405 (finding C) --------


def test_fallback_gating_only_for_verb_unsupported() -> None:
    def _resp(status: int) -> httpx.Response:
        return httpx.Response(status, json={"error": "x"})

    # 404/405 = verb unsupported → try SSE fallback.
    assert _should_try_stream_generate_content(_resp(404)) is True
    assert _should_try_stream_generate_content(_resp(405)) is True
    # 400 (our bad request) + 5xx (provider unavailable) → NO verb retry.
    assert _should_try_stream_generate_content(_resp(400)) is False
    assert _should_try_stream_generate_content(_resp(500)) is False
    assert _should_try_stream_generate_content(_resp(503)) is False
    # Auth/rate-limit never retry (403 is auth_required, NOT a verb-unsupported
    # signal — team-lead ruling: keep it as auth, don't SSE-retry it).
    assert _should_try_stream_generate_content(_resp(401)) is False
    assert _should_try_stream_generate_content(_resp(403)) is False
    assert _should_try_stream_generate_content(_resp(429)) is False


@pytest.mark.asyncio
async def test_generate_content_5xx_maps_to_502_without_sse_retry() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith(f"{_API_VERSION}:loadCodeAssist"):
            return httpx.Response(200, json={"cloudaicompanionProject": "p"})
        calls.append(url)
        return httpx.Response(500, json={"error": "boom"})

    custom = AntigravityCustomLLM(
        settings=_SETTINGS, http_client_factory=_http_factory(httpx.MockTransport(handler))
    )
    with pytest.raises(CustomLLMError) as exc_info:
        await _complete(custom, headers={ANTIGRAVITY_PROFILE_HEADER: "p1"})
    assert exc_info.value.status_code == 502
    # No streamGenerateContent verb-retry was attempted for a 5xx.
    assert not any("streamGenerateContent" in u for u in calls)
