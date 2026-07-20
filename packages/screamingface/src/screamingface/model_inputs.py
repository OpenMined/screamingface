"""Fusion model-input normalization shared by members and model reducers."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import NotRequired, TypedDict

from screamingface._tooling import TOOL_PARAMETER

type ParameterValue = str | int | float | bool


class ModelConfig(TypedDict):
    model: str
    prompt: NotRequired[str]
    params: NotRequired[dict[str, ParameterValue]]


@dataclass(frozen=True, slots=True, init=False)
class Model:
    """One named, reusable model call in a FusionMonster graph."""

    name: str
    model: str
    prompt: str
    _parameter_items: tuple[tuple[str, ParameterValue], ...] = field(repr=False)

    def __init__(
        self,
        name: str,
        model: str,
        *,
        prompt: str = "Answer the question.",
        params: Mapping[str, ParameterValue] | None = None,
    ) -> None:
        call = make_model_call(model=model, prompt=prompt, params=params)
        object.__setattr__(self, "name", _system_name(name, "model name"))
        object.__setattr__(self, "model", call.model)
        object.__setattr__(self, "prompt", call.prompt)
        object.__setattr__(self, "_parameter_items", call.parameter_items)

    @property
    def params(self) -> dict[str, ParameterValue]:
        return dict(self._parameter_items)


type ModelInput = str | ModelConfig | Model


@dataclass(frozen=True, slots=True)
class _ModelCall:
    model: str
    prompt: str
    parameter_items: tuple[tuple[str, ParameterValue], ...] = field(repr=False)

    @property
    def params(self) -> dict[str, ParameterValue]:
        return dict(self.parameter_items)


@dataclass(frozen=True, slots=True)
class _FusionMember:
    id: str
    call: _ModelCall
    explicit: bool = field(repr=False)
    model_value: Model | None = field(default=None, repr=False)

    @property
    def model(self) -> str:
        return self.call.model

    def to_model_input(self) -> ModelInput:
        if self.model_value is not None:
            return self.model_value
        if not self.explicit:
            return self.model
        config: ModelConfig = {"model": self.model}
        if self.call.prompt:
            config["prompt"] = self.call.prompt
        if self.call.parameter_items:
            config["params"] = self.call.params
        return config


def normalize_model_inputs(
    values: Sequence[ModelInput], *, default_prompt: str
) -> tuple[_FusionMember, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError("fusion models must be a sequence")
    prompt = _nonempty(default_prompt, "fusion prompt")
    return tuple(
        _FusionMember(
            id=f"member_{index}",
            call=_model_call(value, prompt),
            explicit=not isinstance(value, str),
            model_value=value if isinstance(value, Model) else None,
        )
        for index, value in enumerate(values, 1)
    )


def make_model_call(
    *, model: str, prompt: str, params: Mapping[str, ParameterValue] | None = None
) -> _ModelCall:
    return _ModelCall(
        model=_nonempty(model, "model"),
        prompt=_nonempty(prompt, "model prompt"),
        parameter_items=_parameter_items(params),
    )


def _model_call(value: ModelInput, default_prompt: str) -> _ModelCall:
    if isinstance(value, Model):
        return _ModelCall(value.model, value.prompt, value._parameter_items)
    if isinstance(value, str):
        return make_model_call(model=value, prompt=default_prompt)
    if not isinstance(value, Mapping):
        raise TypeError("fusion models must be model IDs, mappings, or sf.Model values")
    unknown = set(value) - {"model", "prompt", "params"}
    if unknown:
        fields = ", ".join(sorted(str(field) for field in unknown))
        raise ValueError(f"model configuration contains unknown field(s): {fields}")
    if "model" not in value:
        raise ValueError("model configuration is missing required field: model")
    return make_model_call(
        model=value["model"],
        prompt=value.get("prompt", default_prompt),
        params=value.get("params"),
    )


def _nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must not be empty")
    return value.strip()


def _system_name(value: object, label: str) -> str:
    return "-".join(_nonempty(value, label).lower().split())


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
