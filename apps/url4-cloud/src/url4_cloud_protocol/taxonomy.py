"""Taxonomy models — tokens + USD cost (spec §7, §8). Money is Decimal; cost = Σ its parts."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, model_validator


class TokenUsage(BaseModel):
    """Token counts for one node's model call (OTel gen_ai usage)."""

    model_config = ConfigDict(extra="forbid", use_attribute_docstrings=True)

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    reasoning_tokens: int = 0


class CostBreakdown(BaseModel):
    """USD cost per usage type; ``total_usd`` MUST equal the sum of its parts (spec §8)."""

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
    """A serialized failure; mirrors url4 ``Url4Error`` so Guard semantics survive (spec §7)."""

    model_config = ConfigDict(use_attribute_docstrings=True)

    code: str
    """Stable error code (== ``Url4Error.code``)."""
    message: str
    permanent: bool = False
    """Whether the failure is permanent (== ``Url4Error.permanent``); drives Guard retry."""
