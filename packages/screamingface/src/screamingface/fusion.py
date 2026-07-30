"""Composite Recipe values."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from screamingface.model import Model
from screamingface.recipe import Recipe, _name
from screamingface.reducers import Reducer


@dataclass(frozen=True, slots=True, init=False, eq=False)
class Fusion(Recipe):
    """Combine ordered member Recipes through one explicit Reducer."""

    name: str
    members: tuple[Recipe, ...]
    reducer: Reducer

    def __init__(
        self,
        name: str,
        *,
        members: Sequence[Recipe],
        reducer: Reducer,
    ) -> None:
        selected_members = _members(members)
        if not isinstance(reducer, Reducer):
            raise TypeError("Fusion reducer must be an sf.Reducer")
        object.__setattr__(self, "name", _name(name, "fusion name"))
        object.__setattr__(self, "members", selected_members)
        object.__setattr__(self, "reducer", reducer)

    @property
    def _recipe_marker(self) -> None:
        return None

    def __repr__(self) -> str:
        members = ", ".join(repr(member.name) for member in self.members)
        return f"Fusion({self.name!r}, members=[{members}], reducer={self.reducer!r})"

    def _repr_html_(self) -> str:
        from screamingface._card_display import fusion_card_html

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
