"""OME-583 (§4.2/§9): shared function-calling builders in standard_parameters.

FEATURE: first-class `tools` / `tool_choice` chat parameters. These provider-agnostic
builders are the SINGLE vocabulary each provider selects from — a bounded schema that
gates `tools[].type` / object-form `tool_choice.type` against the provider's advertised
tool types, the rule pair that enables them, and the mirrored observations that keep
every enabled tool path fully evidenced.

INVARIANT (§4.2): these builders name NO provider; the caller passes its own tool
capabilities and source label, so enabling function calling stays a provider-local edit.
INVARIANT (§4.4): observations mirror the ruled paths exactly — an enabled tool param is
never left blank, and an unruled one is never fabricated.
"""

from __future__ import annotations

import pytest

from aigateway.core.chat_parameters import (
    GatewayStatus,
    ParameterValidationError,
    ToolCapability,
)
from aigateway.core.standard_parameters import (
    N_SCHEMA,
    PENALTY_SCHEMA,
    RESPONSE_FORMAT_SCHEMA,
    SEED_SCHEMA,
    direct_parameter_observations,
    function_calling_rules,
    tool_choice_schema,
    tool_parameter_observations,
    tools_schema,
)


def _function_cap(status: GatewayStatus = "enabled") -> ToolCapability:
    return ToolCapability(tool_type="function", provider_support="supported", gateway_status=status)


# --- tools_schema: array[object] gated by the tools[].type discriminator -----


def test_tools_schema_accepts_the_openai_function_tool_array() -> None:
    schema = tools_schema(("function",))
    # the OpenAI shape a caller sends (and the probe fed every provider transform).
    schema.validate_value([{"type": "function", "function": {"name": "get_weather"}}])


def test_tools_schema_rejects_an_unadvertised_tool_type() -> None:
    # a type the provider never advertised fails closed at the discriminator.
    schema = tools_schema(("function",))
    with pytest.raises(ParameterValidationError):
        schema.validate_value([{"type": "web_search"}])


def test_tools_schema_rejects_an_item_without_a_type() -> None:
    # an OpenAI tool MUST carry type:"function"; a typeless item is malformed, not
    # silently allowed (fail closed).
    schema = tools_schema(("function",))
    with pytest.raises(ParameterValidationError):
        schema.validate_value([{"function": {"name": "x"}}])


def test_tools_schema_rejects_a_non_array() -> None:
    schema = tools_schema(("function",))
    with pytest.raises(ParameterValidationError):
        schema.validate_value({"type": "function"})


def test_tools_schema_renders_a_structural_array_json_schema() -> None:
    rendered = tools_schema(("function",)).to_json_schema()
    assert rendered["type"] == "array"
    assert rendered["items"] == {"type": "object"}
    # the discriminator is a gateway-side constraint, advertised in the tools section
    # (supported_tools), NOT duplicated into the published parameter shape.
    assert "enum" not in rendered


# --- tool_choice_schema: string | object, object gated by type ---------------


def test_tool_choice_schema_accepts_string_and_object_forms() -> None:
    schema = tool_choice_schema(("function",))
    schema.validate_value("auto")  # string form: discriminator skipped
    schema.validate_value("required")
    schema.validate_value({"type": "function", "function": {"name": "get_weather"}})


def test_tool_choice_schema_rejects_an_unadvertised_object_type() -> None:
    schema = tool_choice_schema(("function",))
    with pytest.raises(ParameterValidationError):
        schema.validate_value({"type": "web_search"})


def test_tool_choice_schema_renders_a_string_object_union() -> None:
    assert tool_choice_schema(("function",)).to_json_schema()["type"] == ["string", "object"]


# --- function_calling_rules: the rule pair, empty when nothing is enabled -----


def test_function_calling_rules_emit_tools_and_tool_choice_by_default() -> None:
    rules = function_calling_rules(
        (_function_cap(),), auth_modes=("api_key",), projection_revision="r1"
    )
    by_path = {rule.request_path: rule for rule in rules}
    assert set(by_path) == {"tools", "tool_choice"}
    for rule in rules:
        assert rule.projection_kind == "direct"
        assert rule.parameter_schema is not None  # every enabled param carries a schema
        assert rule.applicable_auth_modes == ("api_key",)


def test_function_calling_rules_can_omit_tool_choice() -> None:
    # Gemini's builder maps tools[] but emits no tool-selection control (§9), so it
    # enables tools ONLY — no dishonest tool_choice advertisement.
    rules = function_calling_rules(
        (_function_cap(),),
        auth_modes=("api_key", "oauth"),
        projection_revision="r1",
        tool_choice=False,
    )
    assert {rule.request_path for rule in rules} == {"tools"}


def test_function_calling_rules_are_empty_without_an_enabled_tool_type() -> None:
    # no phantom rules: no capabilities, or only a disabled one, yields no rule.
    assert function_calling_rules((), auth_modes=("api_key",), projection_revision="r1") == ()
    disabled = _function_cap("disabled")
    assert (
        function_calling_rules((disabled,), auth_modes=("api_key",), projection_revision="r1") == ()
    )


def test_function_calling_rules_schema_gates_the_tools_type() -> None:
    (tools_rule,) = [
        rule
        for rule in function_calling_rules(
            (_function_cap(),), auth_modes=("api_key",), projection_revision="r1"
        )
        if rule.request_path == "tools"
    ]
    assert tools_rule.parameter_schema is not None
    with pytest.raises(ParameterValidationError):
        tools_rule.parameter_schema.validate_value([{"type": "code_interpreter"}])


