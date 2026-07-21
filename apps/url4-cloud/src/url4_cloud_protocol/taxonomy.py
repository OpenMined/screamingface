"""Taxonomy payloads — OTel gen_ai token usage + USD cost (docs/protocol.md §5.1, §5.3)."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# WHY: validation_alias + serialization_alias (not `alias`) so the JSON wire uses the OTel
# `gen_ai.usage.*` keys while Python constructs/type-checks by the field name (populate_by_name).


class TokenUsage(BaseModel):
    """Token counts, keyed by OTel GenAI ``gen_ai.usage.*`` on the wire (docs/protocol.md §5.1)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, use_attribute_docstrings=True)

    input_tokens: int = Field(
        default=0,
        validation_alias="gen_ai.usage.input_tokens",
        serialization_alias="gen_ai.usage.input_tokens",
    )
    output_tokens: int = Field(
        default=0,
        validation_alias="gen_ai.usage.output_tokens",
        serialization_alias="gen_ai.usage.output_tokens",
    )
    cache_read_tokens: int = Field(
        default=0,
        validation_alias="gen_ai.usage.cache_read_tokens",
        serialization_alias="gen_ai.usage.cache_read_tokens",
    )
    cache_creation_tokens: int = Field(
        default=0,
        validation_alias="gen_ai.usage.cache_creation_tokens",
        serialization_alias="gen_ai.usage.cache_creation_tokens",
    )
    reasoning_tokens: int = Field(
        default=0,
        validation_alias="gen_ai.usage.reasoning_tokens",
        serialization_alias="gen_ai.usage.reasoning_tokens",
    )


class CostBreakdown(BaseModel):
    """USD cost per usage type; ``total_usd`` == Σ parts (docs/protocol.md §5.3)."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)

    input_usd: Decimal = Decimal("0")
    output_usd: Decimal = Decimal("0")
    cache_read_usd: Decimal = Decimal("0")
    cache_creation_usd: Decimal = Decimal("0")
    reasoning_usd: Decimal = Decimal("0")
    total_usd: Decimal
    """Sum of the per-type costs — enforced by the validator below."""

    @model_validator(mode="after")
    def _total_is_sum(self) -> "CostBreakdown":
        # INVARIANT: total_usd == Σ parts — makes an illogical cost impossible to construct.
        parts = (
            self.input_usd
            + self.output_usd
            + self.cache_read_usd
            + self.cache_creation_usd
            + self.reasoning_usd
        )
        if self.total_usd != parts:
            raise ValueError(f"total_usd {self.total_usd} != Σ parts {parts}")
        return self


class ErrorInfo(BaseModel):
    """A serialized failure; mirrors url4 ``Url4Error`` (docs/protocol.md §5.4)."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    code: str
    message: str
    permanent: bool = False
