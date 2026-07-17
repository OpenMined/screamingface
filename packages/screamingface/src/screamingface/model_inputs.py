"""Public model-input data shape and private normalized fusion slots."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import NotRequired, TypedDict

type ParameterValue = str | int | float | bool


class ModelConfig(TypedDict):
    """Optional per-model configuration accepted by :class:`Fusion`.

    A plain model ID is shorthand for ``{"model": model_id}``.
    """

    model: str
    name: NotRequired[str]
    prompt: NotRequired[str]
    params: NotRequired[dict[str, ParameterValue]]


type ModelInput = str | ModelConfig


@dataclass(frozen=True, slots=True)
class _FusionMember:
    """One normalized URL4 call slot; intentionally not part of the public API."""

    id: str
    model: str
    prompt: str
    parameter_items: tuple[tuple[str, ParameterValue], ...] = field(repr=False)
    has_explicit_name: bool = field(repr=False)

    @property
    def params(self) -> Mapping[str, ParameterValue]:
        return MappingProxyType(dict(self.parameter_items))

    def to_model_input(self) -> ModelInput:
        """Return a fresh canonical public string/dictionary representation."""

        if not self.has_explicit_name and self.prompt == "$question" and not self.parameter_items:
            return self.model
        config: ModelConfig = {"model": self.model}
        if self.has_explicit_name:
            config["name"] = self.id
        if self.prompt != "$question":
            config["prompt"] = self.prompt
        if self.parameter_items:
            config["params"] = dict(self.parameter_items)
        return config


@dataclass(frozen=True, slots=True)
class _ModelDraft:
    model: str
    name: str | None
    prompt: str
    parameter_items: tuple[tuple[str, ParameterValue], ...]


def normalize_model_inputs(values: tuple[ModelInput, ...]) -> tuple[_FusionMember, ...]:
    """Validate model inputs and assign stable private call-slot identities."""

    drafts = tuple(_model_draft(value) for value in values)
    model_counts = Counter(draft.model for draft in drafts)
    occurrences: Counter[str] = Counter()
    members: list[_FusionMember] = []
    for draft in drafts:
        occurrences[draft.model] += 1
        generated_id = (
            draft.model
            if model_counts[draft.model] == 1
            else f"{draft.model}#{occurrences[draft.model]}"
        )
        members.append(
            _FusionMember(
                id=draft.name or generated_id,
                model=draft.model,
                prompt=draft.prompt,
                parameter_items=draft.parameter_items,
                has_explicit_name=draft.name is not None,
            )
        )

    ids = [member.id for member in members]
    if len(ids) != len(set(ids)):
        raise ValueError("fusion model names must be unique")
    return tuple(members)


def _model_draft(value: ModelInput) -> _ModelDraft:
    if isinstance(value, str):
        return _ModelDraft(_nonempty(value, "model id"), None, "$question", ())
    if not isinstance(value, Mapping):
        value_type = type(value).__name__
        raise TypeError(f"fusion models must be model IDs or model dictionaries, got {value_type}")

    allowed = {"model", "name", "prompt", "params"}
    unknown = set(value) - allowed
    if unknown:
        fields = ", ".join(sorted(str(field) for field in unknown))
        raise ValueError(f"model configuration contains unknown field(s): {fields}")
    if "model" not in value:
        raise ValueError("model configuration is missing required field: model")

    model = _nonempty(value["model"], "model configuration field 'model'")
    name_value = value.get("name")
    name = None if name_value is None else _nonempty(name_value, "model configuration field 'name'")
    prompt = _nonempty(
        value.get("prompt", "$question"),
        "model configuration field 'prompt'",
    )
    return _ModelDraft(model, name, prompt, _parameter_items(value.get("params")))


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
        normalized_key = _nonempty(key, "model parameter name")
        if not isinstance(value, (str, int, float, bool)):
            raise TypeError(
                f"model parameter {normalized_key!r} must be text, a number, or a boolean"
            )
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"model parameter {normalized_key!r} must be finite")
        items.append((normalized_key, value))
    return tuple(items)
