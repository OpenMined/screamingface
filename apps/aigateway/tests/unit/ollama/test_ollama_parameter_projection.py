"""OME-636: Ollama's enabled rule set, proven through LiteLLM's own transform.

FEATURE: caller parameter support for the local no-auth provider. Ollama shipped
NO rules, so the fail-closed classifier rejected every optional field a normal
OpenAI-compatible client sent. It was the last plugin in that state.

STORY: as a caller on a local Ollama host — where I hold no credentials at all —
the sampling and tool fields I send reach the model, and the fields Ollama cannot
honor come back as a safe 400 instead of being dropped somewhere downstream.

INVARIANT (§9 "Projection"): Ollama's final transform is LiteLLM's own
``OllamaChatConfig.map_openai_params``, not gateway code. A rule is earned only by
proving the value survives THAT mapping, so the tests below assert on the real
transformed parameter dict.
INVARIANT: a provider's DECLARED support list is not evidence — the mapping is.
``get_supported_openai_params`` names ``tool_choice``; the mapping has no branch
for it and discards it. The declaration is what a naive port would have trusted.
"""

from __future__ import annotations

from typing import Any

import pytest
from litellm.utils import get_optional_params

from aigateway.core.parameter_projection import (
    UnsupportedParametersError,
    classify_and_project_chat_parameters,
)
from aigateway.plugins.ollama_provider.plugin import OllamaProviderPlugin

_MODEL = "ollama/llama3.2"
_UPSTREAM_MODEL = "llama3.2"
_MESSAGES = [{"role": "user", "content": "hi"}]
_TOOL = {"type": "function", "function": {"name": "get_weather", "parameters": {}}}
# Fields litellm takes as its own arguments rather than as mapped model params.
_NOT_MODEL_PARAMS = {"model", "messages", "api_key", "api_base", "extra_headers", "timeout"}


def _plugin() -> OllamaProviderPlugin:
    return OllamaProviderPlugin()


def _rules():
    return _plugin().chat_parameter_rules(model=_MODEL, auth_type="none")


def _projected(caller_body: dict[str, Any]) -> dict[str, Any]:
    plugin = _plugin()
    projected = classify_and_project_chat_parameters(
        plugin.strip_provider_dispatch_controls(caller_body),
        rules=plugin.chat_parameter_rules(model=_MODEL, auth_type="none"),
        auth_mode="none",
    )
    return plugin.prepare_chat_body(projected)


def _wire(caller_body: dict[str, Any]) -> dict[str, Any]:
    """Run the full path and return the params litellm would put on the wire.

    ``chat_completion`` hands the prepared body to ``litellm.acompletion``, which
    resolves ``ollama_chat/…`` to OllamaChatConfig and maps the optional params —
    so calling ``get_optional_params`` for that provider mirrors dispatch exactly.
    """
    prepared = _projected(caller_body)
    params = {k: v for k, v in prepared.items() if k not in _NOT_MODEL_PARAMS}
    out = get_optional_params(model=_UPSTREAM_MODEL, custom_llm_provider="ollama_chat", **params)
    out.pop("stream", None)
    return out


def _reject(caller_body: dict[str, Any]) -> dict[str, str]:
    plugin = _plugin()
    with pytest.raises(UnsupportedParametersError) as exc:
        classify_and_project_chat_parameters(
            plugin.strip_provider_dispatch_controls(caller_body),
            rules=plugin.chat_parameter_rules(model=_MODEL, auth_type="none"),
            auth_mode="none",
        )
    return exc.value.rejected


def _body(**fields: Any) -> dict[str, Any]:
    return {"model": _MODEL, "messages": _MESSAGES, **fields}


# --- the rule set -------------------------------------------------------------


def test_the_enabled_paths_are_exactly_the_ones_the_transform_carries() -> None:
    assert {rule.request_path for rule in _rules()} == {
        "temperature",
        "top_p",
        "max_tokens",
        "seed",
        "stop",
        "response_format",
        "reasoning_effort",
        "tools",
    }


def test_every_rule_applies_to_the_no_auth_mode_only() -> None:
    # Ollama holds no credentials; publishing an oauth or api-key mode would
    # advertise a path dispatch cannot take.
    for rule in _rules():
        assert tuple(rule.applicable_auth_modes) == ("none",)


# --- the wire params ----------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value", "wire_key", "wire_value"),
    [
        ("temperature", 0.5, "temperature", 0.5),
        ("top_p", 0.9, "top_p", 0.9),
        ("seed", 7, "seed", 7),
        ("max_tokens", 64, "num_predict", 64),
        ("stop", ["END"], "stop", ["END"]),
    ],
)
def test_each_sampling_field_reaches_its_wire_key(
    field: str, value: Any, wire_key: str, wire_value: Any
) -> None:
    assert _wire(_body(**{field: value}))[wire_key] == wire_value


