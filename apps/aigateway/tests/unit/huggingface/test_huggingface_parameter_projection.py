"""Phase 7b (OME-479 §6.2/§9): Hugging Face enabled rules + installed-transform proof.

FEATURE: Hugging Face P0 observation overlay — the DISPATCH side. HF's router is
OpenAI-compatible, so the standard sampling fields the INSTALLED litellm transform
accepts are enabled as `direct` rules; every other caller field fails closed.

INVARIANT (§6.2 step 4 / §9 "Projection"): a rule is enabled ONLY with proof that
the field reaches the installed final transform. These tests pin the last boundary
by running the request pipeline AND the installed ``HuggingFaceChatConfig``
transform — not merely asserting a key reached ``litellm.acompletion(**kwargs)``.
INVARIANT: unruled fields (incl. HF-unsupported ``top_k``) are rejected fail-closed
BEFORE any credential work.
"""

from __future__ import annotations

import pytest
from litellm.llms.huggingface.chat.transformation import HuggingFaceChatConfig

from aigateway.core.parameter_projection import (
    UnsupportedParametersError,
    classify_and_project_chat_parameters,
)
from aigateway.plugins.huggingface_provider.plugin import HuggingFaceProviderPlugin

_MODEL = "huggingface/openai/gpt-oss-120b:cerebras"
# What litellm sees after it strips the ``huggingface/`` custom-provider prefix.
_UPSTREAM = "openai/gpt-oss-120b:cerebras"
_MESSAGES = [{"role": "user", "content": "hi"}]


def _dispatch_body(caller_body: dict) -> dict:
    # The route pipeline (routes/chat.py), minus profile defaults (empty here):
    # strip provider controls → fail-closed classify/project → prepare_chat_body.
    plugin = HuggingFaceProviderPlugin()
    stripped = plugin.strip_provider_dispatch_controls(caller_body)
    projected = classify_and_project_chat_parameters(
        stripped,
        rules=plugin.chat_parameter_rules(model=_MODEL, auth_type="api_key"),
        auth_mode="api_key",
    )
    return plugin.prepare_chat_body(projected)


def test_temperature_and_max_tokens_are_ruled() -> None:
    rules = HuggingFaceProviderPlugin().chat_parameter_rules(model=_MODEL, auth_type="api_key")
    paths = {rule.request_path for rule in rules}
    assert {"temperature", "max_tokens"} <= paths


def test_enabled_params_reach_installed_final_transform() -> None:
    prepared = _dispatch_body(
        {"model": _MODEL, "messages": _MESSAGES, "temperature": 0.5, "max_tokens": 128}
    )
    # AIGateway-owned boundary: the gateway forwards both at the top level.
    assert prepared["temperature"] == 0.5
    assert prepared["max_tokens"] == 128
    # Installed final transform (litellm ``HuggingFaceChatConfig``): both reach the
    # outbound provider body — pinned against the installed library, not assumed.
    cfg = HuggingFaceChatConfig()
    mapped = cfg.map_openai_params(
        non_default_params={
            "temperature": prepared["temperature"],
            "max_tokens": prepared["max_tokens"],
        },
        optional_params={},
        model=_UPSTREAM,
        drop_params=False,
    )
    body = cfg.transform_request(
        model=_UPSTREAM,
        messages=prepared["messages"],
        optional_params=mapped,
        litellm_params={"api_base": prepared["api_base"]},
        headers={},
    )
    assert body["temperature"] == 0.5
    assert body["max_tokens"] == 128


def test_unruled_parameter_is_rejected_fail_closed() -> None:
    plugin = HuggingFaceProviderPlugin()
    with pytest.raises(UnsupportedParametersError) as exc:
        classify_and_project_chat_parameters(
            {"model": _MODEL, "messages": _MESSAGES, "top_p": 0.9},
            rules=plugin.chat_parameter_rules(model=_MODEL, auth_type="api_key"),
            auth_mode="api_key",
        )
    # top_p is observed-but-unruled for HF: visible in the contract, REJECTED here.
    assert exc.value.rejected == {"top_p": "unknown"}


def test_native_top_k_is_rejected_fail_closed() -> None:
    # HF's installed transform has NO top_k and the gateway rules none, so a wrapped
    # native top_k fails closed — no fabricated native support (honesty vs OpenRouter).
    plugin = HuggingFaceProviderPlugin()
    with pytest.raises(UnsupportedParametersError) as exc:
        classify_and_project_chat_parameters(
            {"model": _MODEL, "messages": _MESSAGES, "provider_params": {"top_k": 40}},
            rules=plugin.chat_parameter_rules(model=_MODEL, auth_type="api_key"),
            auth_mode="api_key",
        )
    assert any("top_k" in path for path in exc.value.rejected)


# --- OME-583 (§9): function calling reaches the installed HuggingFaceChatConfig transform --

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the weather for a city",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        },
    }
]


def test_tools_and_tool_choice_are_ruled() -> None:
    rules = HuggingFaceProviderPlugin().chat_parameter_rules(model=_MODEL, auth_type="api_key")
    paths = {rule.request_path for rule in rules}
    assert {"tools", "tool_choice"} <= paths


