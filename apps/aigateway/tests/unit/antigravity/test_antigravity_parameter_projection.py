"""OME-634: Antigravity's enabled rules, proven into the Code Assist wire body.

FEATURE: caller parameter support for Antigravity. The plugin shipped NO rules, and
the classifier is fail-closed, so every optional field a normal OpenAI-compatible
client sends was rejected with a 400 before dispatch. This represents what
``build_generate_content_body`` already honors as gateway rules, so the fields the
builder maps become enabled and every other field still fails closed.

STORY: as a caller on an Antigravity OAuth profile, the sampling params and tools I
send reach the Code Assist request body; anything the gateway has not reviewed is
rejected with a safe 400 before any credential is read.

INVARIANT (§9 "Projection"): a rule is enabled ONLY with proof the value reaches the
last AIGateway-owned boundary — here ``build_generate_content_body``, OUR code that
emits the wire body — pinned by running the request pipeline exactly as
``routes/chat.py`` + ``plugin.chat_completion`` do, never by asserting a kwarg
reached a handler.
INVARIANT: Antigravity is OAuth-ONLY (``supports_api_key() is False``), so every rule
declares that single mode. An api-key mode is not merely unused here — it does not
exist for this provider, and publishing rules for it would advertise a path the
gateway cannot take.
"""

from __future__ import annotations

import pytest

from aigateway.core.parameter_projection import (
    UnsupportedParametersError,
    classify_and_project_chat_parameters,
)
from aigateway.plugins.antigravity_provider.message_adapter import build_generate_content_body
from aigateway.plugins.antigravity_provider.plugin import AntigravityProviderPlugin

_MODEL = "antigravity/gemini-3-flash"
_MESSAGES = [{"role": "user", "content": "hi"}]
# Mirrors plugin.chat_completion's optional_params harvest: everything top-level
# except these becomes the builder's optional_params.
_OPTIONAL_EXCLUDES = {"model", "messages", "api_key", "extra_headers", "timeout"}
_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Look up the weather",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
    },
}


def _plugin() -> AntigravityProviderPlugin:
    return AntigravityProviderPlugin()


def _rules():
    return _plugin().chat_parameter_rules(model=_MODEL, auth_type="oauth")


def _projected(caller_body: dict) -> dict:
    # The route pipeline (routes/chat.py), minus profile defaults: strip provider
    # controls → fail-closed classify/project → prepare_chat_body.
    plugin = _plugin()
    projected = classify_and_project_chat_parameters(
        plugin.strip_provider_dispatch_controls(caller_body),
        rules=plugin.chat_parameter_rules(model=_MODEL, auth_type="oauth"),
        auth_mode="oauth",
    )
    return plugin.prepare_chat_body(projected)


def _wire_body(caller_body: dict) -> dict:
    # Reproduces the dispatch harvest: prepared body → optional_params →
    # build_generate_content_body → the inner `request` object sent upstream.
    prepared = _projected(caller_body)
    optional_params = {k: v for k, v in prepared.items() if k not in _OPTIONAL_EXCLUDES}
    return build_generate_content_body(prepared["messages"], optional_params)


def _generation_config(caller_body: dict) -> dict:
    return _wire_body(caller_body).get("generationConfig", {})


def _reject(caller_body: dict) -> dict[str, str]:
    plugin = _plugin()
    with pytest.raises(UnsupportedParametersError) as exc:
        classify_and_project_chat_parameters(
            plugin.strip_provider_dispatch_controls(caller_body),
            rules=plugin.chat_parameter_rules(model=_MODEL, auth_type="oauth"),
            auth_mode="oauth",
        )
    return exc.value.rejected


# --- the rule set -------------------------------------------------------------


def test_the_enabled_paths_are_exactly_the_fields_the_builder_maps() -> None:
    # INVARIANT: the rule set is not "the OpenAI standard fields" — it is the set the
    # INSTALLED builder reads out of optional_params. A rule for anything else would
    # accept a caller's value and silently drop it before the wire.
    assert {rule.request_path for rule in _rules()} == {
        "temperature",
        "top_p",
        "max_tokens",
        "stop",
        "provider_params.top_k",
        "tools",
    }


def test_every_rule_is_oauth_only() -> None:
    assert _plugin().supports_api_key() is False
    for rule in _rules():
        assert tuple(rule.applicable_auth_modes) == ("oauth",), rule.request_path


def test_native_top_k_is_a_wrapper_rule_projected_to_the_key_the_builder_reads() -> None:
    (rule,) = [r for r in _rules() if r.request_path == "provider_params.top_k"]
    assert rule.projection_kind == "provider_native"
    assert rule.target == "top_k"


# --- the wire body ------------------------------------------------------------