def test_tools_reach_the_wire_in_the_shape_ollama_accepts() -> None:
    # Ollama 0.4+ takes the OpenAI nested tool shape directly, so the transform
    # passes it through unchanged — no adapter needed, unlike a Responses backend.
    assert _wire(_body(tools=[_TOOL]))["tools"] == [_TOOL]


@pytest.mark.parametrize(
    ("response_format", "expected"),
    [
        ({"type": "json_object"}, "json"),
        (
            {"type": "json_schema", "json_schema": {"name": "s", "schema": {"type": "object"}}},
            {"type": "object"},
        ),
    ],
)
def test_the_structured_output_arms_reach_the_format_field(
    response_format: dict[str, Any], expected: Any
) -> None:
    assert _wire(_body(response_format=response_format))["format"] == expected


def test_the_text_response_format_arm_is_carried_by_producing_no_wire_field() -> None:
    # WHY this is faithful rather than a silent drop: absent `format` IS Ollama's
    # free-form text behavior, so the caller gets exactly what {"type":"text"}
    # asks for. Narrowing the schema to reject the arm would refuse a legal
    # OpenAI default that the provider already satisfies.
    assert "format" not in _wire(_body(response_format={"type": "text"}))


@pytest.mark.parametrize(
    ("effort", "think"),
    [("none", False), ("minimal", False), ("low", True), ("medium", True), ("high", True)],
)
def test_reasoning_effort_reaches_the_think_flag(effort: str, think: bool) -> None:
    # The mapping COARSENS an effort ladder to a boolean outside the gpt-oss family.
    # The value is carried at reduced resolution, and the direction is preserved —
    # pinned here so a future litellm change to this mapping is visible.
    assert _wire(_body(reasoning_effort=effort))["think"] is think


# --- still fail-closed --------------------------------------------------------


def test_tool_choice_is_refused_because_the_transform_silently_discards_it() -> None:
    # The unit's clearest case for reading the mapping instead of the declared list:
    # get_supported_openai_params() names tool_choice, but map_openai_params has no
    # branch for it and pops it, noting upstream that it hangs Ollama requests.
    assert _reject(_body(tools=[_TOOL], tool_choice="auto")) == {"tool_choice": "unknown"}
    assert "tool_choice" not in get_optional_params(
        model=_UPSTREAM_MODEL,
        custom_llm_provider="ollama_chat",
        tools=[_TOOL],
        tool_choice="auto",
    )


@pytest.mark.parametrize("field", ["presence_penalty", "n", "logprobs", "top_logprobs"])
def test_fields_the_transform_rejects_fail_closed_first(field: str) -> None:
    # litellm RAISES UnsupportedParamsError on these; the classifier refuses them
    # earlier, which is the better error and costs no credential access.
    assert _reject(_body(**{field: 1})) == {field: "unknown"}


def test_frequency_penalty_is_not_enabled_despite_being_carried() -> None:
    # WHY excluded: the transform renames it to `repeat_penalty`, which is a
    # DIFFERENT scale — OpenAI's 0 means "no penalty" and is the common default,
    # while Ollama disables at 1.0 and treats 0 as a degenerate value. Carrying a
    # value is necessary but not sufficient; the mapping must also preserve
    # meaning, and an inverted default is worse than an honest refusal.
    assert _reject(_body(frequency_penalty=0)) == {"frequency_penalty": "unknown"}


def test_an_unknown_field_still_fails_closed() -> None:
    assert _reject(_body(wibble=1)) == {"wibble": "unknown"}


@pytest.mark.parametrize(
    ("field", "value"),
    [("temperature", 9.0), ("top_p", 4.0), ("max_tokens", 0), ("reasoning_effort", "turbo")],
)
def test_schema_violations_fail_closed_as_malformed(field: str, value: Any) -> None:
    assert _reject(_body(**{field: value})) == {field: "malformed"}


def test_a_native_ollama_option_cannot_be_smuggled_through() -> None:
    # num_predict is Ollama's own wire name. Only a rule may put it there, and the
    # rule projects from `max_tokens`; the raw wire key is not a caller surface.
    assert _reject(_body(num_predict=32)) == {"num_predict": "unknown"}


# --- contract agreement -------------------------------------------------------


def test_every_enabled_path_carries_an_observation_from_ollamas_own_source() -> None:
    plugin = _plugin()
    enabled = {rule.request_path for rule in _rules()}
    observations = plugin.chat_parameter_observations(model=_MODEL, auth_type="none")
    assert {obs.request_path for obs in observations} == enabled
    assert {obs.source for obs in observations} == {"ollama:litellm-chat"}


def test_the_advertised_tool_capability_matches_the_enabled_tools_rule() -> None:
    tools = _plugin().chat_parameter_tools(model=_MODEL, auth_type="none")
    assert [t.tool_type for t in tools] == ["function"]
    assert all(t.gateway_status == "enabled" for t in tools)
