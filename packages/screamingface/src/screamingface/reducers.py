"""Reducer definitions; execution is introduced in Phase 2."""

from __future__ import annotations

from abc import ABC
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import ClassVar

from screamingface.model_inputs import ParameterValue, make_model_call


class Reducer(ABC):
    """Base type for mechanisms that turn member answers into one answer."""

    kind: ClassVar[str]


@dataclass(frozen=True, slots=True)
class MajorityVote(Reducer):
    """Exact-string majority vote with stable member-order tie breaking."""

    kind: ClassVar[str] = "majority_vote"


@dataclass(frozen=True, slots=True, init=False)
class Model(Reducer):
    """Use a URL4-routed model to reduce labeled member answers."""

    model: str
    prompt: str
    _parameter_items: tuple[tuple[str, ParameterValue], ...] = field(repr=False)
    kind: ClassVar[str] = "model"

    def __init__(
        self,
        *,
        model: str,
        prompt: str,
        params: Mapping[str, ParameterValue] | None = None,
    ) -> None:
        call = make_model_call(model=model, prompt=prompt, params=params)
        object.__setattr__(self, "model", call.model)
        object.__setattr__(self, "prompt", call.prompt)
        object.__setattr__(self, "_parameter_items", call.parameter_items)

    @property
    def params(self) -> dict[str, ParameterValue]:
        return dict(self._parameter_items)
