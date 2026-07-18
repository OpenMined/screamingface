"""Network-free Fusion authoring; URL4 compilation arrives in Phase 2."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from screamingface.model_inputs import ModelInput, _FusionMember, normalize_model_inputs
from screamingface.reducers import Reducer


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
        prompt: str = "$question",
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
