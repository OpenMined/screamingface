from __future__ import annotations

import json
from typing import Any, cast

import httpx
import litellm
import pytest
from litellm.llms.custom_llm import CustomLLMError
from litellm.types.utils import ModelResponse

from aigateway.plugins.codex_provider.chat_handler import (
    CODEX_RESPONSES_URL,
    CodexCustomLLM,
    _model_response_from_sse,
    ensure_litellm_codex_provider_registered,
)


def _http_factory(transport: httpx.MockTransport):
    def factory():
        return httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(5.0))

    return factory


def _completed_sse(text: str = "hello") -> str:
    payload = {
        "type": "response.completed",
        "response": {
            "id": "resp_1",
            "created_at": 123,
            "model": "gpt-5.4-mini",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": text}],
                }
            ],
            "usage": {"input_tokens": 3, "output_tokens": 2},
        },
    }
    return f"event: response.completed\ndata: {json.dumps(payload)}\n\ndata: [DONE]\n\n"


def _empty_completed_sse() -> str:
    payload = {
        "type": "response.completed",
        "response": {
            "id": "resp_1",
            "created_at": 123,
            "model": "gpt-5.4-mini",
            "output": [],
            "usage": {"input_tokens": 3, "output_tokens": 2},
        },
    }
    return f"event: response.completed\ndata: {json.dumps(payload)}\n\ndata: [DONE]\n\n"


def _sse_event(payload: dict[str, Any]) -> str:
    return f"event: {payload['type']}\ndata: {json.dumps(payload)}\n\n"


def test_build_payload_uses_default_instructions_when_no_system_message() -> None:
    from aigateway.plugins.codex_provider.chat_handler import _build_payload

    payload = _build_payload(
        "codex/gpt-5.4-mini",
        [{"role": "user", "content": "hi"}],
        {},
    )

    assert payload["instructions"] == "You are a helpful assistant."


def test_model_response_uses_output_text_deltas_when_completed_output_empty() -> None:
    body = "".join(
        [
            _sse_event({"type": "response.output_text.delta", "delta": "Hello"}),
            _sse_event({"type": "response.output_text.delta", "delta": "!"}),
            _empty_completed_sse(),
        ]
    )

    response = _model_response_from_sse(body, "gpt-5.4-mini")

    assert response.choices[0].message.content == "Hello!"


def test_model_response_uses_output_item_done_when_completed_output_empty() -> None:
    body = "".join(
        [
            _sse_event(
                {
                    "type": "response.output_item.done",
                    "item": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "Hello!"}],
                    },
                }
            ),
            _empty_completed_sse(),
        ]
    )

    response = _model_response_from_sse(body, "gpt-5.4-mini")

    assert response.choices[0].message.content == "Hello!"


class _InjectedClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        self.calls.append({"url": url, **kwargs})
        return httpx.Response(
            200,
            text=_completed_sse("from injected client"),
            headers={"content-type": "text/event-stream"},
        )


class _StreamingOnlyResponse:
    status_code = 200

    @property
    def text(self) -> str:
        raise AssertionError("streaming parser must not buffer response.text")

    async def aiter_lines(self):
        for line in _completed_sse("streamed only").splitlines():
            yield line

    async def aclose(self) -> None:
        return None


class _StreamingOnlyClient:
    def __init__(self) -> None:
        self.stream_requested = False

    async def post(self, url: str, **kwargs: Any) -> _StreamingOnlyResponse:  # noqa: ARG002
        self.stream_requested = kwargs.get("stream") is True
        return _StreamingOnlyResponse()


@pytest.mark.asyncio
async def test_codex_handler_posts_sse_request_and_returns_model_response() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            text=_completed_sse("hello from codex"),
            headers={"content-type": "text/event-stream"},
        )

    custom = CodexCustomLLM(http_client_factory=_http_factory(httpx.MockTransport(handler)))

    response = await custom.acompletion(
        model="codex/gpt-5.4-mini",
        messages=[
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "hi"},
        ],
        api_base=None,
        custom_prompt_dict={},
        model_response=ModelResponse(),
        print_verbose=lambda *_args, **_kwargs: None,
        encoding=None,
        api_key="oauth-token",
        logging_obj=None,
        optional_params={
            "max_tokens": 123,
            "temperature": 0.2,
            "reasoning": {"effort": "medium"},
            "include": ["custom.include"],
        },
        headers={"ChatGPT-Account-Id": "acct-1"},
    )

    assert captured["url"] == CODEX_RESPONSES_URL
    assert captured["headers"]["authorization"] == "Bearer oauth-token"
    assert captured["headers"]["chatgpt-account-id"] == "acct-1"
    assert captured["payload"] == {
        "model": "gpt-5.4-mini",
        "input": [{"role": "user", "content": "hi"}],
        "instructions": "be terse",
        "stream": True,
        "store": False,
        "include": ["reasoning.encrypted_content", "custom.include"],
        "reasoning": {"effort": "medium"},
    }
    assert response.model == "gpt-5.4-mini"
    assert response.choices[0].message.content == "hello from codex"
    usage = response.model_dump()["usage"]
    assert usage["prompt_tokens"] == 3
    assert usage["completion_tokens"] == 2


