"""OME-479 gateway-owned value validation — the ``ParameterSchema`` half.

FEATURE: effective model-capability contract. This module owns the ONE type that
decides whether a caller-supplied value is admissible, plus the vocabulary that
type is expressed in: the schema type enums, the per-type predicates, and the
validation error.

INVARIANT: validation is gateway-owned and dependency-free (no jsonschema). A
value is admitted only by a schema a provider rule declared — never by its
presence, never by provider support, never by a default.

INVARIANT: nothing here reads or writes provider state, and the type is frozen
and ``extra="forbid"``, so a malformed schema fails closed at CONSTRUCTION
rather than admitting a wrong value at request time.

AIDEV-NOTE (OME-704): split out of ``._types`` when the string constraints
(``pattern`` / ``max_length``) pushed that file past the repository's 450-line
limit — the same reason ``._algebra`` was split out under OME-602. The dependency
runs one way: ``._types`` imports ``ParameterSchema`` from here, never the
reverse. Import these from the ``chat_parameters`` PACKAGE, never from this
module directly; the split between halves is an implementation detail.
"""

from __future__ import annotations

import math
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator


class ParameterValidationError(ValueError):
    """A caller-supplied value violates its gateway-owned schema."""


# Type names ParameterSchema can validate. A tuple of these expresses a
# TOP-LEVEL union (e.g. ``stop`` is string | array[string]); "object" and
# "array" are structural container types.
SchemaType = Literal["number", "integer", "string", "boolean", "array", "object"]
SchemaItemType = Literal["number", "integer", "string", "boolean", "object"]

# INVARIANT: bool subclasses int, so a boolean must never satisfy a numeric schema.
# Single source of per-type predicates, shared by top-level and array-item checks.
_TYPE_PREDICATES: dict[str, Any] = {
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "string": lambda v: isinstance(v, str),
    "array": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}


def _is_non_finite_float(value: Any) -> bool:
    return isinstance(value, float) and not math.isfinite(value)


