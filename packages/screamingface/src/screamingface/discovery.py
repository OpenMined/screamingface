"""Read-only Engine discovery values."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from screamingface._ui.catalog import _CaseCatalog


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


@dataclass(frozen=True, slots=True)
class CaseInfo:
    """One public benchmark case — the id and the prompt a Candidate would receive.

    INVARIANT (answer-key discipline): exactly id + input — grading criteria, kwargs,
    and rubrics never cross the Engine boundary, so this value cannot carry them.
    """

    id: int
    input: str

    def __post_init__(self) -> None:
        if isinstance(self.id, bool) or not isinstance(self.id, int) or self.id < 1:
            raise ValueError("Case id must be a positive integer")
        object.__setattr__(self, "input", _nonblank(self.input, "Case input"))


@dataclass(frozen=True, slots=True)
class Benchmark:
    """What one Engine-owned Benchmark is — identity, size, and browsable cases.

    FEATURE: benchmark researcher discovery (OME-724) — a researcher reads this card
    and pages real prompts before spending money evaluating.
    """

    id: str
    family: str
    variant: str
    title: str
    description: str
    revision: str
    case_count: int
    # WHY: the value stays frozen/comparable data; the transport it was born from is
    # carried only as a non-comparing private field so `.cases()` can page lazily.
    _fetch_cases: Callable[[int, int], _CaseCatalog] = field(compare=False, repr=False)

    def __post_init__(self) -> None:
        for name in ("id", "family", "variant", "title", "description", "revision"):
            object.__setattr__(self, name, _nonblank(getattr(self, name), f"Benchmark {name}"))
        if (
            isinstance(self.case_count, bool)
            or not isinstance(self.case_count, int)
            or self.case_count < 1
        ):
            raise ValueError("Benchmark case_count must be a positive integer")

    def cases(self, limit: int = 50, offset: int = 0) -> _CaseCatalog:
        """Fetch one page of this Benchmark's public cases from the Engine."""

        return self._fetch_cases(limit, offset)

    def _repr_html_(self) -> str:
        from screamingface._ui.cards import benchmark_card_html

        return benchmark_card_html(self)


def _nonblank(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    if not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


__all__ = ["Benchmark", "BenchmarkInfo", "CaseInfo", "ModelInfo"]
