"""Composite Candidate values."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from screamingface._candidate_policy import GenerationParams
from screamingface._candidate_policy import params as _generation_params
from screamingface._candidate_policy import prompt as _generation_prompt
from screamingface.model import Model
from screamingface.recipe import Recipe, _model_route, _name


@dataclass(frozen=True, slots=True, init=False, eq=False)
class Fusion(Recipe):
    """Combine ordered members with optional Candidate-owned synthesis policy."""

    name: str
    members: tuple[Recipe, ...]
    synthesizer: str | None
    prompt: str | None
    _params: GenerationParams

    def __init__(
        self,
        members: Sequence[Recipe],
        *,
        name: str | None = None,
        synthesizer: str | None = None,
        prompt: str | None = None,
        params: Mapping[str, str | int | float | bool] | None = None,
    ) -> None:
        selected_members = _members(members)
        inferred_name = "+".join(member.name for member in selected_members)
        object.__setattr__(
            self,
            "name",
            inferred_name if name is None else _name(name, "fusion name"),
        )
        object.__setattr__(self, "members", selected_members)
        object.__setattr__(
            self,
            "synthesizer",
            None if synthesizer is None else _model_route(synthesizer),
        )
        object.__setattr__(self, "prompt", _generation_prompt(prompt, "fusion prompt"))
        object.__setattr__(self, "_params", _generation_params(params, "fusion params"))

    @property
    def params(self) -> GenerationParams:
        return self._params

    @property
    def _recipe_marker(self) -> None:
        return None

    def __repr__(self) -> str:
        members = ", ".join(repr(member.name) for member in self.members)
        inferred_name = "+".join(member.name for member in self.members)
        arguments = [f"[{members}]"]
        if self.name != inferred_name:
            arguments.append(f"name={self.name!r}")
        if self.synthesizer is not None:
            arguments.append(f"synthesizer={self.synthesizer!r}")
        if self.prompt is not None:
            arguments.append(f"prompt={self.prompt!r}")
        if self.params:
            arguments.append(f"params={dict(self.params)!r}")
        return f"Fusion({', '.join(arguments)})"

    def _repr_html_(self) -> str:
        from screamingface._ui.cards import fusion_card_html

        return fusion_card_html(self)


def _members(values: object) -> tuple[Recipe, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError("Fusion members must be sf.Model or sf.Fusion values")
    selected = tuple(values)
    if len(selected) < 2:
        raise ValueError("a Fusion requires at least two members")
    if any(not isinstance(member, Model | Fusion) for member in selected):
        raise TypeError("Fusion members must be sf.Model or sf.Fusion values")
    _unique_names(selected)
    return selected


def _unique_names(members: tuple[Recipe, ...]) -> None:
    seen: set[str] = set()
    for member in members:
        if member.name in seen:
            raise ValueError(f"duplicate Fusion member name {member.name!r}")
        seen.add(member.name)


__all__ = ["Fusion"]
