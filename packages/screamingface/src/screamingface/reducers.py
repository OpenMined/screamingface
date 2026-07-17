"""Fusion reducer strategies compiled or executed by ScreamingFace."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MajorityVote:
    """Select the most common normalized answer.

    ``tie_breaker`` names an existing fusion model whose answer wins a tied
    vote. It never causes an additional model call.
    """

    tie_breaker: str | None = None

    @property
    def name(self) -> str:
        return "majority_vote"


@dataclass(frozen=True, slots=True)
class Synthesize:
    """Ask one model to synthesize the labeled panel answers.

    Unlike :class:`MajorityVote`, synthesis is part of the URL4 execution graph
    and therefore causes one additional model-route call.
    """

    model: str
    temperature: float = 0.0
    max_tokens: int = 8192

    def __post_init__(self) -> None:
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("synthesizer model must not be empty")
        if (
            isinstance(self.temperature, bool)
            or not isinstance(self.temperature, (int, float))
            or not math.isfinite(self.temperature)
            or self.temperature < 0
        ):
            raise ValueError("synthesizer temperature must be a non-negative finite number")
        if (
            isinstance(self.max_tokens, bool)
            or not isinstance(self.max_tokens, int)
            or self.max_tokens < 1
        ):
            raise ValueError("synthesizer max_tokens must be a positive integer")

    @property
    def name(self) -> str:
        return "synthesize"


Reducer = MajorityVote | Synthesize
