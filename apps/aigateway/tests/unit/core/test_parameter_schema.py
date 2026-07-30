"""OME-581: ParameterSchema gains object + top-level union + object-discriminator.

FEATURE: the effective parameter contract must describe the standard structured
OpenAI-compatible fields the gateway forwards — stop (string|array), tools
(array[object]), tool_choice (string|object), response_format (object) — and gate
a tool-type discriminator. This validation stays DELIBERATELY SHALLOW: the schema
proves the top-level shape and the tool-type discriminator; nested function/JSON
Schema bodies and tool names are LiteLLM/provider concerns.

INVARIANT: enabling a structured field is impossible until the schema can describe
it (the detailed contract requires a non-null schema for every enabled param), so
this core capability is the prerequisite for provider enablement — and it enables
NO provider on its own.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from aigateway.core.chat_parameters import ParameterSchema, ParameterValidationError

# --- object type -------------------------------------------------------------


def test_object_type_accepts_dict_rejects_non_dict() -> None:
    schema = ParameterSchema(type="object")  # response_format shape
    schema.validate_value({"type": "json_object"})  # ok
    for bad in (5, "x", [], True):
        with pytest.raises(ParameterValidationError):
            schema.validate_value(bad)


def test_to_json_schema_renders_object() -> None:
    assert ParameterSchema(type="object").to_json_schema() == {"type": "object"}


# --- top-level type union: string | array[string]  (stop) --------------------


def test_string_or_array_union_accepts_both_forms() -> None:
    schema = ParameterSchema(type=("string", "array"), item_type="string")
    schema.validate_value("STOP")
    schema.validate_value(["a", "b"])


def test_string_or_array_union_rejects_wrong_types() -> None:
    schema = ParameterSchema(type=("string", "array"), item_type="string")
    with pytest.raises(ParameterValidationError):
        schema.validate_value(5)  # neither string nor array
    with pytest.raises(ParameterValidationError):
        schema.validate_value([1])  # array item is not a string


def test_to_json_schema_renders_union_as_type_array() -> None:
    schema = ParameterSchema(type=("string", "array"), item_type="string")
    assert schema.to_json_schema() == {"type": ["string", "array"], "items": {"type": "string"}}


# --- array[object] + discriminator  (tools) ----------------------------------


def _tools_schema() -> ParameterSchema:
    return ParameterSchema(
        type="array",
        item_type="object",
        object_discriminator="type",
        object_discriminator_enum=("function",),
    )


def test_array_of_objects_accepts_allowed_tool_type() -> None:
    _tools_schema().validate_value([{"type": "function", "function": {"name": "f"}}])


def test_array_of_objects_rejects_non_object_item() -> None:
    with pytest.raises(ParameterValidationError):
        _tools_schema().validate_value([1])


def test_array_of_objects_rejects_disallowed_discriminator_per_item() -> None:
    with pytest.raises(ParameterValidationError):
        _tools_schema().validate_value([{"type": "web_search"}])  # not enabled


def test_array_of_objects_rejects_item_missing_discriminator() -> None:
    with pytest.raises(ParameterValidationError):
        _tools_schema().validate_value([{"function": {"name": "f"}}])  # no "type"


def test_to_json_schema_renders_array_of_objects() -> None:
    # The discriminator enum is NOT embedded here — allowed tool types are advertised
    # in the contract's tools section (DRY); the schema fragment stays structural.
    assert _tools_schema().to_json_schema() == {"type": "array", "items": {"type": "object"}}


# --- string | object + discriminator  (tool_choice) --------------------------


def _tool_choice_schema() -> ParameterSchema:
    return ParameterSchema(
        type=("string", "object"),
        object_discriminator="type",
        object_discriminator_enum=("function",),
    )


def test_string_or_object_union_accepts_string_and_allowed_object() -> None:
    schema = _tool_choice_schema()
    schema.validate_value("auto")  # string form: no discriminator check
    schema.validate_value({"type": "function", "function": {"name": "f"}})


def test_string_or_object_union_rejects_disallowed_object_and_scalar() -> None:
    schema = _tool_choice_schema()
    with pytest.raises(ParameterValidationError):
        schema.validate_value({"type": "web_search"})  # object discriminator not enabled
    with pytest.raises(ParameterValidationError):
        schema.validate_value({})  # object missing discriminator
    with pytest.raises(ParameterValidationError):
        schema.validate_value(5)  # neither string nor object


def test_to_json_schema_renders_string_object_union() -> None:
    assert _tool_choice_schema().to_json_schema() == {"type": ["string", "object"]}


# --- construction guards (fail closed) ---------------------------------------


def test_discriminator_without_enum_is_rejected_at_construction() -> None:
    with pytest.raises(ValidationError):
        ParameterSchema(type="object", object_discriminator="type")


def test_discriminator_on_non_object_capable_type_is_rejected() -> None:
    # A discriminator only makes sense when the value (or its items) can be an object.
    with pytest.raises(ValidationError):
        ParameterSchema(
            type="number", object_discriminator="type", object_discriminator_enum=("function",)
        )


# --- backward compatibility: existing scalar behavior is preserved -----------


def test_scalar_number_schema_still_rejects_bool_and_enforces_bounds() -> None:
    schema = ParameterSchema(type="number", minimum=0, maximum=1)
    schema.validate_value(0.5)
    with pytest.raises(ParameterValidationError):
        schema.validate_value(True)  # bool is not a number
    with pytest.raises(ParameterValidationError):
        schema.validate_value(1.5)  # above maximum
