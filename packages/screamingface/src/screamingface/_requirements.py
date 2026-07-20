"""Pure planning of provider requirements for each evaluation stage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from screamingface._profile import Registry
from screamingface.benchmark import Benchmark
from screamingface.fusion import Fusion
from screamingface.graders import Rubric
from screamingface.reducers import Model

type RequirementRole = Literal["member", "reducer", "grader"]


@dataclass(frozen=True, slots=True)
class ModelRequirement:
    provider: str
    model: str
    role: RequirementRole


def run_requirements(fusion: Fusion, registry: Registry) -> tuple[ModelRequirement, ...]:
    requirements = [_requirement(model, "member", registry) for model in fusion.model_ids]
    if isinstance(fusion.reducer, Model):
        requirements.append(_requirement(fusion.reducer.model, "reducer", registry))
    return _unique(requirements)


def grade_requirements(benchmark: Benchmark, registry: Registry) -> tuple[ModelRequirement, ...]:
    if isinstance(benchmark.grader, Rubric):
        return (_requirement(benchmark.grader.model, "grader", registry),)
    return ()


def evaluate_requirements(
    fusion: Fusion, benchmark: Benchmark, registry: Registry
) -> tuple[ModelRequirement, ...]:
    return _unique(run_requirements(fusion, registry) + grade_requirements(benchmark, registry))


def _unique(
    requirements: tuple[ModelRequirement, ...] | list[ModelRequirement],
) -> tuple[ModelRequirement, ...]:
    return tuple(dict.fromkeys(requirements))


def _requirement(model: str, role: RequirementRole, registry: Registry) -> ModelRequirement:
    record = next((item for item in registry.models if item.id == model), None)
    if record is None:
        # INVARIANT: Existing execution preflight owns the public unknown-model error. This pure
        # planner cannot silently infer providers from model route prefixes.
        raise ValueError(f"model {model!r} is absent from the engine registry")
    if not record.provider:
        raise ValueError(f"model {model!r} has no explicit provider ownership")
    return ModelRequirement(provider=record.provider, model=model, role=role)
