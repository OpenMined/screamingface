"""OME-634: Codex's enabled rule, proven into the Responses payload.

FEATURE: caller parameter support for Codex. The plugin shipped NO rules, and the
classifier is fail-closed, so a caller's ``reasoning_effort`` was rejected BEFORE
``prepare_chat_body`` ran — making the plugin's own conversion of that field
structurally unreachable. This restores it with the rule the conversion always
needed.

STORY: as a caller on a Codex OAuth profile, the reasoning effort I ask for reaches
the Responses payload; the sampling fields Codex cannot honor are refused with a
safe 400 rather than silently dropped on the way to the wire.

INVARIANT (§9 "Projection"): Codex's final transform is ``_build_payload``, which
copies a FIXED set of keys out of optional_params and drops the rest. A rule is
earned only by proving the value survives that copy — the tests below assert on the
payload dict itself, not on a handler kwarg.
INVARIANT: Codex is NOT OpenAI. It rides the ChatGPT subscription Responses endpoint,
whose accepted surface is much narrower than Chat Completions; the gateway reports
that difference instead of papering over it.
"""

from __future__ import annotations

import pytest

from aigateway.core.parameter_projection import (
    UnsupportedParametersError,
    classify_and_project_chat_parameters,
)
from aigateway.plugins.codex_provider.chat_handler import _build_payload
from aigateway.plugins.codex_provider.plugin import CodexProviderPlugin

_MODEL = "codex/gpt-5.3-codex"
_MESSAGES = [{"role": "user", "content": "hi"}]
# Mirrors plugin.chat_completion's optional_params harvest.
_OPTIONAL_EXCLUDES = {"model", "messages", "api_key", "extra_headers", "timeout"}
_TOOL = {"type": "function", "function": {"name": "get_weather", "parameters": {}}}


def _plugin() -> CodexProviderPlugin:
    return CodexProviderPlugin()


def _rules():
    return _plugin().chat_parameter_rules(model=_MODEL, auth_type="oauth")


def _projected(caller_body: dict) -> dict:
    plugin = _plugin()
    projected = classify_and_project_chat_parameters(
        plugin.strip_provider_dispatch_controls(caller_body),
        rules=plugin.chat_parameter_rules(model=_MODEL, auth_type="oauth"),
        auth_mode="oauth",
    )
    return plugin.prepare_chat_body(projected)


def _payload(caller_body: dict) -> dict:
    # The full dispatch path: classify → prepare_chat_body (reasoning_effort →
    # reasoning) → optional_params harvest → _build_payload, the Responses body.
    prepared = _projected(caller_body)
    optional_params = {k: v for k, v in prepared.items() if k not in _OPTIONAL_EXCLUDES}
    return _build_payload(prepared["model"], prepared["messages"], optional_params)


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


def test_reasoning_effort_is_the_only_enabled_path() -> None:
    # Deliberately narrow: it is the ONLY standard caller field _build_payload carries
    # to the wire. Anything broader would accept a value and drop it silently.
    assert {rule.request_path for rule in _rules()} == {"reasoning_effort"}


def test_the_rule_is_oauth_only() -> None:
    # The Responses endpoint accepts subscription OAuth tokens only — the handler
    # rejects sk-/sk-proj- keys outright — so there is no api-key mode to rule for.
    (rule,) = _rules()
    assert tuple(rule.applicable_auth_modes) == ("oauth",)


# --- the wire payload ---------------------------------------------------------


@pytest.mark.parametrize("effort", ["none", "minimal", "low", "medium", "high"])
def test_caller_reasoning_effort_reaches_the_responses_payload(effort: str) -> None:
    # The regression this unit undoes: classification used to reject the field before
    # prepare_chat_body could convert it, so the conversion was dead code.
    payload = _payload({"model": _MODEL, "messages": _MESSAGES, "reasoning_effort": effort})
    assert payload["reasoning"] == {"effort": effort}


def test_an_off_ladder_reasoning_effort_fails_closed() -> None:
    assert _reject({"model": _MODEL, "messages": _MESSAGES, "reasoning_effort": "turbo"}) == {
        "reasoning_effort": "malformed"
    }


def test_the_payload_still_carries_no_sampling_keys() -> None:
    # The reason sampling is NOT ruled, pinned as a characterization: even handed
    # these keys directly, the final transform drops them. A rule would therefore
    # promise the caller something the wire never sees.
    payload = _build_payload(
        _MODEL, _MESSAGES, {"temperature": 0.7, "top_p": 0.9, "max_tokens": 128}
    )
    assert not {"temperature", "top_p", "max_tokens"} & set(payload)


# --- still fail-closed --------------------------------------------------------


@pytest.mark.parametrize("field", ["temperature", "top_p", "max_tokens", "stop", "seed"])
def test_sampling_fields_the_transform_drops_are_refused_not_silently_dropped(
    field: str,
) -> None:
    assert _reject({"model": _MODEL, "messages": _MESSAGES, field: 1}) == {field: "unknown"}


def test_tools_stay_unsupported_pending_a_responses_shape_adapter() -> None:
    # _build_payload copies `tools` VERBATIM into a Responses payload, but the shapes
    # differ: Chat Completions nests the definition under "function", the Responses
    # API expects it flattened beside "type". Verbatim forwarding would put an
    # unreadable shape on the wire, so function calling is not advertised yet.
    assert _reject({"model": _MODEL, "messages": _MESSAGES, "tools": [_TOOL]}) == {
        "tools": "unknown"
    }
    assert _plugin().chat_parameter_tools(model=_MODEL, auth_type="oauth") == ()


def test_a_caller_native_responses_field_cannot_be_smuggled() -> None:
    # previous_response_id is copied by the transform but is structurally dead: the
    # payload hardcodes store=False, so no response is ever persisted to continue from.
    rejected = _reject({"model": _MODEL, "messages": _MESSAGES, "previous_response_id": "resp_123"})
    assert rejected == {"previous_response_id": "unknown"}
    assert _build_payload(_MODEL, _MESSAGES, {})["store"] is False


# --- contract agreement -------------------------------------------------------


def test_the_enabled_path_carries_a_provider_observation() -> None:
    observations = _plugin().chat_parameter_observations(model=_MODEL, auth_type="oauth")
    assert {obs.request_path for obs in observations} == {"reasoning_effort"}
    assert {obs.source for obs in observations} == {"codex:responses"}


def test_codex_advertises_no_tool_capability() -> None:
    # Drives the /v1/models supported_tools summary as well as the detail contract:
    # an empty capability set means the gateway claims no function calling here.
    assert _plugin().chat_parameter_tools(model=_MODEL, auth_type="oauth") == ()