class ParameterSchema(BaseModel):
    """A bounded, gateway-owned validation schema for one request path.

    Deliberately small and dependency-free (no jsonschema): enough to validate
    the OpenAI-compatible params the gateway forwards — scalars, typed arrays,
    top-level objects, and top-level type UNIONS (e.g. ``stop`` is string |
    array[string]) — and to render a JSON-Schema fragment for the detailed
    contract.

    INVARIANT (shallow by design): validation proves the TOP-LEVEL shape and,
    for objects / array items, an optional single-key discriminator (used to
    gate ``tools[].type`` and object-form ``tool_choice`` against a provider's
    enabled tool types). Nested function definitions, JSON-Schema bodies, and
    tool names are LiteLLM/provider concerns and are intentionally NOT modelled.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # A single type, or a tuple of types for a top-level union.
    type: SchemaType | tuple[SchemaType, ...]
    minimum: float | None = None
    maximum: float | None = None
    enum: tuple[str, ...] | None = None
    item_type: SchemaItemType | None = None
    # Bounded STRING constraints (OME-704). WHY they exist: a value whose exactness
    # matters — a decimal price ceiling that a binary JSON float would round before
    # validation ever ran — must cross the gateway as a string, and neither ``enum``
    # nor the numeric bounds can express "non-negative fixed-point decimal, at most
    # 64 characters". Applied to string values only; a non-string member of a union
    # is judged by its own type rules.
    pattern: str | None = None
    max_length: int | None = None
    # Optional single-key discriminator: when the value (or each array item) is an
    # object, its ``object_discriminator`` key must be in ``object_discriminator_enum``
    # (gates tools[].type fail-closed). Both fields are set together, or neither.
    object_discriminator: str | None = None
    object_discriminator_enum: tuple[str, ...] | None = None

    @model_validator(mode="after")
    def _check_schema_consistency(self) -> ParameterSchema:
        # INVARIANT: a schema that can match nothing, or a half-specified
        # discriminator, is a provider-config error — fail closed at construction.
        if isinstance(self.type, tuple) and not self.type:
            raise ValueError("type union must be non-empty")
        has_disc = self.object_discriminator is not None
        has_enum = self.object_discriminator_enum is not None
        if has_disc != has_enum:
            raise ValueError(
                "object_discriminator and object_discriminator_enum must be set together"
            )
        if has_disc:
            if not self.object_discriminator_enum:
                raise ValueError("object_discriminator_enum must be non-empty")
            # A discriminator only means something when the value or its items
            # can be an object.
            if "object" not in self._type_options and self.item_type != "object":
                raise ValueError("object_discriminator requires an object-capable type")
        self._check_string_constraints()
        return self

    def _check_string_constraints(self) -> None:
        # INVARIANT: a string constraint that can never fire is a provider-config
        # error, not a harmless no-op — it reads as protection that is absent.
        if (self.pattern is not None or self.max_length is not None) and (
            "string" not in self._type_options
        ):
            raise ValueError("pattern/max_length require a string-capable type")
        if self.max_length is not None and self.max_length < 1:
            raise ValueError("max_length must be positive")
        if self.pattern is None:
            return
        # WHY anchoring is REQUIRED even though validation full-matches: this pattern
        # is PUBLISHED in the detailed contract, and a JSON-Schema consumer applies
        # partial-match semantics to it. Unanchored, it would mean something looser
        # to every client than it means to the gateway.
        if not (self.pattern.startswith("^") and self.pattern.endswith("$")):
            raise ValueError(f"pattern must be anchored with ^ and $: {self.pattern!r}")
        try:
            re.compile(self.pattern)
        except re.error as exc:
            raise ValueError(f"invalid pattern: {exc}") from exc

    @property
    def _type_options(self) -> tuple[str, ...]:
        return (self.type,) if isinstance(self.type, str) else self.type

    def to_json_schema(self) -> dict[str, Any]:
        rendered_type: Any = self.type if isinstance(self.type, str) else list(self.type)
        out: dict[str, Any] = {"type": rendered_type}
        if self.minimum is not None:
            out["minimum"] = self.minimum
        if self.maximum is not None:
            out["maximum"] = self.maximum
        if self.enum is not None:
            out["enum"] = list(self.enum)
        if self.item_type is not None:
            out["items"] = {"type": self.item_type}
        if self.pattern is not None:
            out["pattern"] = self.pattern
        if self.max_length is not None:
            out["maxLength"] = self.max_length
        # WHY: the discriminator is a gateway-side validation constraint, not part
        # of the published shape — the allowed values (e.g. a provider's enabled
        # tool types) are advertised in the contract's own tools section, so
        # embedding them here too would duplicate the source of truth. Keep the
        # rendered fragment purely structural.
        return out

    def validate_value(self, value: Any) -> None:
        """Raise ParameterValidationError when ``value`` violates this schema."""
        options = self._type_options
        if not any(_TYPE_PREDICATES[name](value) for name in options):
            raise ParameterValidationError(f"expected one of {options}")
        # INVARIANT: range checks are fail-open for NaN, and unbounded numeric
        # schemas also admit infinities. Reject every non-finite float first.
        if _is_non_finite_float(value):
            raise ParameterValidationError("not a finite number")
        if isinstance(value, list):
            self._validate_items(value)
            if self.item_type == "object" and self.object_discriminator is not None:
                for item in value:
                    self._check_discriminator(item)
        elif isinstance(value, dict) and self.object_discriminator is not None:
            self._check_discriminator(value)
        if isinstance(value, str):
            self._validate_string(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if self.minimum is not None and value < self.minimum:
                raise ParameterValidationError("below minimum")
            if self.maximum is not None and value > self.maximum:
                raise ParameterValidationError("above maximum")
        if self.enum is not None and value not in self.enum:
            raise ParameterValidationError("not an allowed value")

    def _validate_string(self, value: str) -> None:
        # INVARIANT: LENGTH is checked before the PATTERN, so a pathological value is
        # bounded before the regex engine ever sees it.
        if self.max_length is not None and len(value) > self.max_length:
            raise ParameterValidationError("longer than the maximum length")
        # WHY fullmatch rather than match: a partial match would admit "1abc" on the
        # strength of its leading "1". ``re`` caches the compiled pattern internally,
        # and construction already proved it compiles.
        if self.pattern is not None and re.fullmatch(self.pattern, value) is None:
            raise ParameterValidationError("does not match the required pattern")

    def _check_discriminator(self, obj: dict[str, Any]) -> None:
        # obj is a dict; key/enum set together (construction guard); guard narrows type.
        key = self.object_discriminator
        allowed = self.object_discriminator_enum
        if key is None or allowed is None:
            return
        if obj.get(key) not in allowed:
            raise ParameterValidationError("object discriminator value not allowed")

    def _validate_items(self, value: list[Any]) -> None:
        if self.item_type is None:
            return
        check = _TYPE_PREDICATES[self.item_type]
        if not all(check(item) for item in value):
            raise ParameterValidationError("array item has wrong type")
        if self.item_type == "number" and any(_is_non_finite_float(item) for item in value):
            raise ParameterValidationError("array item is not a finite number")
