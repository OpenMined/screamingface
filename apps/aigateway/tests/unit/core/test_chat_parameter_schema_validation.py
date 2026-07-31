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


# --- bounded string constraints: pattern + max_length (OME-704) ---------------
#
# WHY these exist: a price ceiling must cross the gateway as an EXACT decimal
# string (a binary JSON float would round the caller's ceiling before it is ever
# validated), so the gateway needs a way to bound a string's SHAPE and LENGTH.
# Neither `enum` nor the numeric bounds can express "non-negative fixed-point
# decimal, at most 64 characters".

_DECIMAL_PATTERN = r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$"


def test_pattern_accepts_a_full_match_and_rejects_a_partial_one() -> None:
    # INVARIANT: full-match semantics. A partial match would let "1abc" through on
    # the strength of its leading "1" — the value then reaches the provider as an
    # unparseable price and the caller's credential has already been spent.
    schema = ParameterSchema(type="string", pattern=_DECIMAL_PATTERN)
    for good in ("0", "1", "10", "0.5", "100.00", "1.000"):
        schema.validate_value(good)  # no raise
    for bad in ("1abc", "abc1", " 1", "1 ", "-1", "1e5", "+1", "01", ".5", "1.", "", "NaN", "inf"):
        with pytest.raises(ParameterValidationError):
            schema.validate_value(bad)


def test_pattern_rejects_a_trailing_newline_despite_the_dollar_anchor() -> None:
    # WHY explicit: Python's `$` also matches just BEFORE a final newline, so a
    # `re.match`-based check would accept "1\n" and forward a whitespace-bearing
    # price. Full-match semantics are what close that gap.
    schema = ParameterSchema(type="string", pattern=_DECIMAL_PATTERN)
    with pytest.raises(ParameterValidationError):
        schema.validate_value("1\n")


def test_max_length_accepts_at_the_bound_and_rejects_above_it() -> None:
    schema = ParameterSchema(type="string", max_length=64)
    schema.validate_value("x" * 64)  # no raise — the bound is INCLUSIVE
    with pytest.raises(ParameterValidationError):
        schema.validate_value("x" * 65)


def test_the_bounded_decimal_schema_rejects_an_over_long_value_before_parsing() -> None:
    # STORY: a caller sends a pathological 10k-digit decimal. It must fail on the
    # length bound, so no unbounded Decimal parse is ever attempted downstream.
    schema = ParameterSchema(type="string", max_length=64, pattern=_DECIMAL_PATTERN)
    longest = "0." + "9" * 62  # exactly 64 characters, and a valid decimal
    assert len(longest) == 64
    schema.validate_value(longest)  # no raise
    with pytest.raises(ParameterValidationError):
        schema.validate_value("0." + "9" * 63)  # 65 characters


def test_string_constraints_are_rendered_into_the_published_json_schema() -> None:
    # The detailed contract is what a client validates against BEFORE sending, so
    # the bound it reads must be the bound the gateway enforces.
    assert ParameterSchema(
        type="string", max_length=64, pattern=_DECIMAL_PATTERN
    ).to_json_schema() == {
        "type": "string",
        "pattern": _DECIMAL_PATTERN,
        "maxLength": 64,
    }


def test_an_invalid_regex_is_a_construction_error() -> None:
    # Fail closed at construction, like every other schema inconsistency: a broken
    # pattern must never become a rule that silently validates nothing.
    with pytest.raises(ValueError):
        ParameterSchema(type="string", pattern="([unclosed")


def test_an_unanchored_pattern_is_a_construction_error() -> None:
    # WHY anchoring is required even though validation full-matches: the pattern is
    # PUBLISHED, and a JSON-Schema consumer applies partial-match semantics to it.
    # An unanchored pattern would therefore mean something LOOSER to every client
    # than it means to the gateway.
    for unanchored in (r"[0-9]+", r"^[0-9]+", r"[0-9]+$"):
        with pytest.raises(ValueError):
            ParameterSchema(type="string", pattern=unanchored)


def test_a_non_positive_max_length_is_a_construction_error() -> None:
    for bad in (-1, 0):
        with pytest.raises(ValueError):
            ParameterSchema(type="string", max_length=bad)


def test_string_constraints_on_a_type_that_cannot_hold_a_string_are_rejected() -> None:
    # A pattern on an integer schema can never fire, so it is a provider-config
    # error rather than a harmless no-op — it reads as protection that is absent.
    with pytest.raises(ValueError):
        ParameterSchema(type="integer", pattern=_DECIMAL_PATTERN)
    with pytest.raises(ValueError):
        ParameterSchema(type="integer", max_length=64)
    with pytest.raises(ValueError):
        ParameterSchema(type="array", item_type="string", max_length=64)


def test_string_constraints_are_allowed_on_a_union_that_admits_strings() -> None:
    schema = ParameterSchema(type=("string", "integer"), pattern=_DECIMAL_PATTERN, max_length=8)
    schema.validate_value("1.5")
    # INVARIANT: the string constraints apply to STRING values only — a non-string
    # member of the union is judged by its own type rules, not by the pattern.
    schema.validate_value(7)
    with pytest.raises(ParameterValidationError):
        schema.validate_value("nope")
