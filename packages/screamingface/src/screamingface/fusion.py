"""Composite Candidate values."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from screamingface.model import Model
from screamingface.recipe import Recipe, _name


@dataclass(frozen=True, slots=True, init=False, eq=False)
class Fusion(Recipe):
    """Combine ordered members through an optional Candidate-owned synthesizer."""

    name: str
    members: tuple[Recipe, ...]
    synthesizer: Model | None

    def __init__(
        self,
        members: Sequence[Recipe],
        *,
        name: str | None = None,
        synthesizer: str | Model | None = None,
    ) -> None:
        selected_members = _members(members)
        inferred_name = "+".join(member.name for member in selected_members)
        object.__setattr__(
            self,
            "name",
            inferred_name if name is None else _name(name, "fusion name"),
        )
        object.__setattr__(self, "members", selected_members)
        object.__setattr__(self, "synthesizer", _synthesizer(synthesizer))

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


def _synthesizer(value: object) -> Model | None:
    if value is None:
        return None
    if isinstance(value, Model):
        return value
    if isinstance(value, str):
        return Model(value)
    raise TypeError("Fusion synthesizer must be an sf.Model or model route string")


def _unique_names(members: tuple[Recipe, ...]) -> None:
    seen: set[str] = set()
    for member in members:
        if member.name in seen:
            raise ValueError(f"duplicate Fusion member name {member.name!r}")
        seen.add(member.name)


__all__ = ["Fusion"]
