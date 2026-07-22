"""Composite answer Recipes built from Models and nested Fusions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from screamingface.model import Model
from screamingface.model_inputs import _RecipeMember
from screamingface.recipe import Recipe, _name
from screamingface.reducers import Reducer

type Member = str | Model | Fusion
type RecipeNode = Model | Fusion


@dataclass(frozen=True, slots=True, init=False)
class Fusion(Recipe):
    """A Recipe that combines member answers through one explicit reducer."""

    name: str
    members: tuple[RecipeNode, ...]
    reducer: Reducer

    def __init__(
        self,
        name: str,
        *,
        members: Sequence[Member],
        reducer: Reducer,
    ) -> None:
        normalized_name = _name(name, "fusion name")
        normalized_members = _normalize_members(members)
        if not isinstance(reducer, Reducer):
            raise TypeError("a Fusion requires a reducer implementing sf.Reducer")
        object.__setattr__(self, "name", normalized_name)
        object.__setattr__(self, "members", normalized_members)
        object.__setattr__(self, "reducer", reducer)
        _validate_graph(self)

    @property
    def model_ids(self) -> tuple[str, ...]:
        models: list[str] = []
        _collect_models(self, models, set())
        return tuple(models)

    @property
    def _members(self) -> tuple[_RecipeMember, ...]:
        members: list[_RecipeMember] = []
        _collect_members(self, members, set())
        return tuple(members)

    @property
    def _reducers(self) -> tuple[Reducer, ...]:
        reducers: list[Reducer] = []
        _collect_reducers(self, reducers, set())
        return tuple(reducers)


def _normalize_members(values: Sequence[Member]) -> tuple[RecipeNode, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError("Fusion members must be a sequence")
    members: list[RecipeNode] = []
    for value in values:
        if isinstance(value, (Model, Fusion)):
            members.append(value)
        elif isinstance(value, str) and value.strip():
            members.append(Model(value))
        else:
            raise TypeError("Fusion members must be model IDs, sf.Model, or sf.Fusion values")
    if not members:
        raise ValueError("a Fusion requires at least one member")
    return tuple(members)


def _collect_models(recipe: RecipeNode, models: list[str], seen: set[int]) -> None:
    identity = id(recipe)
    if identity in seen:
        return
    seen.add(identity)
    if isinstance(recipe, Model):
        models.append(recipe.model)
        return
    for member in recipe.members:
        _collect_models(member, models, seen)


def _collect_members(recipe: RecipeNode, members: list[_RecipeMember], seen: set[int]) -> None:
    identity = id(recipe)
    if identity in seen:
        return
    seen.add(identity)
    if isinstance(recipe, Model):
        members.append(_RecipeMember(id=f"member_{len(members) + 1}", call=recipe._call))
        return
    for member in recipe.members:
        _collect_members(member, members, seen)


def _collect_reducers(recipe: RecipeNode, reducers: list[Reducer], seen: set[int]) -> None:
    identity = id(recipe)
    if identity in seen:
        return
    seen.add(identity)
    if isinstance(recipe, Model):
        return
    for member in recipe.members:
        _collect_reducers(member, reducers, seen)
    reducers.append(recipe.reducer)


def _validate_graph(root: Fusion) -> None:
    names: dict[str, int] = {}
    visited: set[int] = set()
    active: set[int] = set()

    def visit(recipe: RecipeNode) -> None:
        identity = id(recipe)
        if identity in active:
            raise ValueError(f"Recipe graph contains a cycle at {recipe.name!r}")
        if identity in visited:
            return
        owns_name = isinstance(recipe, Fusion) or recipe._explicit_name
        if owns_name:
            owner = names.get(recipe.name)
            if owner is not None and owner != identity:
                raise ValueError(f"duplicate Recipe name {recipe.name!r}")
            names[recipe.name] = identity
        active.add(identity)
        if isinstance(recipe, Fusion):
            for member in recipe.members:
                visit(member)
        active.remove(identity)
        visited.add(identity)

    visit(root)


__all__ = ["Fusion"]