# --- tool_parameter_observations: mirror the ruled paths, fully evidenced -----


def test_tool_parameter_observations_mirror_the_ruled_paths() -> None:
    obs = tool_parameter_observations((_function_cap(),), source="prov:static")
    assert {o.request_path for o in obs} == {"tools", "tool_choice"}
    for observation in obs:
        assert observation.support == "supported"
        assert observation.source == "prov:static"


def test_tool_parameter_observations_honor_the_tool_choice_flag() -> None:
    only_tools = tool_parameter_observations(
        (_function_cap(),), source="prov:static", tool_choice=False
    )
    assert {o.request_path for o in only_tools} == {"tools"}


def test_tool_parameter_observations_are_empty_without_an_enabled_tool_type() -> None:
    assert tool_parameter_observations((), source="prov:static") == ()
    assert tool_parameter_observations((_function_cap("disabled"),), source="prov:static") == ()


# --- OME-584: RESPONSE_FORMAT_SCHEMA — object gated by the type discriminator --


def test_response_format_schema_accepts_the_documented_openai_forms() -> None:
    # the three documented OpenAI response_format types the OpenAI-compatible routers accept.
    RESPONSE_FORMAT_SCHEMA.validate_value({"type": "text"})
    RESPONSE_FORMAT_SCHEMA.validate_value({"type": "json_object"})
    RESPONSE_FORMAT_SCHEMA.validate_value(
        {
            "type": "json_schema",
            "json_schema": {"name": "weather", "schema": {"type": "object"}},
        }
    )


def test_response_format_schema_rejects_an_unknown_type() -> None:
    # an unknown response-format type fails closed at the discriminator (not silently
    # forwarded) — the gateway gates the shape, the provider validates the rest.
    with pytest.raises(ParameterValidationError):
        RESPONSE_FORMAT_SCHEMA.validate_value({"type": "xml"})


def test_response_format_schema_rejects_a_typeless_object() -> None:
    # OpenAI requires response_format.type; a typeless object is malformed.
    with pytest.raises(ParameterValidationError):
        RESPONSE_FORMAT_SCHEMA.validate_value({"json_schema": {"name": "x"}})


def test_response_format_schema_rejects_a_non_object() -> None:
    # response_format is an object, never a bare string — a scalar fails closed.
    with pytest.raises(ParameterValidationError):
        RESPONSE_FORMAT_SCHEMA.validate_value("json_object")


def test_response_format_schema_renders_a_structural_object_json_schema() -> None:
    rendered = RESPONSE_FORMAT_SCHEMA.to_json_schema()
    assert rendered["type"] == "object"
    # the discriminator is a gateway-side constraint, not part of the published shape.
    assert "enum" not in rendered


# --- direct_parameter_observations: evidence for non-sampling ruled fields -----


def test_direct_parameter_observations_build_one_observation_per_path() -> None:
    obs = direct_parameter_observations(("response_format", "n"), source="prov:static")
    assert {o.request_path for o in obs} == {"response_format", "n"}
    for observation in obs:
        assert observation.support == "supported"
        assert observation.source == "prov:static"


def test_direct_parameter_observations_are_empty_for_no_paths() -> None:
    assert direct_parameter_observations((), source="prov:static") == ()


# --- OME-585: SEED_SCHEMA (any integer) and N_SCHEMA (integer >= 1) -----------


def test_seed_schema_accepts_any_integer() -> None:
    # OpenAI `seed` is an arbitrary integer — the gateway does not narrow the range
    # (including 0 and negatives), so it never rejects a value the provider would accept.
    SEED_SCHEMA.validate_value(0)
    SEED_SCHEMA.validate_value(42)
    SEED_SCHEMA.validate_value(-7)


def test_seed_schema_rejects_a_non_integer() -> None:
    # a float is not an integer seed — fails closed as malformed at classification.
    with pytest.raises(ParameterValidationError):
        SEED_SCHEMA.validate_value(1.5)


def test_n_schema_accepts_one_or_more() -> None:
    N_SCHEMA.validate_value(1)  # inclusive lower bound
    N_SCHEMA.validate_value(4)


def test_n_schema_rejects_zero() -> None:
    # `n` is the number of choices to return; 0 is below the minimum of 1.
    with pytest.raises(ParameterValidationError):
        N_SCHEMA.validate_value(0)


def test_n_schema_rejects_a_non_integer() -> None:
    with pytest.raises(ParameterValidationError):
        N_SCHEMA.validate_value(2.5)


# --- OME-586: PENALTY_SCHEMA (number in the OpenAI-compatible [-2, 2] range) --


def test_penalty_schema_accepts_the_inclusive_bounds_and_zero() -> None:
    # frequency_penalty / presence_penalty share OpenAI's [-2, 2] range; both bounds
    # are inclusive and the neutral 0 is valid.
    PENALTY_SCHEMA.validate_value(-2)
    PENALTY_SCHEMA.validate_value(0)
    PENALTY_SCHEMA.validate_value(2)
    PENALTY_SCHEMA.validate_value(0.5)


def test_penalty_schema_rejects_out_of_range() -> None:
    # a value just outside the documented range fails closed as malformed at
    # classification — the gateway advertises and enforces the provider's real bound.
    with pytest.raises(ParameterValidationError):
        PENALTY_SCHEMA.validate_value(2.0001)
    with pytest.raises(ParameterValidationError):
        PENALTY_SCHEMA.validate_value(-2.0001)


def test_penalty_schema_rejects_a_non_number() -> None:
    with pytest.raises(ParameterValidationError):
        PENALTY_SCHEMA.validate_value("high")
