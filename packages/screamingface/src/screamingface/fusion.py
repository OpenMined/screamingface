"""Composite Candidate values."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, ClassVar

from screamingface.recipe import Recipe, _name, _recipe


@dataclass(frozen=True, slots=True, init=False)
class Fusion(Recipe):
    """Combine ordered parallel members through an explicit synthesizer Recipe."""

    name: str
    members: tuple[Recipe, ...]
    synthesizer: Recipe

    def __init__(
        self,
        members: Sequence[str | Recipe],
        *,
        name: str | None = None,
        synthesizer: str | Recipe,
    ) -> None:
        selected_members = _members(members)
        inferred_name = "+".join(member.name for member in selected_members)
        object.__setattr__(
            self,
            "name",
            inferred_name if name is None else _name(name, "fusion name"),
        )
        object.__setattr__(self, "members", selected_members)
        object.__setattr__(self, "synthesizer", _recipe(synthesizer, "Fusion synthesizer"))

    @property
    def _recipe_marker(self) -> None:
        return None

    def __repr__(self) -> str:
        members = ", ".join(repr(member.name) for member in self.members)
        inferred_name = "+".join(member.name for member in self.members)
        arguments = [f"[{members}]"]
        if self.name != inferred_name:
            arguments.append(f"name={self.name!r}")
        arguments.append(f"synthesizer={self.synthesizer!r}")
        return f"Fusion({', '.join(arguments)})"

    def _repr_html_(self) -> str:
        from screamingface._ui.cards import fusion_card_html

        return fusion_card_html(self)

    __hash__: ClassVar[Any] = None


def _members(values: object) -> tuple[Recipe, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError("Fusion members must be an ordered sequence of model routes or Recipes")
    selected = tuple(_recipe(value, "Fusion member") for value in values)
    if not selected:
        raise ValueError("a Fusion requires at least one member")
    return selected


__all__ = ["Fusion"]
