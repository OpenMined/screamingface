"""OME-651: the gateway-owned OpenRouter strict-routing policy.

FEATURE: an accepted parameter cannot be silently ignored. OpenRouter defaults
``provider.require_parameters`` to false and documents that an endpoint which does
not support a supplied parameter may still receive the request and drop the unknown
field — so gateway acceptance, a published ``enabled`` status and successful
projection can all hold while the parameter has no effect. The gateway forces
``provider.require_parameters=true`` at its own preparation boundary, turning a
silent no-op into either a served request that honored every parameter or an
explicit provider refusal.

INVARIANT: EVERY OpenRouter chat dispatch carries the policy — there is no
parameter-dependent, model-dependent or caller-dependent path that omits it.
INVARIANT: the policy is gateway-owned. The classifier refuses a caller ``provider``
before any credential is read, and the boundary overwrites the path regardless.
INVARIANT (the tripwire that matters): the proof runs against the INSTALLED litellm
transform, on the FINAL wire JSON — not against mocked dispatch kwargs. litellm
carries the gateway's dispatch fields to OpenRouter through two behaviours it does
not promise (folding non-OpenAI kwargs into ``extra_body``, then flattening
``extra_body`` onto the wire top level). If either changes, strictness would vanish
SILENTLY, which is the exact failure mode this ticket exists to remove.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from aigateway.core.parameter_projection import classify_and_project_chat_parameters
from aigateway.plugins.openrouter_provider import plugin as openrouter_plugin_module
from aigateway.plugins.openrouter_provider.plugin import (
    OFFICIAL_API_BASE,
    OpenRouterProviderPlugin,
)
from aigateway.plugins.openrouter_provider.settings import OpenRouterPluginSettings

_KEY = "sk-or-v1-strict"
_MODEL = "openrouter/anthropic/claude-fable-5"
_UPSTREAM = "anthropic/claude-fable-5"
# Plain request JSON. Deliberately ``list[Any]`` rather than ``list[dict[str, Any]]``:
# ``transform_request`` wants litellm's invariant ``List[AllMessageValues]``, and the
# message shape is not what this module is pinning.
_MESSAGES: list[Any] = [{"role": "user", "content": "hi"}]

# The wire value under test, spelled out rather than imported. A rename of the
# production constant must not be able to silently rename what OpenRouter receives.
_STRICT = {"require_parameters": True}


# --------------------------------------------------------------------------
# harness
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _api_key_validation_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    # Explicit test double (per tests/unit/conftest.py AIDEV-NOTE): key readiness
    # is not what strict routing exercises.
    from aigateway.core.api_key_validation import (
        ApiKeyValidationResult,
        ApiKeyValidationStage,
        ApiKeyValidationState,
    )
    from aigateway.core.api_key_validation_service import ApiKeyValidationService

    async def _valid(_self, _plugin, _provider, _api_key) -> ApiKeyValidationResult:
        return ApiKeyValidationResult(
            state=ApiKeyValidationState.VALID, stage=ApiKeyValidationStage.READINESS
        )

    monkeypatch.setattr(ApiKeyValidationService, "validate", _valid)


@pytest.fixture()
def enabled_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        openrouter_plugin_module.PLUGIN, "settings", OpenRouterPluginSettings(enabled=True)
    )


def _dispatch_body(caller_body: dict[str, Any]) -> dict[str, Any]:
    """The exact route pipeline: strip controls → fail-closed classify/project → prepare."""
    plugin = OpenRouterProviderPlugin()
    stripped = plugin.strip_provider_dispatch_controls(caller_body)
    projected = classify_and_project_chat_parameters(
        stripped,
        rules=plugin.chat_parameter_rules(model=_MODEL, auth_type="api_key"),
        auth_mode="api_key",
    )
    return plugin.prepare_chat_body(projected)


def _wire_json(dispatch_body: dict[str, Any]) -> dict[str, Any]:
    """The FINAL OpenRouter request JSON, through the installed litellm 1.87.0 path.

    Mirrors what ``litellm.acompletion`` does with the gateway's dispatch kwargs:
    ``get_optional_params`` normalizes them (folding non-OpenAI keys into
    ``extra_body``), then the OpenRouter config's ``transform_request`` produces the
    body actually posted to the provider.
    """
    from litellm.llms.openrouter.chat.transformation import OpenrouterConfig
    from litellm.utils import get_optional_params

    passthrough = {
        key: value
        for key, value in dispatch_body.items()
        # Transport plumbing, not request content — never part of the JSON body.
        if key not in {"model", "messages", "api_base", "extra_headers", "api_key"}
    }
    optional = get_optional_params(model=_UPSTREAM, custom_llm_provider="openrouter", **passthrough)
    return OpenrouterConfig().transform_request(
        model=_UPSTREAM,
        messages=list(_MESSAGES),
        optional_params=dict(optional),
        litellm_params={},
        headers={},
    )


def _create_connection(client) -> None:
    resp = client.post(
        "/v1/oauth/connections/api-key",
        json={"provider": "openrouter", "label": "work-openrouter", "api_key": _KEY},
    )
    assert resp.status_code == 201, resp.text


def _fake_acompletion(captured: dict):
    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            model_dump=lambda: {"id": "or-1", "choices": [{"message": {"content": "ok"}}]}
        )

    return fake_acompletion


def _post_chat(client, body: dict[str, Any] | None = None):
    payload = {"model": _MODEL, "messages": list(_MESSAGES), **(body or {})}
    return client.post("/v1/chat/completions", json=payload)


# --------------------------------------------------------------------------
# the policy is on EVERY dispatch
# --------------------------------------------------------------------------


def test_a_bare_request_still_carries_the_strict_routing_policy() -> None:
    # The weakest possible request — no optional parameters at all. Strictness is a
    # property of the provider boundary, not of the parameters that happen to ride it.
    body = _dispatch_body({"model": _MODEL, "messages": list(_MESSAGES)})
    assert body["provider"] == _STRICT


@pytest.mark.parametrize(
    "caller",
    [
        pytest.param({"temperature": 0.5}, id="standard"),
        pytest.param({"provider_params": {"top_k": 40}}, id="native"),
        pytest.param(
            {
                "tools": [
                    {
                        "type": "function",
                        "function": {"name": "lookup", "parameters": {"type": "object"}},
                    }
                ],
                "tool_choice": "auto",
            },
            id="tool",
        ),
    ],
)
def test_every_projected_parameter_class_dispatches_with_strictness(caller) -> None:
    body = _dispatch_body({"model": _MODEL, "messages": list(_MESSAGES), **caller})
    assert body["provider"] == _STRICT


def test_strictness_composes_with_the_existing_dispatch_hardening() -> None:
    # The policy joins the other gateway-owned dispatch fields; it does not displace
    # the pinned official base or the trusted attribution headers.
    body = _dispatch_body({"model": _MODEL, "messages": list(_MESSAGES)})
    assert body["provider"] == _STRICT
    assert body["api_base"] == OFFICIAL_API_BASE
    assert body["extra_headers"]["X-Title"] == "ScreamingFace"
    assert "api_key" not in body


def test_the_policy_does_not_disturb_the_projection_output() -> None:
    # extra_body means ONE thing in this codebase: the native targets projection
    # produced. Strict routing is gateway policy and stays out of it.
    body = _dispatch_body(
        {"model": _MODEL, "messages": list(_MESSAGES), "provider_params": {"top_k": 40}}
    )
    assert body["extra_body"] == {"top_k": 40}
    assert body["provider"] == _STRICT


# --------------------------------------------------------------------------
# a caller cannot remove or override it
# --------------------------------------------------------------------------


def test_a_caller_provider_object_is_refused_before_dispatch(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    # First layer: `provider` carries no rule, so the fail-closed classifier names it
    # and refuses BEFORE any credential is read. `allow_fallbacks` is the field that
    # would otherwise re-open exactly what strictness closes.
    _create_connection(authenticated_client)
    captured: dict = {}
    with patch("litellm.acompletion", _fake_acompletion(captured)):
        resp = _post_chat(
            authenticated_client,
            {"provider": {"require_parameters": False, "allow_fallbacks": True}},
        )
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["rejected"] == {"provider": "unknown"}
    assert captured == {}


def test_the_boundary_overwrites_a_provider_that_reaches_it() -> None:
    # Second layer, independent of the first: even handed a body that already carries
    # a permissive `provider`, the boundary assigns the policy rather than merging
    # into it — so a future loosening upstream cannot weaken the wire value.
    plugin = OpenRouterProviderPlugin()
    body = plugin.prepare_chat_body(
        {
            "model": _MODEL,
            "messages": list(_MESSAGES),
            "provider": {"require_parameters": False, "allow_fallbacks": True, "order": ["x"]},
        }
    )
    assert body["provider"] == _STRICT


def test_the_policy_object_is_not_shared_between_requests() -> None:
    # A per-request copy: mutating one prepared body must not re-write the policy
    # every later request would carry.
    plugin = OpenRouterProviderPlugin()
    first = plugin.prepare_chat_body({"model": _MODEL, "messages": list(_MESSAGES)})
    first["provider"]["require_parameters"] = False
    first["provider"]["allow_fallbacks"] = True
    second = plugin.prepare_chat_body({"model": _MODEL, "messages": list(_MESSAGES)})
    assert second["provider"] == _STRICT


def test_the_policy_reaches_the_real_dispatch_call(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    # Through the REAL route, at the last gateway-controlled point.
    _create_connection(authenticated_client)
    captured: dict = {}
    with patch("litellm.acompletion", _fake_acompletion(captured)):
        resp = _post_chat(authenticated_client, {"temperature": 0.5})
    assert resp.status_code == 200, resp.text
    assert captured["provider"] == _STRICT


# --------------------------------------------------------------------------
# final-transform proof against installed litellm 1.87.0
# --------------------------------------------------------------------------


def test_final_wire_json_carries_strictness_with_every_projected_parameter() -> None:
    # The load-bearing proof. One request exercising every projected class at once —
    # standard, native and tool — and the assertion is on the JSON litellm actually
    # posts, so a transform change that drops the policy fails HERE rather than
    # silently restoring the ignore-a-parameter behaviour in production.
    tools = [{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object"}}}]
    body = _dispatch_body(
        {
            "model": _MODEL,
            "messages": list(_MESSAGES),
            "temperature": 0.5,
            "max_tokens": 128,
            "stop": ["END"],
            "response_format": {"type": "json_object"},
            "seed": 7,
            "n": 2,
            "frequency_penalty": 0.5,
            "presence_penalty": -0.5,
            "logprobs": True,
            "top_logprobs": 3,
            "provider_params": {"top_k": 40},
            "tools": tools,
            "tool_choice": "auto",
        }
    )
    wire = _wire_json(body)

    assert wire["provider"] == _STRICT
    # …together with every projected parameter, each at its own wire location.
    assert wire["temperature"] == 0.5
    assert wire["max_tokens"] == 128
    assert wire["stop"] == ["END"]
    assert wire["response_format"] == {"type": "json_object"}
    assert wire["seed"] == 7
    assert wire["n"] == 2
    assert wire["frequency_penalty"] == 0.5
    assert wire["presence_penalty"] == -0.5
    assert wire["logprobs"] is True
    assert wire["top_logprobs"] == 3
    # the native promotion: extra_body.top_k is flattened onto the wire top level
    assert wire["top_k"] == 40
    assert wire["tools"] == tools
    assert wire["tool_choice"] == "auto"


def test_final_wire_json_carries_strictness_on_a_bare_request() -> None:
    # No parameters to require — the policy is still declared, so an endpoint cannot
    # be selected on the assumption that the gateway is permissive.
    wire = _wire_json(_dispatch_body({"model": _MODEL, "messages": list(_MESSAGES)}))
    assert wire["provider"] == _STRICT


def test_a_parameter_outside_the_catalog_vocabulary_still_reaches_the_wire_with_strictness() -> (
    None
):
    # `n` is gateway-enabled and litellm-proven, but the gateway cannot know whether
    # any given OpenRouter endpoint declares it in `supported_parameters` — the
    # catalog vocabulary is the provider's, not ours. The honest outcome is to send
    # both and let OpenRouter decide explicitly: never pre-filter the parameter away,
    # never relax strictness to keep the request servable.
    wire = _wire_json(_dispatch_body({"model": _MODEL, "messages": list(_MESSAGES), "n": 2}))
    assert wire["n"] == 2
    assert wire["provider"] == _STRICT


# --------------------------------------------------------------------------
# fallback cannot bypass strictness
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "value"),
    [
        pytest.param("models", ["openrouter/anthropic/claude-opus-4.8"], id="models"),
        pytest.param("route", "fallback", id="route"),
    ],
)
def test_caller_fallback_selection_cannot_reach_a_second_route(
    path, value, enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    # OpenRouter's server-side fallback controls would let a caller name additional
    # models for the SAME request. Each one is refused, so the primary route is the
    # only route and there is no second, unstrict dispatch to fall back to.
    _create_connection(authenticated_client)
    captured: dict = {}
    with patch("litellm.acompletion", _fake_acompletion(captured)):
        resp = _post_chat(authenticated_client, {path: value})
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["rejected"] == {path: "unknown"}
    assert captured == {}


def test_the_primary_route_is_the_only_route_and_it_is_strict(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    # Exactly one upstream call, on the caller's own model, carrying the policy —
    # no gateway-side retry against a second model, and nothing for a caller-selected
    # fallback to ride.
    _create_connection(authenticated_client)
    calls: list[dict] = []

    async def counting_acompletion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            model_dump=lambda: {"id": "or-1", "choices": [{"message": {"content": "ok"}}]}
        )

    with patch("litellm.acompletion", counting_acompletion):
        resp = _post_chat(authenticated_client)

    assert resp.status_code == 200, resp.text
    assert len(calls) == 1
    assert calls[0]["model"] == _MODEL
    assert calls[0]["provider"] == _STRICT