def test_enabled_sampling_params_reach_generation_config() -> None:
    config = _generation_config(
        {
            "model": _MODEL,
            "messages": _MESSAGES,
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 128,
        }
    )
    assert config.get("temperature") == 0.7
    assert config.get("topP") == 0.9
    assert config.get("maxOutputTokens") == 128


def test_native_top_k_reaches_generation_config_topK() -> None:
    caller = {"model": _MODEL, "messages": _MESSAGES, "provider_params": {"top_k": 40}}
    prepared = _projected(caller)
    # The wrapper is CONSUMED key-by-key and never splatted into the dispatch body.
    assert prepared["top_k"] == 40
    assert "provider_params" not in prepared
    assert _generation_config(caller).get("topK") == 40


@pytest.mark.parametrize(
    ("stop", "expected"),
    [(["\n\n", "END"], ["\n\n", "END"]), ("STOP", ["STOP"])],
)
def test_stop_reaches_stop_sequences_in_both_union_forms(stop: object, expected: list[str]) -> None:
    # The builder renames `stop` to stopSequences, coercing the scalar form into a
    # one-element list — so BOTH arms of the OpenAI union have a proven wire home.
    config = _generation_config({"model": _MODEL, "messages": _MESSAGES, "stop": stop})
    assert config["stopSequences"] == expected


def test_tools_reach_function_declarations() -> None:
    # The builder unwraps the OpenAI {"type":"function","function":{…}} shape into a
    # Code Assist functionDeclarations entry — a real conversion, not a verbatim copy.
    body = _wire_body({"model": _MODEL, "messages": _MESSAGES, "tools": [_TOOL]})
    (group,) = body["tools"]
    (declaration,) = group["functionDeclarations"]
    assert declaration["name"] == "get_weather"
    assert declaration["description"] == "Look up the weather"
    assert declaration["parameters"]["properties"]["city"] == {"type": "string"}


# --- still fail-closed --------------------------------------------------------


def test_tool_choice_is_not_enabled_because_the_builder_has_no_home_for_it() -> None:
    # The gateway never advertises a control it cannot honor: the builder emits no
    # toolConfig, so tool_choice has nowhere to land and stays rejected even though
    # `tools` is enabled.
    assert "tool_choice" not in {rule.request_path for rule in _rules()}
    assert _reject(
        {"model": _MODEL, "messages": _MESSAGES, "tools": [_TOOL], "tool_choice": "auto"}
    ) == {"tool_choice": "unknown"}


@pytest.mark.parametrize("field", ["response_format", "seed", "n", "frequency_penalty"])
def test_fields_the_builder_drops_still_fail_closed(field: str) -> None:
    assert _reject({"model": _MODEL, "messages": _MESSAGES, field: 1}) == {field: "unknown"}


def test_a_caller_native_generation_config_cannot_be_smuggled() -> None:
    # messages/params → generationConfig is the ONLY supported channel; a raw native
    # object is an unknown field and fails closed before any credential is read.
    rejected = _reject(
        {"model": _MODEL, "messages": _MESSAGES, "generationConfig": {"temperature": 2}}
    )
    assert rejected == {"generationConfig": "unknown"}


@pytest.mark.parametrize(
    ("field", "value"),
    [("temperature", 5.0), ("top_p", 2.0), ("max_tokens", 0), ("stop", [123])],
)
def test_enabled_fields_still_validate_their_schema(field: str, value: object) -> None:
    # Enabling a field never means accepting any shape — the bounded schema still
    # guards, and a bad value is malformed at classification, never on the wire.
    assert _reject({"model": _MODEL, "messages": _MESSAGES, field: value}) == {field: "malformed"}


# --- contract agreement -------------------------------------------------------


def test_every_enabled_path_carries_a_provider_observation() -> None:
    # §4.4: an enabled parameter is never left unevidenced. (An observation still
    # never ENABLES anything — only a rule does.)
    plugin = _plugin()
    observed = {
        obs.request_path
        for obs in plugin.chat_parameter_observations(model=_MODEL, auth_type="oauth")
    }
    assert {rule.request_path for rule in _rules()} <= observed


def test_observations_carry_the_providers_own_source_label() -> None:
    # Antigravity shares the Code Assist request SHAPE with Gemini's OAuth path but is
    # a different upstream, so its evidence is labelled its own — never borrowed.
    sources = {
        obs.source for obs in _plugin().chat_parameter_observations(model=_MODEL, auth_type="oauth")
    }
    assert sources == {"antigravity:code-assist"}


def test_the_advertised_tool_type_matches_the_tools_rule() -> None:
    capabilities = _plugin().chat_parameter_tools(model=_MODEL, auth_type="oauth")
    assert [cap.tool_type for cap in capabilities] == ["function"]
    assert all(cap.gateway_status == "enabled" for cap in capabilities)
