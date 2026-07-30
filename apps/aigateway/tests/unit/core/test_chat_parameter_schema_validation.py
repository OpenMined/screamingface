"""OME-581: ``ParameterSchema`` is the fail-closed value-validation point.

FEATURE: one effective parameter contract. Every caller-supplied value that a
rule admits is checked against the rule's schema here — this is the single place
where "the provider advertises this field" becomes "and this particular value is
acceptable".

INVARIANT: validation is fail-closed and TYPE-EXACT. A bool is not a number, an
int is not a bool, and a float is not an integer, even though Python's own
``isinstance`` would happily say otherwise for the first two. A permissive check
here would let a value through the gateway that the provider then rejects, after
the caller's credential has already been read.

The rule value object, normalization, the inline summary, tool types, the
detailed contract overlay and the transport capabilities live in
``test_chat_parameter_contract``.
"""

from __future__ import annotations

import pytest

from aigateway.core.chat_parameters import ParameterSchema, ParameterValidationError


def test_parameter_schema_validates_values_within_bounds() -> None:
    schema = ParameterSchema(type="number", minimum=0, maximum=2)
    schema.validate_value(1.5)  # no raise
    with pytest.raises(ValueError):
        schema.validate_value(2.5)
    with pytest.raises(ValueError):
        schema.validate_value("hot")


# --- schema value validation: full type matrix (fail-closed enforcement point) ---
#
# WHY: validate_value is where the gateway rejects an out-of-contract client
# value BEFORE dispatch. An untested type branch is a silent fail-OPEN gap, so
# every declared type is proven for both an accepted and a rejected value.


def test_number_schema_rejects_bool_disguised_as_number() -> None:
    # INVARIANT: bool is a subclass of int; True must never satisfy `number`.
    schema = ParameterSchema(type="number", minimum=0, maximum=2)
    with pytest.raises(ParameterValidationError):
        schema.validate_value(True)


def test_integer_schema_accepts_int_and_rejects_float_bool_string() -> None:
    schema = ParameterSchema(type="integer", minimum=1, maximum=100)
    schema.validate_value(40)  # no raise (P0 provider_params.top_k shape)
    for bad in (1.5, True, "40"):
        with pytest.raises(ParameterValidationError):
            schema.validate_value(bad)
    with pytest.raises(ParameterValidationError):
        schema.validate_value(0)  # below minimum
    with pytest.raises(ParameterValidationError):
        schema.validate_value(101)  # above maximum


def test_boolean_schema_accepts_bool_and_rejects_int() -> None:
    schema = ParameterSchema(type="boolean")
    schema.validate_value(True)
    schema.validate_value(False)
    for bad in (1, 0, "true"):
        with pytest.raises(ParameterValidationError):
            schema.validate_value(bad)


def test_string_enum_schema_accepts_member_and_rejects_others() -> None:
    schema = ParameterSchema(type="string", enum=("low", "medium", "high"))
    schema.validate_value("medium")
    for bad in ("extreme", 3, "LOW"):
        with pytest.raises(ParameterValidationError):
            schema.validate_value(bad)


def test_array_schema_validates_membership_and_item_type() -> None:
    schema = ParameterSchema(type="array", item_type="string")
    schema.validate_value(["a", "b"])
    schema.validate_value([])  # empty array is valid
    with pytest.raises(ParameterValidationError):
        schema.validate_value("not-a-list")
    with pytest.raises(ParameterValidationError):
        schema.validate_value(["a", 2])  # heterogeneous item type


def test_to_json_schema_renders_enum_and_array_item_type() -> None:
    assert ParameterSchema(type="string", enum=("a", "b")).to_json_schema() == {
        "type": "string",
        "enum": ["a", "b"],
    }
    assert ParameterSchema(type="array", item_type="number").to_json_schema() == {
        "type": "array",
        "items": {"type": "number"},
    }
