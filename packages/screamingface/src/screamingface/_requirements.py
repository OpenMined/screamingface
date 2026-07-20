"""Pure planning of provider requirements for each evaluation stage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from screamingface._profile import Registry
from screamingface.benchmark import Benchmark
from screamingface.fusion import Fusion
from screamingface.graders import Rubric
from screamingface.reducers import Model

type RequirementRole = Literal["member", "reducer", "grader", "tool"]


@dataclass(frozen=True, slots=True)
class ConnectionRequirement:
    provider: str
    role: RequirementRole
    model: str | None = None


def run_requirements(
    fusion: Fusion, benchmark: Benchmark, registry: Registry
) -> tuple[ConnectionRequirement, ...]:
    requirements = [_requirement(model, "member", registry) for model in fusion.model_ids]
    if isinstance(fusion.reducer, Model):
        requirements.append(_requirement(fusion.reducer.model, "reducer", registry))
    if benchmark.tools:
        requirements.append(_tool_requirement(registry))
    return _unique(requirements)


def grade_requirements(
    benchmark: Benchmark, registry: Registry
) -> tuple[ConnectionRequirement, ...]:
    if isinstance(benchmark.grader, Rubric):
        return (_requirement(benchmark.grader.model, "grader", registry),)
    return ()


def evaluate_requirements(
    fusion: Fusion, benchmark: Benchmark, registry: Registry
) -> tuple[ConnectionRequirement, ...]:
    return _unique(
        run_requirements(fusion, benchmark, registry) + grade_requirements(benchmark, registry)
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


def _tool_requirement(registry: Registry) -> ConnectionRequirement:
    if not any(provider.id == "tavily" for provider in registry.providers):
        raise ValueError("engine registry does not advertise the required Tavily connection")
    return ConnectionRequirement(provider="tavily", role="tool")
