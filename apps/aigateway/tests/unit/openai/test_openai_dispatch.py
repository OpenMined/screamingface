"""No-network characterization of direct OpenAI's final outbound request."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx
import litellm
import pytest
from fastapi import HTTPException
from openai import AsyncOpenAI

from aigateway.core.retry import is_retryable_status
from aigateway.plugins.openai_provider import plugin as plugin_module
from aigateway.plugins.openai_provider.plugin import PLUGIN

_SELECTED_KEY = "sk-synthetic-selected-account-key"


class _FalseyProxyAuth:
    def __bool__(self) -> bool:
        return False


def _completion_response(model: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "ok"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


def _capture_client_factory(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[list[AsyncOpenAI], list[dict[str, Any]], httpx.AsyncClient]:
    clients: list[AsyncOpenAI] = []
    constructor_kwargs: list[dict[str, Any]] = []
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        trust_env=False,
        follow_redirects=False,
    )

    def factory(**kwargs: Any) -> AsyncOpenAI:
        constructor_kwargs.append(dict(kwargs))
        client = AsyncOpenAI(**kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(plugin_module, "_openai_http_client", lambda: http_client)
    monkeypatch.setattr(plugin_module, "AsyncOpenAI", factory)
    return clients, constructor_kwargs, http_client


@pytest.mark.parametrize(
    ("model", "expected_token_field"),
    [
        ("openai/gpt-4o", "max_tokens"),
        ("openai/gpt-5.6", "max_completion_tokens"),
    ],
)
@pytest.mark.asyncio
async def test_dispatch_pins_chat_completions_and_selected_account_context(
    monkeypatch: pytest.MonkeyPatch,
    model: str,
    expected_token_field: str,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_completion_response(model.split("/", 1)[1]))

    clients, constructor_kwargs, http_client = _capture_client_factory(monkeypatch, handler)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-ambient-wrong-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://ambient.invalid/v1")
    monkeypatch.setenv("OPENAI_ORGANIZATION", "org-ambient")
    monkeypatch.setenv("OPENAI_ORG_ID", "org-ambient-fallback")
    monkeypatch.setenv("OPENAI_PROJECT_ID", "proj-ambient")
    monkeypatch.delenv("OPENAI_CUSTOM_HEADERS", raising=False)
    monkeypatch.setattr(litellm, "api_key", "sk-litellm-wrong-key")
    monkeypatch.setattr(litellm, "openai_key", "sk-litellm-openai-wrong-key")
    monkeypatch.setattr(litellm, "api_base", "https://litellm.invalid/v1")
    monkeypatch.setattr(litellm, "headers", None)
    monkeypatch.setattr(litellm, "route_all_chat_openai_to_responses", True)

    body = PLUGIN.prepare_chat_body(
        {
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 7,
        }
    )
    body["api_key"] = _SELECTED_KEY

    result = await PLUGIN.chat_completion(body)
    # LiteLLM schedules best-effort success logging; let its queue drain before
    # pytest closes this parametrized case's event loop.
    await asyncio.sleep(0.05)

    assert result["choices"][0]["message"]["content"] == "ok"
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://api.openai.com/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {_SELECTED_KEY}"
    assert "openai-organization" not in request.headers
    assert "openai-project" not in request.headers
    assert "x-ambient" not in request.headers
    payload = json.loads(request.content)
    assert payload["model"] == model.split("/", 1)[1]
    assert payload[expected_token_field] == 7
    assert ({"max_tokens", "max_completion_tokens"} - {expected_token_field}).isdisjoint(payload)
    assert _SELECTED_KEY not in request.content.decode()
    assert constructor_kwargs[0]["api_key"] == _SELECTED_KEY
    assert constructor_kwargs[0]["base_url"] == "https://api.openai.com/v1"
    assert constructor_kwargs[0]["max_retries"] == 0
    assert constructor_kwargs[0]["http_client"] is http_client
    assert clients[0].is_closed() is True


def test_prepare_chat_body_keeps_only_gateway_owned_origin() -> None:
    prepared = PLUGIN.prepare_chat_body(
        {
            "model": "openai/gpt-5.6",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 7,
            "api_key": "caller-key",
            "api_base": "https://caller.invalid/v1",
            "base_url": "https://caller.invalid/v1",
            "headers": {"Authorization": "caller"},
            "extra_headers": {"X-Custom": "caller"},
            "fallbacks": ["attacker/model"],
            "model_list": [{"model_name": "attacker/model"}],
            "callbacks": ["caller"],
            "success_callback": ["caller"],
            "failure_callback": ["caller"],
            "custom_llm_provider": "attacker",
            "azure": True,
            "text_completion": True,
        }
    )

    assert prepared == {
        "model": "openai/gpt-5.6",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 7,
        "api_base": "https://api.openai.com/v1",
    }


def test_prepare_chat_body_rejects_unregistered_model() -> None:
    with pytest.raises(HTTPException) as raised:
        PLUGIN.prepare_chat_body({"model": "openai/unregistered", "messages": []})

    assert raised.value.status_code == 400
    assert raised.value.detail == {
        "code": "invalid_model",
        "provider": "openai",
        "message": "model is not registered for direct OpenAI dispatch",
    }


@pytest.mark.asyncio
async def test_nonempty_ambient_custom_headers_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_CUSTOM_HEADERS", '{"X-Leak":"ambient"}')

    with pytest.raises(HTTPException) as raised:
        await PLUGIN.chat_completion(
            {
                "model": "openai/gpt-5.6",
                "messages": [],
                "api_key": _SELECTED_KEY,
                "api_base": "https://api.openai.com/v1",
            }
        )

    assert raised.value.status_code == 503
    assert raised.value.detail == {
        "code": "unsafe_openai_environment",
        "provider": "openai",
        "message": "direct OpenAI dispatch is unavailable",
    }
    assert "X-Leak" not in repr(raised.value.detail)


@pytest.mark.asyncio
async def test_process_global_litellm_headers_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_CUSTOM_HEADERS", raising=False)
    monkeypatch.setattr(litellm, "headers", {"X-Leak": "ambient"})

    with pytest.raises(HTTPException) as raised:
        await PLUGIN.chat_completion(
            {
                "model": "openai/gpt-5.6",
                "messages": [],
                "api_key": _SELECTED_KEY,
                "api_base": "https://api.openai.com/v1",
            }
        )

    assert raised.value.status_code == 503
    assert raised.value.detail == {
        "code": "unsafe_openai_environment",
        "provider": "openai",
        "message": "direct OpenAI dispatch is unavailable",
    }
    assert "X-Leak" not in repr(raised.value.detail)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model_fallbacks", ["openai/gpt-4o-mini"]),
        ("callbacks", [object()]),
        ("pre_call_rules", [object()]),
        ("model_alias_map", {"openai/gpt-5.6": "openai/gpt-4o"}),
        ("proxy_auth", _FalseyProxyAuth()),
        ("drop_params", True),
    ],
)
@pytest.mark.asyncio
async def test_process_global_routing_or_observation_state_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: Any,
) -> None:
    monkeypatch.delenv("OPENAI_CUSTOM_HEADERS", raising=False)
    monkeypatch.setattr(litellm, "headers", None)
    monkeypatch.setattr(litellm, field, value)

    def forbidden_client(**_kwargs: Any) -> AsyncOpenAI:
        raise AssertionError("unsafe global state reached client construction")

    monkeypatch.setattr(plugin_module, "AsyncOpenAI", forbidden_client)

    with pytest.raises(HTTPException) as raised:
        await PLUGIN.chat_completion(
            {
                "model": "openai/gpt-5.6",
                "messages": [],
                "api_key": _SELECTED_KEY,
                "api_base": "https://api.openai.com/v1",
            }
        )

    assert raised.value.status_code == 503
    assert raised.value.detail == {
        "code": "unsafe_openai_environment",
        "provider": "openai",
        "message": "direct OpenAI dispatch is unavailable",
    }
    assert is_retryable_status(raised.value) is False


@pytest.mark.asyncio
async def test_missing_selected_key_fails_before_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_CUSTOM_HEADERS", raising=False)
    monkeypatch.setattr(litellm, "headers", None)

    with pytest.raises(HTTPException) as raised:
        await PLUGIN.chat_completion(
            {
                "model": "openai/gpt-5.6",
                "messages": [],
                "api_base": "https://api.openai.com/v1",
            }
        )

    assert raised.value.status_code == 503
    assert raised.value.detail == {
        "code": "unsafe_openai_environment",
        "provider": "openai",
        "message": "direct OpenAI dispatch is unavailable",
    }


def test_every_seed_is_chat_mode_in_the_locked_runtime() -> None:
    for entry in PLUGIN.register_models():
        upstream_model = entry.model_name.split("/", 1)[1]
        assert litellm.get_model_info(upstream_model)["mode"] == "chat", entry.model_name
