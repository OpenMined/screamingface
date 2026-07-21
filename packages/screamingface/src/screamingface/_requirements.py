"""Pure planning of provider requirements for each evaluation stage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from screamingface._profile import Registry
from screamingface.benchmark import Benchmark
from screamingface.graders import Rubric
from screamingface.recipe import Recipe
from screamingface.reducers import Model

type RequirementRole = Literal["member", "reducer", "grader", "tool"]


@dataclass(frozen=True, slots=True)
class ConnectionRequirement:
    provider: str
    role: RequirementRole
    model: str | None = None


def run_requirements(
    recipe: Recipe, benchmark: Benchmark, registry: Registry
) -> tuple[ConnectionRequirement, ...]:
    requirements = [_requirement(model, "member", registry) for model in recipe.model_ids]
    requirements.extend(
        _requirement(reducer.model, "reducer", registry)
        for reducer in recipe._reducers
        if isinstance(reducer, Model)
    )
    if benchmark.tools:
        requirements.extend(_tool_requirements(recipe, registry))
    return _unique(requirements)


def grade_requirements(
    benchmark: Benchmark, registry: Registry
) -> tuple[ConnectionRequirement, ...]:
    if isinstance(benchmark.grader, Rubric):
        return (_requirement(benchmark.grader.model, "grader", registry),)
    return ()


def evaluate_requirements(
    recipe: Recipe, benchmark: Benchmark, registry: Registry
) -> tuple[ConnectionRequirement, ...]:
    return _unique(
        run_requirements(recipe, benchmark, registry) + grade_requirements(benchmark, registry)
    )


def _unique(
    requirements: tuple[ConnectionRequirement, ...] | list[ConnectionRequirement],
) -> tuple[ConnectionRequirement, ...]:
    return tuple(dict.fromkeys(requirements))


def _requirement(model: str, role: RequirementRole, registry: Registry) -> ConnectionRequirement:
    record = next((item for item in registry.models if item.id == model), None)
    if record is None:
        # INVARIANT: Existing execution preflight owns the public unknown-model error. This pure
        # planner cannot silently infer providers from model route prefixes.
        raise ValueError(f"model {model!r} is absent from the engine registry")
    if not record.provider:
        raise ValueError(f"model {model!r} has no explicit provider ownership")
    return ConnectionRequirement(provider=record.provider, model=model, role=role)


def _tool_requirements(recipe: Recipe, registry: Registry) -> tuple[ConnectionRequirement, ...]:
    models = {record.id: record for record in registry.models}
    providers = {provider.id for provider in registry.providers}
    required: list[ConnectionRequirement] = []
    for model_id in recipe.model_ids:
        record = models.get(model_id)
        if record is None:
            raise ValueError(f"model {model_id!r} is absent from the engine registry")
        for connection in record.required_connections:
            if connection not in providers:
                raise ValueError(
                    f"engine registry does not advertise required connection {connection!r}"
                )
            required.append(ConnectionRequirement(provider=connection, role="tool"))
    return _unique(required)
