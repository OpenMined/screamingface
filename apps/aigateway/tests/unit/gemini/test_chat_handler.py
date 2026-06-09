from __future__ import annotations

import json
from typing import Any

import httpx
import litellm
import pytest
from litellm.llms.custom_llm import CustomLLMError
from litellm.types.utils import ModelResponse

from aigateway.plugins.gemini_provider.auth import GEMINI_PROFILE_HEADER
from aigateway.plugins.gemini_provider.chat_handler import (
    CODE_ASSIST_API_VERSION,
    CODE_ASSIST_ENDPOINT,
    GEMINI_API_BASE,
    GeminiCustomLLM,
    ensure_litellm_gemini_provider_registered,
    parse_gemini_retry_after,
)


def test_parse_gemini_retry_after_from_reset_after_text() -> None:
    body = (
        '{"error": {"code": 429, "message": "You have exhausted your capacity '
        'on this model. Your quota will reset after 3s.", "status": "RESOURCE_EXHAUSTED"}}'
    )
    assert parse_gemini_retry_after(body, {}) == 3.0


def test_parse_gemini_retry_after_from_retry_delay_field() -> None:
    body = '{"error": {"details": [{"@type": "...RetryInfo", "retryDelay": "5s"}]}}'
    assert parse_gemini_retry_after(body, {}) == 5.0


def test_parse_gemini_retry_after_prefers_header() -> None:
    assert parse_gemini_retry_after("reset after 9s", {"retry-after": "2"}) == 2.0


def test_parse_gemini_retry_after_none_when_absent() -> None:
    assert parse_gemini_retry_after('{"error": {"code": 429}}', {}) is None


def test_parse_gemini_retry_after_compound_daily_quota() -> None:
    """Daily-quota exhaustion reports a compound 'XhYmZs' window, not 'Ns'.
    Regression for the observed live form 'reset after 22h11m3s'."""
    body = (
        '{"error": {"code": 429, "message": "You have exhausted your capacity. '
        'Your quota will reset after 22h11m3s.", "status": "RESOURCE_EXHAUSTED"}}'
    )
    assert parse_gemini_retry_after(body, {}) == 22 * 3600 + 11 * 60 + 3


def test_parse_gemini_retry_after_compound_minutes_seconds() -> None:
    assert parse_gemini_retry_after("quota will reset after 1m30s.", {}) == 90.0


def test_parse_gemini_retry_after_plain_seconds_still_works() -> None:
    assert parse_gemini_retry_after("reset after 8s.", {}) == 8.0


def _http_factory(transport: httpx.MockTransport):
    def factory():
        return httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(5.0))

    return factory


def _gemini_response(text: str = "pong") -> dict[str, Any]:
    return {
        "candidates": [
            {
                "content": {"parts": [{"text": text}], "role": "model"},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 3,
            "candidatesTokenCount": 2,
            "totalTokenCount": 5,
        },
    }


async def _complete(custom: GeminiCustomLLM, **kwargs: Any):
    defaults: dict[str, Any] = {
        "model": "gemini-cli/gemini-2.5-flash",
        "messages": [{"role": "user", "content": "ping"}],
        "api_base": None,
        "custom_prompt_dict": {},
        "model_response": ModelResponse(),
        "print_verbose": lambda *_args, **_kwargs: None,
        "encoding": None,
        "api_key": None,
        "logging_obj": None,
        "optional_params": {},
    }
    defaults.update(kwargs)
    return await custom.acompletion(**defaults)


@pytest.mark.asyncio
async def test_api_key_path_posts_to_public_gemini_api(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content.decode())
        return httpx.Response(200, json=_gemini_response("from api key"))

    custom = GeminiCustomLLM(http_client_factory=_http_factory(httpx.MockTransport(handler)))

    response = await _complete(
        custom,
        messages=[
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "ping"},
        ],
        optional_params={"max_tokens": 5, "temperature": 0.2},
    )

    assert captured["url"] == f"{GEMINI_API_BASE}/models/gemini-2.5-flash:generateContent"
    assert captured["headers"]["x-goog-api-key"] == "env-key"
    assert "authorization" not in captured["headers"]
    assert captured["payload"]["systemInstruction"] == {"parts": [{"text": "be terse"}]}
    assert captured["payload"]["generationConfig"] == {
        "maxOutputTokens": 5,
        "temperature": 0.2,
    }
    assert response.choices[0].message.content == "from api key"
    assert response.model_dump()["usage"]["total_tokens"] == 5


