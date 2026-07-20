"""Network-free Fusion authoring plus URL4-backed run orchestration."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from screamingface.model_inputs import ModelInput, _FusionMember, normalize_model_inputs
from screamingface.reducers import Reducer

if TYPE_CHECKING:
    from screamingface._progress import ProgressSetting
    from screamingface.benchmark import Benchmark
    from screamingface.report import Report
    from screamingface.run import Run


@dataclass(frozen=True, slots=True, init=False)
class Fusion:
    """An ordered panel and one explicit reduction strategy."""

    name: str
    prompt: str
    reducer: Reducer
    model_ids: tuple[str, ...]
    _members: tuple[_FusionMember, ...] = field(repr=False)

    def __init__(
        self,
        name: str,
        models: Sequence[ModelInput],
        reducer: Reducer,
        *,
        prompt: str = "Answer the question.",
    ) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("fusion name must not be empty")
        if not isinstance(reducer, Reducer):
            raise TypeError("fusion reducer must be an sf.Reducer")
        members = normalize_model_inputs(models, default_prompt=prompt)
        if len(members) < 2:
            raise ValueError("a fusion requires at least two models")
        object.__setattr__(self, "name", "-".join(name.strip().lower().split()))
        object.__setattr__(self, "prompt", prompt.strip())
        object.__setattr__(self, "reducer", reducer)
        object.__setattr__(self, "_members", members)
        object.__setattr__(self, "model_ids", tuple(member.model for member in members))

    @property
    def models(self) -> tuple[ModelInput, ...]:
        return tuple(member.to_model_input() for member in self._members)

    @property
    def url4(self) -> str:
        """Canonical parameterized URL4 recipe with an unbound ``$question``."""

        from screamingface._compiler import compile_fusion

        return compile_fusion(self)

    def run(
        self,
        benchmark: str | Benchmark,
        *,
        first: int | None = None,
        progress: ProgressSetting = None,
    ) -> Run:
        """Run selected benchmark cases through only the configured URL4 engine."""

        from screamingface._execution import run_fusion

        return run_fusion(self, benchmark, first=first, progress=progress)

    def evaluate(
        self,
        benchmark: str | Benchmark,
        *,
        first: int | None = None,
        progress: ProgressSetting = None,
    ) -> Report:
        """Preflight the complete requirement union, then run, grade, and aggregate."""

        from screamingface._execution import evaluate_fusion

        return evaluate_fusion(self, benchmark, first=first, progress=progress)
