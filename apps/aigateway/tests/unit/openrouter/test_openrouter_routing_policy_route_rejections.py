"""OME-704 route-level validation and fail-closed ordering."""

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


def _post_chat(client, body: dict[str, Any] | None = None):
    payload = {"model": _MODEL, "messages": list(_MESSAGES), **(body or {})}
    return client.post("/v1/chat/completions", json=payload)


def _post_wrapper(client, wrapper: dict[str, Any]):
    return _post_chat(client, {"provider_params": wrapper})


_INVALID: tuple[tuple[str, Any], ...] = (
    ("sort", "throughput"),
    ("sort", "latency"),
    ("sort", "price "),
    ("sort", 1),
    ("max_price_prompt", "-1"),
    ("max_price_prompt", "+1"),
    ("max_price_prompt", "1e5"),
    ("max_price_prompt", "01"),
    ("max_price_prompt", ".5"),
    ("max_price_prompt", "1."),
    ("max_price_prompt", " 1"),
    ("max_price_prompt", "NaN"),
    ("max_price_prompt", "inf"),
    ("max_price_prompt", ""),
    ("max_price_prompt", 1.5),
    ("max_price_prompt", True),
    ("max_price_prompt", "1" * 65),
    ("max_price_completion", "0.1.2"),
    ("max_price_completion", None),
    ("data_collection", "maybe"),
    ("data_collection", "Deny"),
    ("data_collection", ""),
    ("zdr", "true"),
    ("zdr", 1),
    ("zdr", None),
)


@pytest.mark.parametrize(("leaf", "value"), _INVALID, ids=[f"{k}={v!r}" for k, v in _INVALID])
def test_an_invalid_value_is_refused_and_never_dispatched(
    leaf, value, enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_wrapper(authenticated_client, {leaf: value})

    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "unsupported_parameters"
    assert detail["rejected"] == {f"provider_params.{leaf}": "malformed"}
    assert dispatch.calls == []


def test_a_rejection_never_echoes_the_raw_value(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    marker = "9e5c-canary-value"
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_wrapper(authenticated_client, {"max_price_prompt": marker})

    assert resp.status_code == 400, resp.text
    assert marker not in resp.text
    assert dispatch.calls == []


def test_a_refusal_names_every_bad_leaf_at_once(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_wrapper(
            authenticated_client,
            {"sort": "throughput", "max_price_prompt": "-1", "zdr": "yes", "data_collection": "ok"},
        )

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["rejected"] == {
        "provider_params.sort": "malformed",
        "provider_params.max_price_prompt": "malformed",
        "provider_params.zdr": "malformed",
        "provider_params.data_collection": "malformed",
    }
    assert dispatch.calls == []


def test_one_bad_leaf_refuses_the_whole_request(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with patch("litellm.acompletion", dispatch):
        resp = _post_wrapper(
            authenticated_client, {"sort": "price", "max_price_prompt": "not-a-price"}
        )

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["rejected"] == {"provider_params.max_price_prompt": "malformed"}
    assert dispatch.calls == []


def _credential_tripwire(_request, **_kwargs):
    raise AssertionError("credential injection ran on a refused request")


@pytest.mark.parametrize(
    "wrapper",
    [
        {"max_price_prompt": "-1"},
        {"sort": "throughput"},
        {"zdr": "true"},
        {"order": ["anthropic"]},
        {"max_price": {"prompt": "1"}},
    ],
    ids=["bad-price", "bad-sort", "bad-zdr", "wrapped-order", "wrapped-max_price"],
)
def test_a_refused_request_never_reaches_credential_material(
    wrapper, enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)
    dispatch = _Dispatch()
    with (
        patch("aigateway.routes.chat._inject_credentials", _credential_tripwire),
        patch("litellm.acompletion", dispatch),
    ):
        resp = _post_wrapper(authenticated_client, wrapper)

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["code"] == "unsupported_parameters"
    assert dispatch.calls == []


def test_a_refused_request_never_reaches_provider_preparation(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client)

    def _tripwire(_self, _body):
        raise AssertionError("prepare_chat_body ran on a refused routing control")

    target = "aigateway.plugins.openrouter_provider.plugin.OpenRouterProviderPlugin"
    with patch(f"{target}.prepare_chat_body", _tripwire):
        resp = _post_wrapper(authenticated_client, {"max_price_prompt": "1e5"})

    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "unsupported_parameters"


def test_a_reconstruction_mismatch_precedes_cache_credentials_dispatch_and_logs(
    enabled_openrouter, credential_blobs, authenticated_client, caplog
) -> None:
    _create_connection(authenticated_client)
    marker = "route-reconstruction-secret-7f21"
    dispatch = _Dispatch()

    def _mismatched_projection(body, **_kwargs):
        return {**body, "provider": {"require_parameters": marker}}

    def _cache_tripwire(*_args, **_kwargs):
        raise AssertionError("cache planning ran on a reconstruction mismatch")

    with (
        patch(
            "aigateway.routes.chat.classify_and_project_chat_parameters",
            _mismatched_projection,
        ),
        patch("aigateway.routes.chat.caller_cache_bypass_paths", _cache_tripwire),
        patch("aigateway.routes.chat._resolve_cache_plan", _cache_tripwire),
        patch("aigateway.routes.chat._inject_credentials", _credential_tripwire),
        patch("litellm.acompletion", dispatch),
        caplog.at_level("DEBUG"),
    ):
        resp = _post_chat(authenticated_client)

    assert resp.status_code == 503, resp.text
    assert resp.json()["detail"] == {
        "code": "provider_unavailable",
        "message": "OpenRouter dispatch is unavailable",
    }
    assert marker not in resp.text
    assert marker not in caplog.text
    assert dispatch.calls == []
