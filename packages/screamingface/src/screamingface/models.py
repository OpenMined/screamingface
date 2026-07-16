"""Model metadata and URL4 route catalog."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Model:
    id: str
    display_name: str
    price_per_million: float | None
    mock_error_bucket: int
    pricing_source: str
    pricing_as_of: date
    route: str
    pricing_basis: str = "blended_tokens"


_CATALOG = (
    Model(
        "codex/gpt-5.5",
        "GPT-5.5",
        12.0,
        0,
        "estimate:SDK catalog",
        date(2026, 7, 16),
        "/codex/gpt-5.5",
    ),
    Model(
        "gemini-cli/gemini-2.5-pro",
        "Gemini 2.5 Pro",
        10.0,
        1,
        "estimate:SDK catalog",
        date(2026, 7, 16),
        "/gemini/2.5",
    ),
    Model(
        "anthropic/claude-sonnet-4-6",
        "Claude Sonnet 4.6",
        15.0,
        2,
        "estimate:SDK catalog",
        date(2026, 7, 16),
        "/claude/sonnet-4.6",
    ),
)

_BY_ID = {model.id: model for model in _CATALOG}


class Models:
    def list(self, *, max_price: float | None = None) -> list[str]:
        if max_price is not None and (not math.isfinite(max_price) or max_price < 0):
            raise ValueError("max_price must be a non-negative finite number")
        return [
            model.id
            for model in _CATALOG
            if (
                max_price is None
                or (model.price_per_million is not None and model.price_per_million <= max_price)
            )
        ]

    def get(self, model_id: str) -> Model:
        try:
            return _BY_ID[model_id]
        except KeyError as exc:
            raise ValueError(f"unknown model: {model_id}") from exc


models = Models()
