"""Read-only Engine discovery values."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """One Model route currently addressable through the configured Engine."""

    id: str
    provider: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _nonblank(self.id, "Model id"))
        object.__setattr__(self, "provider", _nonblank(self.provider, "Model provider"))


@dataclass(frozen=True, slots=True)
class BenchmarkInfo:
    """The stable identity, revision, and size of one Engine-owned Benchmark."""

    id: str
    revision: str
    case_count: int

    def __post_init__(self) -> None:
        for name in ("id", "revision"):
            object.__setattr__(
                self,
                name,
                _nonblank(getattr(self, name), f"Benchmark {name}"),
            )
        if (
            isinstance(self.case_count, bool)
            or not isinstance(self.case_count, int)
            or self.case_count < 1
        ):
            raise ValueError("Benchmark case_count must be a positive integer")

    def _result_dict(self, case_count: int) -> dict[str, object]:
        """Return the pinned subset embedded in a Report."""

        if isinstance(case_count, bool) or not isinstance(case_count, int) or case_count < 1:
            raise ValueError("Report case_count must be a positive integer")
        if case_count > self.case_count:
            raise ValueError("Report case_count cannot exceed its Benchmark case_count")
        return {
            "id": self.id,
            "revision": self.revision,
            "case_count": case_count,
        }


def _nonblank(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


__all__ = ["BenchmarkInfo", "ModelInfo"]