@pytest.mark.asyncio
async def test_oauth_path_uses_code_assist_setup_and_wrapped_generate_content(
    monkeypatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(
            {
                "url": str(request.url),
                "headers": dict(request.headers),
                "payload": json.loads(request.content.decode()),
            }
        )
        if str(request.url).endswith(f"/{CODE_ASSIST_API_VERSION}:loadCodeAssist"):
            return httpx.Response(200, json={"cloudaicompanionProject": "project-123"})
        return httpx.Response(
            200, json={"response": _gemini_response("from oauth"), "traceId": "t1"}
        )

    custom = GeminiCustomLLM(http_client_factory=_http_factory(httpx.MockTransport(handler)))

    response = await _complete(
        custom,
        api_key="ya29.oauth",
        headers={GEMINI_PROFILE_HEADER: "acct:default", "User-Agent": "GeminiCLI/test"},
        optional_params={"max_tokens": 7},
    )

    assert len(calls) == 2
    assert calls[0]["url"] == f"{CODE_ASSIST_ENDPOINT}/{CODE_ASSIST_API_VERSION}:loadCodeAssist"
    assert calls[0]["headers"]["authorization"] == "Bearer ya29.oauth"
    assert calls[0]["headers"]["user-agent"] == "GeminiCLI/test"
    assert calls[0]["payload"]["metadata"]["pluginType"] == "GEMINI"
    assert calls[1]["url"] == f"{CODE_ASSIST_ENDPOINT}/{CODE_ASSIST_API_VERSION}:generateContent"
    assert calls[1]["headers"]["authorization"] == "Bearer ya29.oauth"
    assert "x-goog-api-key" not in calls[1]["headers"]
    assert GEMINI_PROFILE_HEADER.lower() not in calls[1]["headers"]
    body = calls[1]["payload"]
    assert body["model"] == "gemini-2.5-flash"
    assert body["project"] == "project-123"
    assert "user_prompt_id" in body
    assert body["request"]["session_id"]
    assert body["request"]["contents"] == [{"role": "user", "parts": [{"text": "ping"}]}]
    assert body["request"]["generationConfig"] == {"maxOutputTokens": 7}
    assert response.choices[0].message.content == "from oauth"


@pytest.mark.asyncio
async def test_oauth_path_drops_caller_supplied_auth_headers(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    calls: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append({"url": str(request.url), "headers": dict(request.headers)})
        if str(request.url).endswith(f"/{CODE_ASSIST_API_VERSION}:loadCodeAssist"):
            return httpx.Response(200, json={"cloudaicompanionProject": "project-123"})
        return httpx.Response(200, json={"response": _gemini_response("safe")})

    custom = GeminiCustomLLM(http_client_factory=_http_factory(httpx.MockTransport(handler)))

    await _complete(
        custom,
        api_key="ya29.oauth",
        headers={
            GEMINI_PROFILE_HEADER: "acct:default",
            "authorization": "Bearer attacker",
            "x-goog-api-key": "bad-key",
            "x-goog-user-project": "attacker-project",
            "content-type": "text/plain",
            "X-Request-Trace": "ok",
        },
    )

    for call in calls:
        assert call["headers"]["authorization"] == "Bearer ya29.oauth"
        assert call["headers"]["content-type"] == "application/json"
        assert "x-goog-api-key" not in call["headers"]
        assert "x-goog-user-project" not in call["headers"]
        assert call["headers"]["x-request-trace"] == "ok"


@pytest.mark.asyncio
async def test_oauth_setup_is_cached_per_profile(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        if str(request.url).endswith(f"/{CODE_ASSIST_API_VERSION}:loadCodeAssist"):
            return httpx.Response(200, json={"cloudaicompanionProject": "project-123"})
        return httpx.Response(200, json={"response": _gemini_response()})

    custom = GeminiCustomLLM(http_client_factory=_http_factory(httpx.MockTransport(handler)))

    await _complete(custom, api_key="ya29.oauth", headers={GEMINI_PROFILE_HEADER: "acct:default"})
    await _complete(custom, api_key="ya29.oauth", headers={GEMINI_PROFILE_HEADER: "acct:default"})

    assert sum(url.endswith(f"/{CODE_ASSIST_API_VERSION}:loadCodeAssist") for url in urls) == 1
    assert sum(url.endswith(f"/{CODE_ASSIST_API_VERSION}:generateContent") for url in urls) == 2


@pytest.mark.asyncio
async def test_invalidate_session_forces_new_load_code_assist(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    load_projects = ["project-one", "project-two"]
    generated_projects: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if str(request.url).endswith(f"/{CODE_ASSIST_API_VERSION}:loadCodeAssist"):
            return httpx.Response(200, json={"cloudaicompanionProject": load_projects.pop(0)})
        generated_projects.append(payload["project"])
        return httpx.Response(200, json={"response": _gemini_response()})

    custom = GeminiCustomLLM(http_client_factory=_http_factory(httpx.MockTransport(handler)))

    await _complete(custom, api_key="ya29.oauth", headers={GEMINI_PROFILE_HEADER: "acct:default"})
    custom.invalidate_session("acct:default")
    await _complete(custom, api_key="ya29.oauth", headers={GEMINI_PROFILE_HEADER: "acct:default"})

    assert generated_projects == ["project-one", "project-two"]
    assert load_projects == []


@pytest.mark.asyncio
async def test_handler_requires_oauth_or_env_key(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    called = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json=_gemini_response())

    custom = GeminiCustomLLM(http_client_factory=_http_factory(httpx.MockTransport(handler)))

    with pytest.raises(CustomLLMError) as exc_info:
        await _complete(custom)

    assert exc_info.value.status_code == 401
    assert called is False


@pytest.mark.asyncio
async def test_profile_header_key_posts_to_public_gemini_api(monkeypatch) -> None:
    """A gateway-injected x-goog-api-key (per-profile ApiKeyStrategy) selects
    the public generativelanguage API path, same as the env-var fallback."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json=_gemini_response("from profile key"))

    custom = GeminiCustomLLM(http_client_factory=_http_factory(httpx.MockTransport(handler)))

    response = await _complete(custom, headers={"x-goog-api-key": "profile-key"})

    assert captured["url"] == f"{GEMINI_API_BASE}/models/gemini-2.5-flash:generateContent"
    assert captured["headers"]["x-goog-api-key"] == "profile-key"
    assert "authorization" not in captured["headers"]
    assert response.choices[0].message.content == "from profile key"


@pytest.mark.asyncio
async def test_profile_header_key_takes_precedence_over_env_key(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json=_gemini_response())

    custom = GeminiCustomLLM(http_client_factory=_http_factory(httpx.MockTransport(handler)))

    await _complete(custom, headers={"x-goog-api-key": "profile-key"})

    assert captured["headers"]["x-goog-api-key"] == "profile-key"


@pytest.mark.asyncio
async def test_oauth_token_takes_precedence_over_profile_header_key(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        if request.url.path.endswith(":loadCodeAssist"):
            return httpx.Response(200, json={"cloudaicompanionProject": "proj-1"})
        return httpx.Response(200, json=_gemini_response())

    custom = GeminiCustomLLM(http_client_factory=_http_factory(httpx.MockTransport(handler)))

    await _complete(custom, api_key="oauth-tok", headers={"x-goog-api-key": "profile-key"})

    assert all(url.startswith(CODE_ASSIST_ENDPOINT) for url in urls)


def test_gemini_registration_is_idempotent(monkeypatch) -> None:
    monkeypatch.setattr(litellm, "custom_provider_map", [])
    monkeypatch.setattr(litellm, "_custom_providers", [])
    monkeypatch.setattr(litellm, "provider_list", list(litellm.provider_list))
    handler = GeminiCustomLLM()

    ensure_litellm_gemini_provider_registered(handler)
    ensure_litellm_gemini_provider_registered(handler)

    entries = [entry for entry in litellm.custom_provider_map if entry["provider"] == "gemini-cli"]
    assert entries == [{"provider": "gemini-cli", "custom_handler": handler}]
    assert "gemini-cli" in litellm._custom_providers
    assert "gemini-cli" in litellm.provider_list
