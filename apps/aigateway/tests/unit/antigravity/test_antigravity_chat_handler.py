"""Unit 4 — Antigravity chat transport (generateContent-first, MockTransport).

Covers the Antigravity Code Assist body shape (U14: userAgent/requestId, NOT
gemini's user_prompt_id/session_id; systemInstruction as an object-with-parts;
role="model"), the two-layer caller-auth header strip (U4: superset
CLIENT_AUTH_HEADER_NAMES, gateway headers set LAST, negative-by-value scan),
the daily→prod host fallback (U12), per-credential session caching + invalidate,
and pre-stream error mapping (U6: 401/403/429/5xx, NO in-band 429).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from litellm.llms.custom_llm import CustomLLMError
from litellm.types.utils import ModelResponse

from aigateway.plugins.antigravity_provider.auth import ANTIGRAVITY_PROFILE_HEADER
from aigateway.plugins.antigravity_provider.chat_handler import (
    CLIENT_AUTH_HEADER_NAMES,
    AntigravityCustomLLM,
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
        "model": "antigravity/gemini-3.5-flash",
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
        {"response": _antigravity_response("hello")}, "antigravity/gemini-3.5-flash"
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
    body = calls[1]["payload"]
    # Antigravity outer body (U14): userAgent + requestId, NOT user_prompt_id/session_id.
    assert body["project"] == "project-123"
    assert body["model"] == "gemini-3.5-flash"
    assert "userAgent" in body
    assert "requestId" in body
    assert "user_prompt_id" not in body
    assert "session_id" not in body.get("request", {})
    assert body["request"]["contents"] == [{"role": "user", "parts": [{"text": "ping"}]}]
    assert response.choices[0].message.content == "hi there"


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
