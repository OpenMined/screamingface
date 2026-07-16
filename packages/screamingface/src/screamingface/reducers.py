"""Deterministic fusion reducers owned by the ScreamingFace SDK."""

from __future__ import annotations

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
