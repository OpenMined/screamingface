"""Caller-controlled litellm debug/logging controls are stripped at ingress
(OME-428 third-review blocker A).

# STORY: as an attacker (or a careless client) I must not be able to set a
# request-body field that makes litellm 1.87.0 escalate raw prompt/curl/response
# logging to WARNING (litellm_logging.py:1143-1168) — that bypasses the gateway
# sanitizer and leaks the prompt/provider body into logs "in all environments".
# INVARIANT: none of the litellm observability/logging control-plane fields may
# reach ``litellm.acompletion(**body)``; a conformant OpenAI-compatible client
# never sends them, and none is an OpenRouter generation parameter.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import httpx
import litellm
import pytest
from litellm import utils as litellm_utils
from litellm.litellm_core_utils.logging_worker import GLOBAL_LOGGING_WORKER

from aigateway.plugins.openrouter_provider import plugin as openrouter_plugin_module
from aigateway.plugins.openrouter_provider.settings import OpenRouterPluginSettings

_KEY = "sk-or-v1-debug"
_MODEL = "openrouter/anthropic/claude-fable-5"

# The caller-injectable litellm logging/control-plane kwargs found by the
# blocker-A audit of litellm 1.87.0 (all read straight from kwargs and reachable
# via ``litellm.acompletion(**body)``):
#   litellm_request_debug  main.py:1631 -> litellm_logging.py:1143-1168
#                          (logs raw curl/response at WARNING)
#   verbose                main.py:1265 (per-call verbose logging escalation)
#   logger_fn              main.py:1264 (caller-supplied logging callback hook)
#   litellm_logging_obj    main.py:1267 (internal logging-object override)
_DEBUG_CONTROL_FIELDS = (
    "litellm_request_debug",
    "verbose",
    "logger_fn",
    "litellm_logging_obj",
    "callbacks",
    "success_callback",
    "failure_callback",
    "litellm_params",
    "litellm_metadata",
    "turn_off_message_logging",
    "langfuse_host",
    "posthog_api_key",
)


@pytest.fixture()
def enabled_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        openrouter_plugin_module.PLUGIN, "settings", OpenRouterPluginSettings(enabled=True)
    )


def _create_connection(client, label: str) -> None:
    resp = client.post(
        "/v1/oauth/connections/api-key",
        json={"provider": "openrouter", "label": label, "api_key": _KEY},
    )
    assert resp.status_code == 201, resp.text


def _capturing_acompletion(captured: dict):
    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            model_dump=lambda: {
                "id": "gen-ok",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            }
        )

    return fake_acompletion


def test_debug_logging_controls_never_reach_dispatch(
    enabled_openrouter, credential_blobs, authenticated_client
) -> None:
    _create_connection(authenticated_client, "work-or")

    captured: dict = {}
    body = {
        "model": _MODEL,
        "messages": [{"role": "user", "content": "hi"}],
        "litellm_request_debug": True,
        "verbose": True,
        "logger_fn": "attacker-callback",
        "litellm_logging_obj": {"attacker": "obj"},
        "callbacks": ["anthropic_cache_control_hook"],
        "success_callback": ["posthog"],
        "failure_callback": ["posthog"],
        "litellm_params": {"metadata": {"posthog_host": "https://attacker.invalid"}},
        "litellm_metadata": {
            "headers": {"litellm-disable-message-redaction": True},
        },
        "turn_off_message_logging": False,
        "langfuse_host": "https://attacker.invalid",
        "posthog_api_key": "attacker-key",
        "metadata": {
            "trace_id": "safe-provider-metadata",
            "langfuse_secret": "attacker-secret",
        },
    }
    with patch("litellm.acompletion", _capturing_acompletion(captured)):
        resp = authenticated_client.post("/v1/chat/completions", json=body)

    # The debug fields must not break dispatch...
    assert resp.status_code == 200, resp.text
    # ...and none of them may reach litellm, where they would flip raw logging on.
    for field in _DEBUG_CONTROL_FIELDS:
        assert field not in captured, f"{field} reached litellm.acompletion (raw-logging leak)"
    # The legitimate generation fields still pass through.
    assert captured["model"] == _MODEL
    assert captured["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["metadata"] == {"trace_id": "safe-provider-metadata"}


def test_callback_selector_cannot_mutate_litellm_global_callback_state(
    enabled_openrouter,
    credential_blobs,
    authenticated_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _create_connection(authenticated_client, "work-or")
    # The SDK singleton can retain callbacks from a closed loop between tests.
    GLOBAL_LOGGING_WORKER._flush_on_exit()
    assert isinstance(litellm_utils.callback_list, list)
    callback_lists: tuple[list[Any], ...] = (
        cast("list[Any]", litellm.callbacks),
        cast("list[Any]", litellm.input_callback),
        cast("list[Any]", litellm.success_callback),
        cast("list[Any]", litellm.failure_callback),
        cast("list[Any]", litellm._async_input_callback),
        cast("list[Any]", litellm._async_success_callback),
        cast("list[Any]", litellm._async_failure_callback),
        cast("list[Any]", litellm_utils.callback_list),
    )
    snapshots = [list(callbacks) for callbacks in callback_lists]
    for callbacks in callback_lists:
        callbacks.clear()

    async def fake_send(self, request, *args, **kwargs):  # noqa: ANN001
        return httpx.Response(
            200,
            json={
                "id": "gen-ok",
                "model": "anthropic/claude-fable-5",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "ok"},
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
            request=request,
        )

    monkeypatch.setattr(httpx.AsyncClient, "send", fake_send)
    try:
        resp = authenticated_client.post(
            "/v1/chat/completions",
            json={
                "model": _MODEL,
                "messages": [{"role": "user", "content": "hi"}],
                "callbacks": ["anthropic_cache_control_hook"],
            },
        )
        assert resp.status_code == 200, resp.text
        assert all(not callbacks for callbacks in callback_lists)
    finally:
        authenticated_client.portal.call(GLOBAL_LOGGING_WORKER.flush)
        for callbacks, snapshot in zip(callback_lists, snapshots, strict=True):
            callbacks[:] = snapshot
