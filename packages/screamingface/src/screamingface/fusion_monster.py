"""Network-free authoring for a reusable Model and Fusion comparison graph."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from screamingface.fusion import Fusion
from screamingface.model_inputs import Model

type MonsterSystem = Model | Fusion


@dataclass(frozen=True, slots=True, init=False)
class FusionMonster:
    """An ordered set of Models and Fusions evaluated on the same benchmark cases."""

    name: str
    systems: tuple[MonsterSystem, ...]
    _model_dependencies: tuple[Model, ...] = field(repr=False)

    def __init__(self, name: str, systems: Sequence[MonsterSystem]) -> None:
        normalized_name = _name(name, "FusionMonster name")
        values = _systems(systems)
        _unique_system_names(values)
        dependencies = _dependencies(values)
        _system_dependency_names(values, dependencies)
        object.__setattr__(self, "name", normalized_name)
        object.__setattr__(self, "systems", values)
        object.__setattr__(self, "_model_dependencies", dependencies)


def _systems(values: Sequence[MonsterSystem]) -> tuple[MonsterSystem, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError("FusionMonster systems must be a sequence")
    systems = tuple(values)
    if len(systems) < 2:
        raise ValueError("a FusionMonster requires at least two systems")
    if not all(isinstance(system, (Model, Fusion)) for system in systems):
        raise TypeError("FusionMonster systems must be sf.Model or sf.Fusion values")
    return systems


def _unique_system_names(systems: tuple[MonsterSystem, ...]) -> None:
    names = tuple(system.name for system in systems)
    duplicates = tuple(dict.fromkeys(name for name in names if names.count(name) > 1))
    if duplicates:
        raise ValueError(f"FusionMonster system names must be unique: {', '.join(duplicates)}")


def _dependencies(systems: tuple[MonsterSystem, ...]) -> tuple[Model, ...]:
    dependencies: list[Model] = []
    by_name: dict[str, Model] = {}
    for system in systems:
        values = (system,) if isinstance(system, Model) else _fusion_models(system)
        for model in values:
            previous = by_name.get(model.name)
            if previous is not None and previous is not model:
                raise ValueError(
                    f"model dependency name {model.name!r} is ambiguous; "
                    "use distinct names for independent samples"
                )
            if previous is None:
                by_name[model.name] = model
                dependencies.append(model)
    return tuple(dependencies)


def _fusion_models(fusion: Fusion) -> tuple[Model, ...]:
    return tuple(member.model_value for member in fusion._members if member.model_value is not None)


def _system_dependency_names(
    systems: tuple[MonsterSystem, ...], dependencies: tuple[Model, ...]
) -> None:
    system_by_name = {system.name: system for system in systems}
    for dependency in dependencies:
        system = system_by_name.get(dependency.name)
        if system is not None and system is not dependency:
            raise ValueError(
                f"name {dependency.name!r} cannot identify both a system and model dependency"
            )


def _name(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must not be empty")
    return "-".join(value.strip().lower().split())


__all__ = ["FusionMonster"]
