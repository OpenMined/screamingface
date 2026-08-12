"""Internal Benchmark execution signals that must survive URL4 collection."""

from url4.core.errors import ResolutionError


class ProviderRefusal(ResolutionError):
    """Exact provider refusal that stays identifiable through URL4 collection."""

    def __init__(self, refusal: str) -> None:
        super().__init__(refusal, code="provider_refusal", permanent=True)


__all__ = ["ProviderRefusal"]