@pytest.mark.asyncio
async def test_codex_handler_ignores_api_base_override() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, text=_completed_sse())

    custom = CodexCustomLLM(http_client_factory=_http_factory(httpx.MockTransport(handler)))

    await custom.acompletion(
        model="codex/gpt-5.4-mini",
        messages=[{"role": "user", "content": "hi"}],
        api_base="https://attacker.example.test/collect",
        custom_prompt_dict={},
        model_response=ModelResponse(),
        print_verbose=lambda *_args, **_kwargs: None,
        encoding=None,
        api_key="oauth-token",
        logging_obj=None,
        optional_params={},
    )

    assert captured["url"] == CODEX_RESPONSES_URL


@pytest.mark.asyncio
async def test_codex_handler_rejects_api_key_fallback_before_network() -> None:
    called = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, text=_completed_sse())

    custom = CodexCustomLLM(http_client_factory=_http_factory(httpx.MockTransport(handler)))

    with pytest.raises(CustomLLMError) as exc_info:
        await custom.acompletion(
            model="codex/gpt-5.4-mini",
            messages=[{"role": "user", "content": "hi"}],
            api_base=None,
            custom_prompt_dict={},
            model_response=ModelResponse(),
            print_verbose=lambda *_args, **_kwargs: None,
            encoding=None,
            api_key="sk-proj-test",
            logging_obj=None,
            optional_params={},
        )

    assert exc_info.value.status_code == 400
    assert called is False


def test_codex_registration_is_idempotent(monkeypatch) -> None:
    monkeypatch.setattr(litellm, "custom_provider_map", [])
    monkeypatch.setattr(litellm, "_custom_providers", [])
    monkeypatch.setattr(litellm, "provider_list", list(litellm.provider_list))
    handler = CodexCustomLLM()

    ensure_litellm_codex_provider_registered(handler)
    ensure_litellm_codex_provider_registered(handler)

    entries = [entry for entry in litellm.custom_provider_map if entry["provider"] == "codex"]
    assert entries == [{"provider": "codex", "custom_handler": handler}]
    assert "codex" in litellm._custom_providers
    assert "codex" in litellm.provider_list


@pytest.mark.asyncio
async def test_codex_handler_uses_injected_litellm_client() -> None:
    injected = _InjectedClient()

    def unused_factory():
        raise AssertionError("http_client_factory should not be used when LiteLLM injects client")

    custom = CodexCustomLLM(http_client_factory=unused_factory)

    response = await custom.acompletion(
        model="codex/gpt-5.4-mini",
        messages=[{"role": "user", "content": "hi"}],
        api_base=None,
        custom_prompt_dict={},
        model_response=ModelResponse(),
        print_verbose=lambda *_args, **_kwargs: None,
        encoding=None,
        api_key="oauth-token",
        logging_obj=None,
        optional_params={},
        client=cast(Any, injected),
    )

    assert response.choices[0].message.content == "from injected client"
    assert injected.calls[0]["url"] == CODEX_RESPONSES_URL
    assert injected.calls[0]["stream"] is True


@pytest.mark.asyncio
async def test_codex_handler_parses_sse_without_buffering_response_text() -> None:
    injected = _StreamingOnlyClient()
    custom = CodexCustomLLM(http_client_factory=lambda: None)

    response = await custom.acompletion(
        model="codex/gpt-5.4-mini",
        messages=[{"role": "user", "content": "hi"}],
        api_base=None,
        custom_prompt_dict={},
        model_response=ModelResponse(),
        print_verbose=lambda *_args, **_kwargs: None,
        encoding=None,
        api_key="oauth-token",
        logging_obj=None,
        optional_params={},
        client=cast(Any, injected),
    )

    assert injected.stream_requested is True
    assert response.choices[0].message.content == "streamed only"