def test_tools_and_tool_choice_reach_installed_final_transform() -> None:
    prepared = _dispatch_body(
        {
            "model": _MODEL,
            "messages": _MESSAGES,
            "tools": _TOOLS,
            "tool_choice": "auto",
        }
    )
    assert prepared["tools"] == _TOOLS
    assert prepared["tool_choice"] == "auto"
    # Installed final transform (litellm HuggingFaceChatConfig): both reach the
    # outbound provider body — pinned against the installed library, not assumed.
    cfg = HuggingFaceChatConfig()
    mapped = cfg.map_openai_params(
        non_default_params={"tools": _TOOLS, "tool_choice": "auto"},
        optional_params={},
        model=_UPSTREAM,
        drop_params=False,
    )
    body = cfg.transform_request(
        model=_UPSTREAM,
        messages=prepared["messages"],
        optional_params=mapped,
        litellm_params={"api_base": prepared["api_base"]},
        headers={},
    )
    assert body["tools"] == _TOOLS
    assert body["tool_choice"] == "auto"


def test_unadvertised_tool_type_is_rejected_fail_closed() -> None:
    plugin = HuggingFaceProviderPlugin()
    with pytest.raises(UnsupportedParametersError) as exc:
        classify_and_project_chat_parameters(
            {"model": _MODEL, "messages": _MESSAGES, "tools": [{"type": "web_search"}]},
            rules=plugin.chat_parameter_rules(model=_MODEL, auth_type="api_key"),
            auth_mode="api_key",
        )
    assert exc.value.rejected == {"tools": "malformed"}


# --- OME-584 (§9): response_format reaches the installed HuggingFaceChatConfig transform --

_RESPONSE_FORMAT_JSON_OBJECT = {"type": "json_object"}
_RESPONSE_FORMAT_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "weather",
        "schema": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}


def test_response_format_is_ruled() -> None:
    rules = HuggingFaceProviderPlugin().chat_parameter_rules(model=_MODEL, auth_type="api_key")
    assert "response_format" in {rule.request_path for rule in rules}


def test_response_format_reaches_installed_final_transform() -> None:
    cfg = HuggingFaceChatConfig()
    for rf in (_RESPONSE_FORMAT_JSON_OBJECT, _RESPONSE_FORMAT_JSON_SCHEMA):
        prepared = _dispatch_body({"model": _MODEL, "messages": _MESSAGES, "response_format": rf})
        # AIGateway-owned boundary: the gateway forwards it at the top level.
        assert prepared["response_format"] == rf
        # Installed final transform (litellm HuggingFaceChatConfig): the value reaches
        # the outbound provider body VERBATIM — pinned against the installed library.
        mapped = cfg.map_openai_params(
            non_default_params={"response_format": rf},
            optional_params={},
            model=_UPSTREAM,
            drop_params=False,
        )
        body = cfg.transform_request(
            model=_UPSTREAM,
            messages=prepared["messages"],
            optional_params=mapped,
            litellm_params={"api_base": prepared["api_base"]},
            headers={},
        )
        assert body["response_format"] == rf


def test_malformed_response_format_type_is_rejected_fail_closed() -> None:
    plugin = HuggingFaceProviderPlugin()
    with pytest.raises(UnsupportedParametersError) as exc:
        classify_and_project_chat_parameters(
            {"model": _MODEL, "messages": _MESSAGES, "response_format": {"type": "xml"}},
            rules=plugin.chat_parameter_rules(model=_MODEL, auth_type="api_key"),
            auth_mode="api_key",
        )
    assert exc.value.rejected == {"response_format": "malformed"}


# --- OME-585 (§9): seed + n reach the installed HuggingFaceChatConfig transform --


def test_seed_and_n_are_ruled() -> None:
    rules = HuggingFaceProviderPlugin().chat_parameter_rules(model=_MODEL, auth_type="api_key")
    assert {"seed", "n"} <= {rule.request_path for rule in rules}


def test_seed_and_n_reach_installed_final_transform() -> None:
    prepared = _dispatch_body({"model": _MODEL, "messages": _MESSAGES, "seed": 42, "n": 3})
    # AIGateway-owned boundary: the gateway forwards both at the top level.
    assert prepared["seed"] == 42
    assert prepared["n"] == 3
    # Installed final transform (litellm HuggingFaceChatConfig): both reach the outbound
    # provider body VERBATIM — pinned against the installed library, not assumed.
    cfg = HuggingFaceChatConfig()
    mapped = cfg.map_openai_params(
        non_default_params={"seed": 42, "n": 3},
        optional_params={},
        model=_UPSTREAM,
        drop_params=False,
    )
    body = cfg.transform_request(
        model=_UPSTREAM,
        messages=prepared["messages"],
        optional_params=mapped,
        litellm_params={"api_base": prepared["api_base"]},
        headers={},
    )
    assert body["seed"] == 42
    assert body["n"] == 3


def test_malformed_n_is_rejected_fail_closed() -> None:
    plugin = HuggingFaceProviderPlugin()
    with pytest.raises(UnsupportedParametersError) as exc:
        classify_and_project_chat_parameters(
            {"model": _MODEL, "messages": _MESSAGES, "n": 0},  # below the minimum of 1
            rules=plugin.chat_parameter_rules(model=_MODEL, auth_type="api_key"),
            auth_mode="api_key",
        )
    assert exc.value.rejected == {"n": "malformed"}


def test_non_integer_seed_is_rejected_fail_closed() -> None:
    plugin = HuggingFaceProviderPlugin()
    with pytest.raises(UnsupportedParametersError) as exc:
        classify_and_project_chat_parameters(
            {"model": _MODEL, "messages": _MESSAGES, "seed": 1.5},  # not an integer
            rules=plugin.chat_parameter_rules(model=_MODEL, auth_type="api_key"),
            auth_mode="api_key",
        )
    assert exc.value.rejected == {"seed": "malformed"}
