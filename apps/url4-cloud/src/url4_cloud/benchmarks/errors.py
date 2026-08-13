"""Internal Benchmark execution signals that must survive URL4 collection."""

import json

from url4.core.errors import ResolutionError
from url4_cloud.benchmarks.contract import validate_finish_reason


class ProviderRefusal(ResolutionError):
    """Exact provider refusal that stays identifiable through URL4 collection."""

    def __init__(self, refusal: str, *, finish_reason: str | None) -> None:
        if not isinstance(refusal, str) or not refusal.strip():
            raise ValueError("provider refusal must be non-empty text")
        finish_reason = validate_finish_reason(finish_reason)
        super().__init__(
            json.dumps(
                {"refusal": refusal, "finish_reason": finish_reason},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            code="provider_refusal",
            permanent=True,
        )


__all__ = ["ProviderRefusal"]
