"""Shared public interface and behavior for URL4-backed answer recipes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from screamingface._progress import ProgressSetting
    from screamingface.benchmark import Benchmark
    from screamingface.model_inputs import _RecipeMember
    from screamingface.reducers import Reducer
    from screamingface.report import Report
    from screamingface.run import Run


class Recipe(ABC):
    """Non-constructible base for a shareable URL4 answer graph."""

    name: str

    @property
    def url4(self) -> str:
        from screamingface._compiler import compile_recipe

        return compile_recipe(self)

    def run(
        self,
        benchmark: str | Benchmark,
        *,
        first: int | None = None,
        progress: ProgressSetting = None,
    ) -> Run:
        from screamingface._execution import run_recipe

        return run_recipe(self, benchmark, first=first, progress=progress)

    def evaluate(
        self,
        benchmark: str | Benchmark,
        *,
        first: int | None = None,
        progress: ProgressSetting = None,
    ) -> Report:
        from screamingface._execution import evaluate_recipe

        return evaluate_recipe(self, benchmark, first=first, progress=progress)

    @property
    @abstractmethod
    def model_ids(self) -> tuple[str, ...]:
        """Return flattened model route IDs in stable member order."""

    @property
    @abstractmethod
    def _members(self) -> tuple[_RecipeMember, ...]:
        """Return flattened engine response members in stable order."""

    @property
    @abstractmethod
    def _reducers(self) -> tuple[Reducer, ...]:
        """Return every reducer needed by the graph in dependency order."""


def _name(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must not be empty")
    return "-".join(value.strip().lower().split())


__all__ = ["Recipe"]
