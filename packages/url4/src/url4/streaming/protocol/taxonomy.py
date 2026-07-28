from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TokenUsage(BaseModel):
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
    model_config = ConfigDict(use_attribute_docstrings=True)

    code: str
    message: str
    permanent: bool = False
