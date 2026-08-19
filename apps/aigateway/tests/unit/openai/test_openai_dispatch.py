"""No-network characterization of direct OpenAI's final outbound request."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Iterator, Mapping
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
        ("openai/gpt-5.6-sol", "max_completion_tokens"),
        ("openai/gpt-5.6-terra", "max_completion_tokens"),
        ("openai/gpt-5.6-luna", "max_completion_tokens"),
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
    assert "ssl_verify" not in payload
    assert _SELECTED_KEY not in request.content.decode()
    assert constructor_kwargs[0]["api_key"] == _SELECTED_KEY
    assert constructor_kwargs[0]["base_url"] == "https://api.openai.com/v1"
    assert constructor_kwargs[0]["max_retries"] == 0
    assert constructor_kwargs[0]["http_client"] is http_client
    assert clients[0].is_closed() is True


def test_prepare_chat_body_keeps_only_gateway_owned_origin() -> None:
    prepared = PLUGIN.prepare_chat_body(
        {
            "model": "openai/gpt-5.6-sol",
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
        "model": "openai/gpt-5.6-sol",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 7,
        "api_base": "https://api.openai.com/v1",
    }


def test_prepare_chat_body_forwards_any_route_valid_model_and_refuses_malformed_ids() -> None:
    """OME-884 (authorized contract change): the catalog publishes, it does not admit.

    OME-864 refused any model absent from ``default_models`` here. That made the
    bootstrap ``/v1/models`` listing a dispatch allowlist, so a model OpenAI serves
    could not be addressed directly, and unpublishing one silently revoked dispatch.
    Preparation now validates the model ID's GRAMMAR — the same predicate the
    global-cache projection uses, so the two can never disagree about which requests
    are forwardable — and OpenAI remains the authority on whether the model exists and
    whether the caller's key may use it.
    """
    unlisted = "openai/gpt-4o-2024-11-20"
    assert unlisted not in PLUGIN.settings.default_models

    prepared = PLUGIN.prepare_chat_body({"model": unlisted, "messages": []})

    assert prepared == {
        "model": unlisted,
        "messages": [],
        "api_base": "https://api.openai.com/v1",
    }

    for malformed in ("openai/", "openai/gpt 5", "openai/gpt/5", "openrouter/openai/gpt-4o"):
        with pytest.raises(HTTPException) as raised:
            PLUGIN.prepare_chat_body({"model": malformed, "messages": []})
        assert raised.value.status_code == 400, malformed
        assert raised.value.detail == {
            "code": "invalid_model",
            "provider": "openai",
            "message": "model is not a valid direct OpenAI model id",
        }


@pytest.mark.asyncio
async def test_nonempty_ambient_custom_headers_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_CUSTOM_HEADERS", '{"X-Leak":"ambient"}')

    with pytest.raises(HTTPException) as raised:
        await PLUGIN.chat_completion(
            {
                "model": "openai/gpt-5.6-sol",
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
                "model": "openai/gpt-5.6-sol",
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
        ("model_alias_map", {"openai/gpt-5.6-sol": "openai/gpt-4o"}),
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
                "model": "openai/gpt-5.6-sol",
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
                "model": "openai/gpt-5.6-sol",
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


# --- OME-884: the runtime states that must ALSO stop a cache read --------------
#
# WHY these are dispatch tests as well as participation tests: the two verdicts come
# from ONE shared predicate on purpose. A state that only stopped dispatch would leave
# the cache serving rows from a runtime the gateway refuses to dispatch into; a state
# that only stopped participation would let the poisoned runtime answer live requests.


@pytest.mark.parametrize(
    "poison",
    [
        pytest.param(
            lambda mp: mp.setattr(litellm.OpenAIConfig, "temperature", 1),
            id="openai_config",
        ),
        pytest.param(
            lambda mp: mp.setenv("EXPERIMENTAL_OPENAI_BASE_LLM_HTTP_HANDLER", "true"),
            id="experimental_handler",
        ),
        pytest.param(
            lambda mp: mp.setattr(litellm, "secret_manager_client", object()),
            id="secret_manager",
        ),
    ],
)
@pytest.mark.asyncio
async def test_ambient_openai_configuration_and_transport_swaps_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    poison: Callable[[pytest.MonkeyPatch], None],
) -> None:
    """Three states OME-864 did not cover, each of which silently changes the call.

    * ``litellm.OpenAIConfig`` entries are merged into ``optional_params`` for EVERY
      OpenAI completion, so an operator-set temperature changes the answer while the
      cache key cannot see it.
    * ``EXPERIMENTAL_OPENAI_BASE_LLM_HTTP_HANDLER`` swaps the dispatch handler, so the
      client construction, retry and TLS guarantees this plugin's adapter revision pins
      are no longer the ones in force.
    * a configured secret-manager client resolves values — including the flag above —
      from outside this process, so no environment read here is authoritative any more.
    """
    monkeypatch.delenv("OPENAI_CUSTOM_HEADERS", raising=False)
    monkeypatch.delenv("EXPERIMENTAL_OPENAI_BASE_LLM_HTTP_HANDLER", raising=False)
    monkeypatch.setattr(litellm, "secret_manager_client", None)
    monkeypatch.setattr(litellm, "headers", None)
    poison(monkeypatch)

    def forbidden_client(**_kwargs: Any) -> AsyncOpenAI:
        raise AssertionError("unsafe ambient state reached client construction")

    monkeypatch.setattr(plugin_module, "AsyncOpenAI", forbidden_client)

    with pytest.raises(HTTPException) as raised:
        await PLUGIN.chat_completion(
            {
                "model": "openai/gpt-5.6-sol",
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
async def test_an_alias_for_another_model_leaves_this_one_dispatchable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The alias refusal is per-MODEL, and this is the half that proves it is not global.

    ``test_process_global_routing_or_observation_state_fails_closed`` already pins that
    an alias FOR the requested model refuses. Without this companion, a guard that
    disabled the provider outright whenever ANY alias existed would pass that test —
    and would abandon every unrelated model's cache over one poisoned entry.
    """
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_completion_response("gpt-5.6-sol"))

    _capture_client_factory(monkeypatch, handler)
    monkeypatch.delenv("OPENAI_CUSTOM_HEADERS", raising=False)
    monkeypatch.setattr(litellm, "headers", None)
    monkeypatch.setattr(litellm, "model_alias_map", {"openai/gpt-4o": "openai/gpt-4o-mini"})

    body = PLUGIN.prepare_chat_body(
        {"model": "openai/gpt-5.6-sol", "messages": [{"role": "user", "content": "ping"}]}
    )
    body["api_key"] = _SELECTED_KEY

    result = await PLUGIN.chat_completion(body)
    await asyncio.sleep(0.05)

    assert result["choices"][0]["message"]["content"] == "ok"
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_dispatch_sends_exactly_the_controls_the_cache_key_projects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The coupling that makes "the key describes what dispatch sends" checkable.

    INVARIANT: ``gateway_dispatch_controls()`` has exactly two readers — the projection
    and ``chat_completion``. This asserts the second one actually applies the table, so
    a control added to the wire cannot quietly stay out of the key.

    Captured at the ``litellm.acompletion`` boundary rather than at the HTTP wire on
    purpose: these are LiteLLM CONTROLS, most of which never appear as payload fields.
    The final wire is a separate observation layer with its own tests.
    """
    captured: list[dict[str, Any]] = []
    real_acompletion = litellm.acompletion

    async def capturing(**kwargs: Any) -> Any:
        captured.append(dict(kwargs))
        return await real_acompletion(**kwargs)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion_response("gpt-5.6-sol"))

    _capture_client_factory(monkeypatch, handler)
    monkeypatch.delenv("OPENAI_CUSTOM_HEADERS", raising=False)
    monkeypatch.setattr(litellm, "headers", None)
    monkeypatch.setattr(litellm, "acompletion", capturing)

    body = PLUGIN.prepare_chat_body(
        {"model": "openai/gpt-5.6-sol", "messages": [{"role": "user", "content": "ping"}]}
    )
    body["api_key"] = _SELECTED_KEY
    await PLUGIN.chat_completion(body)
    await asyncio.sleep(0.05)

    projected = PLUGIN.global_cache_projection(
        {"model": "openai/gpt-5.6-sol", "messages": [{"role": "user", "content": "ping"}]}
    )
    assert isinstance(projected, dict)
    prepared = projected["prepared"]
    assert len(captured) == 1
    for field, value in prepared.items():
        assert captured[0][field] == value, field
    # The caller's key is NOT among them: it is transport, injected into the client and
    # deliberately absent from both the projected controls and the acompletion kwargs.
    assert "api_key" not in captured[0]
    assert "api_key" not in prepared


@pytest.mark.parametrize("model", [entry.model_name for entry in PLUGIN.register_models()])
@pytest.mark.asyncio
async def test_every_default_model_pins_its_token_field_at_the_final_http_wire(
    monkeypatch: pytest.MonkeyPatch, model: str
) -> None:
    """All fourteen seeds, at the wire — an adapter-revision input, not a nicety.

    INVARIANT (OME-884): ``max_tokens`` is KEYED, and LiteLLM decides on its own whether
    the ceiling reaches OpenAI as ``max_tokens`` (GPT-4/4o) or ``max_completion_tokens``
    (GPT-5/o-series). Both spellings mean one ceiling, so one key is correct — but only
    while the mapping is the one this revision was pinned against. A LiteLLM upgrade
    that moves a model between the two spellings changes what an unchanged request
    sends, and MUST bump ``GLOBAL_CACHE_ADAPTER_REVISION`` before rows are reused.

    WHY the wire and not the ``litellm.acompletion`` kwargs: the mapping happens INSIDE
    litellm, so the boundary above it shows ``max_tokens`` for every model and would
    pin nothing at all.
    """
    requests: list[httpx.Request] = []
    upstream = model.split("/", 1)[1]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_completion_response(upstream))

    _capture_client_factory(monkeypatch, handler)
    monkeypatch.delenv("OPENAI_CUSTOM_HEADERS", raising=False)
    monkeypatch.setattr(litellm, "headers", None)

    body = PLUGIN.prepare_chat_body(
        {"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 7}
    )
    body["api_key"] = _SELECTED_KEY
    await PLUGIN.chat_completion(body)
    await asyncio.sleep(0.05)

    assert len(requests) == 1
    assert str(requests[0].url) == "https://api.openai.com/v1/chat/completions"
    payload = json.loads(requests[0].content)
    assert payload["model"] == upstream
    fields = {"max_tokens", "max_completion_tokens"} & set(payload)
    assert len(fields) == 1, (model, sorted(fields))
    assert payload[fields.pop()] == 7


# --- OME-884 review: an ambient read that RAISES must still refuse -------------


class _ExplodingAliasMap(Mapping[str, str]):
    """A ``model_alias_map`` whose membership test raises instead of answering."""

    def __contains__(self, key: object) -> bool:
        raise RuntimeError("hostile alias map")

    def __getitem__(self, key: str) -> str:
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return iter(())

    def __len__(self) -> int:
        return 0


class _ExplodingTruthiness:
    """An ambient global that cannot even be asked whether it is set."""

    def __bool__(self) -> bool:
        raise RuntimeError("hostile truthiness")


def _raising_get_config() -> dict[str, Any]:
    raise RuntimeError("ambient config read exploded")


@pytest.mark.parametrize(
    "poison",
    [
        pytest.param(
            lambda mp: mp.setattr(
                litellm.OpenAIConfig, "get_config", staticmethod(_raising_get_config)
            ),
            id="get_config",
        ),
        pytest.param(
            lambda mp: mp.setattr(litellm, "model_alias_map", _ExplodingAliasMap()),
            id="alias_lookup",
        ),
        pytest.param(
            lambda mp: mp.setattr(litellm, "headers", _ExplodingTruthiness()),
            id="truthiness",
        ),
    ],
)
@pytest.mark.asyncio
async def test_an_ambient_read_that_raises_refuses_before_client_construction(
    monkeypatch: pytest.MonkeyPatch,
    poison: Callable[[pytest.MonkeyPatch], None],
) -> None:
    """The guard promised "fail CLOSED and never raise"; only the first half was true.

    Every ambient read was defensive about a MISSING attribute and about none of them
    answering by RAISING. A broken or hostile LiteLLM global therefore escaped as an
    ordinary ``RuntimeError``, which the chat route renders as a generic 502
    ``provider_error`` — telling the operator the upstream provider failed when in fact
    the gateway could not certify its own runtime.

    INVARIANT: unreadable is unsafe. The refusal is the SAME sanitized, non-retryable
    503 every other unsafe state produces, and it still lands before any client is
    constructed and before any credential leaves the body.
    """
    monkeypatch.delenv("OPENAI_CUSTOM_HEADERS", raising=False)
    monkeypatch.delenv("EXPERIMENTAL_OPENAI_BASE_LLM_HTTP_HANDLER", raising=False)
    monkeypatch.setattr(litellm, "secret_manager_client", None)
    monkeypatch.setattr(litellm, "model_alias_map", {})
    monkeypatch.setattr(litellm, "headers", None)
    poison(monkeypatch)

    def forbidden_client(**_kwargs: Any) -> AsyncOpenAI:
        raise AssertionError("an unreadable runtime reached client construction")

    monkeypatch.setattr(plugin_module, "AsyncOpenAI", forbidden_client)

    with pytest.raises(HTTPException) as raised:
        await PLUGIN.chat_completion(
            {
                "model": "openai/gpt-5.6-sol",
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
