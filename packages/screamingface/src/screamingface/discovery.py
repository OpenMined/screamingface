"""Read-only Engine discovery values."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

type ScoreDirection = Literal["maximize", "minimize"]


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
    """One stable Benchmark name and its latest Engine-pinned revision."""

    name: str
    id: str
    manifest_digest: str
    title: str
    case_count: int
    primary_metric: str
    score_direction: ScoreDirection

    def __post_init__(self) -> None:
        for name in ("name", "id", "title", "primary_metric"):
            object.__setattr__(
                self,
                name,
                _nonblank(getattr(self, name), f"Benchmark {name}"),
            )
        digest = _nonblank(self.manifest_digest, "Benchmark manifest_digest")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
            raise ValueError(
                "Benchmark manifest_digest must be 'sha256:' plus 64 lowercase hex digits"
            )
        object.__setattr__(self, "manifest_digest", digest)
        if (
            isinstance(self.case_count, bool)
            or not isinstance(self.case_count, int)
            or self.case_count < 1
        ):
            raise ValueError("Benchmark case_count must be a positive integer")
        if self.score_direction not in {"maximize", "minimize"}:
            raise ValueError("Benchmark score_direction must be 'maximize' or 'minimize'")

    def _result_dict(self, case_count: int) -> dict[str, object]:
        """Return the pinned subset embedded in a Report."""

        if isinstance(case_count, bool) or not isinstance(case_count, int) or case_count < 1:
            raise ValueError("Report case_count must be a positive integer")
        if case_count > self.case_count:
            raise ValueError("Report case_count cannot exceed its Benchmark case_count")
        return {
            "id": self.id,
            "manifest_digest": self.manifest_digest,
            "primary_metric": self.primary_metric,
            "score_direction": self.score_direction,
            "case_count": case_count,
        }


def _nonblank(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


__all__ = ["BenchmarkInfo", "ModelInfo", "ScoreDirection"]
