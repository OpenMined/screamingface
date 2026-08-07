"""Phase 7d (OME-479 §4.6/§6.2): Hugging Face dispatch projection.

FEATURE: Hugging Face P0 observation overlay — the DISPATCH side. Proves the plan's
Phase 7 step 5: the pinned-router origin and request-local credential survive the
fail-closed projection pipeline intact, and a request carrying a projected output
parameter reaches the provider in the reviewed shape.

INVARIANT (§6.2): parameter projection COMPOSES with the existing SF-345 hardening —
``prepare_chat_body`` still pins the HF router ``api_base`` and strips the caller's
token, alongside the projected ``temperature``/``max_tokens``.
"""

from __future__ import annotations

import litellm
import pytest

from aigateway.core.parameter_projection import (
    UnsupportedParametersError,
    classify_and_project_chat_parameters,
)
from aigateway.plugins.huggingface_provider.plugin import HuggingFaceProviderPlugin

_MODEL = "huggingface/openai/gpt-oss-120b:cerebras"
_MESSAGES = [{"role": "user", "content": "hi"}]
_ROUTER_API_BASE = HuggingFaceProviderPlugin().settings.router_api_base


def _dispatch_body(caller_body: dict) -> dict:
    # The exact route pipeline (routes/chat.py), minus profile defaults (empty
    # here): strip provider controls → fail-closed classify/project → prepare.
    plugin = HuggingFaceProviderPlugin()
    stripped = plugin.strip_provider_dispatch_controls(caller_body)
    projected = classify_and_project_chat_parameters(
        stripped,
        rules=plugin.chat_parameter_rules(model=_MODEL, auth_type="api_key"),
        auth_mode="api_key",
    )
    return plugin.prepare_chat_body(projected)


def test_enabled_params_compose_with_pinned_router_and_request_local_token() -> None:
    body = _dispatch_body(
        {"model": _MODEL, "messages": _MESSAGES, "temperature": 0.5, "max_tokens": 128}
    )
    # SF-345 hardening intact ALONGSIDE the projected params (Phase 7 step 5):
    assert body["api_base"] == _ROUTER_API_BASE  # pinned-router origin
    assert "api_key" not in body  # request-local credential is never forwarded here
    # the projected standard fields stay top-level, ready for the installed transform.
    assert body["temperature"] == 0.5
    assert body["max_tokens"] == 128


def test_stop_reaches_dispatch_and_installed_transform() -> None:
    # OME-582 (§9): the enabled stop rule projects the caller field onto the dispatch
    # body, and the INSTALLED litellm Hugging Face path forwards it as the OpenAI-native
    # `stop` — pinned against the installed library, not assumed.
    body = _dispatch_body({"model": _MODEL, "messages": _MESSAGES, "stop": ["\n\n", "END"]})
    assert body["stop"] == ["\n\n", "END"]
    optional = litellm.utils.get_optional_params(
        model="openai/gpt-oss-120b",
        custom_llm_provider="huggingface",
        stop=["\n\n", "END"],
    )
    assert optional["stop"] == ["\n\n", "END"]


def test_caller_supplied_api_key_is_rejected_not_forwarded() -> None:
    # fail-closed defense distinct from an ordinary unruled param: a caller cannot
    # smuggle an api_key as a "parameter" — it is unknown to the rules and rejected
    # before any credential work, so it never reaches prepare_chat_body's strip.
    plugin = HuggingFaceProviderPlugin()
    with pytest.raises(UnsupportedParametersError) as exc:
        classify_and_project_chat_parameters(
            {"model": _MODEL, "messages": _MESSAGES, "api_key": "hf_nope"},
            rules=plugin.chat_parameter_rules(model=_MODEL, auth_type="api_key"),
            auth_mode="api_key",
        )
    assert "api_key" in exc.value.rejected
