"""Validated model-call values shared by Models and model reducers."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

from screamingface._tooling import TOOL_PARAMETER

type ParameterValue = str | int | float | bool


@dataclass(frozen=True, slots=True)
class _ModelCall:
    model: str
    prompt: str
    parameter_items: tuple[tuple[str, ParameterValue], ...] = field(repr=False)

    @property
    def params(self) -> dict[str, ParameterValue]:
        return dict(self.parameter_items)


@dataclass(frozen=True, slots=True)
class _RecipeMember:
    id: str
    call: _ModelCall

    @property
    def model(self) -> str:
        return self.call.model


def make_model_call(
    *, model: str, prompt: str, params: Mapping[str, ParameterValue] | None = None
) -> _ModelCall:
    return _ModelCall(
        model=_nonempty(model, "model"),
        prompt=_nonempty(prompt, "model prompt"),
        parameter_items=_parameter_items(params),
    )


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value.strip()


def _parameter_items(
    params: Mapping[str, ParameterValue] | None,
) -> tuple[tuple[str, ParameterValue], ...]:
    if params is None:
        return ()
    if not isinstance(params, Mapping):
        raise TypeError("model params must be a mapping")
    items: list[tuple[str, ParameterValue]] = []
    for key, value in params.items():
        name = _nonempty(key, "model parameter name")
        if name == TOOL_PARAMETER:
            raise ValueError(
                "model parameter 'tools' is reserved; declare required capabilities on sf.Benchmark"
            )
        if not isinstance(value, (str, int, float, bool)):
            raise TypeError(f"model parameter {name!r} must be a JSON scalar")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"model parameter {name!r} must be finite")
        items.append((name, value))
    return tuple(items)
