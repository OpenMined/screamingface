"""OME-704 route-level isolation from OpenRouter's raw control plane."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from aigateway.plugins.openrouter_provider import plugin as openrouter_plugin_module
from aigateway.plugins.openrouter_provider.settings import OpenRouterPluginSettings

_KEY = "sk-or-v1-routing"
_MODEL = "openrouter/anthropic/claude-fable-5"
_MESSAGES: list[Any] = [{"role": "user", "content": "hi"}]
_OFFICIAL_API_BASE = "https://openrouter.ai/api/v1"
_STRICT = {"require_parameters": True}
_CONTROL_LEAVES = (
    "sort",
    "max_price_prompt",
    "max_price_completion",
    "data_collection",
    "zdr",
)


@pytest.fixture(autouse=True)
def _api_key_validation_ok(monkeypatch: pytest.MonkeyPatch) -> None:
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


def _create_connection(client) -> None:
    resp = client.post(
        "/v1/oauth/connections/api-key",
        json={"provider": "openrouter", "label": "work-openrouter", "api_key": _KEY},
    )
    assert resp.status_code == 201, resp.text


class _Dispatch:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            model_dump=lambda: {
                "id": f"or-{len(self.calls)}",
                "choices": [{"message": {"content": "ok"}}],
            }
        )

    @property
    def only(self) -> dict[str, Any]:
        assert len(self.calls) == 1, f"expected exactly one dispatch, got {len(self.calls)}"
        return self.calls[0]


def _post_chat(client, body: dict[str, Any] | None = None):
    payload = {"model": _MODEL, "messages": list(_MESSAGES), **(body or {})}
    return client.post("/v1/chat/completions", json=payload)


def _post_wrapper(client, wrapper: dict[str, Any]):
    return _post_chat(client, {"provider_params": wrapper})


_EXCLUDED_TOP_LEVEL: tuple[tuple[str, Any], ...] = (
    ("provider", {"order": ["anthropic"], "allow_fallbacks": False}),
    ("provider", {"max_price": {"prompt": "1"}}),
    ("order", ["anthropic"]),
    ("only", ["anthropic"]),
    ("ignore", ["openai"]),
    ("allow_fallbacks", False),
    ("quantizations", ["fp8"]),
    ("route", "fallback"),
    ("models", ["openrouter/anthropic/claude-opus-4.8"]),
    ("plugins", [{"id": "web"}]),
)


@pytest.mark.parametrize(
    ("path", "value"),
    _EXCLUDED_TOP_LEVEL,
    ids=[f"{k}-{i}" for i, (k, _) in enumerate(_EXCLUDED_TOP_LEVEL)],
)
def test_an_excluded_routing_field_is_a_named_unknown_rejection(
    path, value, enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_chat(authenticated_client, {path: value})

    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "unsupported_parameters"
    assert detail["rejected"] == {path: "unknown"}
    assert dispatch.calls == []


def test_the_raw_provider_object_is_refused_even_beside_valid_controls(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_chat(
            authenticated_client,
            {"provider_params": {"sort": "price"}, "provider": {"order": ["anthropic"]}},
        )

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["rejected"] == {"provider": "unknown"}
    assert dispatch.calls == []


_WRAPPER_ATTACKS: tuple[tuple[str, Any], ...] = (
    ("order", ["anthropic"]),
    ("only", ["anthropic"]),
    ("ignore", ["openai"]),
    ("allow_fallbacks", False),
    ("quantizations", ["fp8"]),
    ("require_parameters", False),
    ("max_price", {"prompt": "1"}),
    ("provider", {"order": ["anthropic"]}),
    ("data_collection_policy", "deny"),
    ("zero_data_retention", True),
    ("max_price_prompt_usd", "1"),
)


@pytest.mark.parametrize(("leaf", "value"), _WRAPPER_ATTACKS, ids=[k for k, _ in _WRAPPER_ATTACKS])
def test_a_wrapped_excluded_field_is_a_named_unknown_rejection(
    leaf, value, enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_wrapper(authenticated_client, {leaf: value})

    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "unsupported_parameters"
    assert detail["rejected"] == {f"provider_params.{leaf}": "unknown"}
    assert dispatch.calls == []


@pytest.mark.parametrize("leaf", _CONTROL_LEAVES)
def test_a_dotted_top_level_leaf_is_not_a_second_addressing_form(
    leaf, enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_chat(authenticated_client, {f"provider_params.{leaf}": "price"})

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["rejected"] == {f"provider_params.{leaf}": "unknown"}
    assert dispatch.calls == []


def test_a_non_object_wrapper_is_refused_by_shape(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_chat(authenticated_client, {"provider_params": ["sort"]})

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["rejected"] == {"provider_params": "not_an_object"}
    assert dispatch.calls == []


def test_generic_dispatch_controls_are_still_stripped_not_rejected(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_chat(
            authenticated_client,
            {
                "provider_params": {"max_price_prompt": "1.5"},
                "api_base": "https://evil.example/v1",
                "base_url": "https://evil.example/v1",
                "model_list": [{"model_name": _MODEL, "litellm_params": {"api_key": "sk-evil"}}],
                "extra_body": {"provider": {"order": ["anthropic"], "allow_fallbacks": True}},
            },
        )

    assert resp.status_code == 200, resp.text
    captured = dispatch.only
    assert captured["api_base"] == _OFFICIAL_API_BASE
    assert "base_url" not in captured
    assert "model_list" not in captured
    assert captured["provider"] == {"max_price": {"prompt": "1.5"}, **_STRICT}
    assert "extra_body" not in captured
    assert "evil.example" not in repr({k: v for k, v in captured.items() if k != "api_key"})


def test_a_wrapped_native_param_and_the_routing_policy_share_the_wire(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_wrapper(authenticated_client, {"top_k": 40, "sort": "price"})

    assert resp.status_code == 200, resp.text
    captured = dispatch.only
    assert captured["extra_body"] == {"top_k": 40}
    assert captured["provider"] == {"sort": "price", **_STRICT}
