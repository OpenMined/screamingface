"""Assemble a complete Evaluation from one Benchmark fetch and local Candidates."""

from __future__ import annotations

from collections.abc import Sequence

from screamingface._evaluation.benchmark import _BenchmarkResource
from screamingface._evaluation.candidate import (
    _CompiledCandidate,
    compile_candidate,
)
from screamingface._evaluation.linking import link_candidate
from screamingface._evaluation.model import (
    _compiled_candidate,
    _compiled_evaluation,
    _Evaluation,
)
from screamingface.recipe import Recipe


def compile_evaluation(
    recipes: Sequence[Recipe],
    resource: _BenchmarkResource,
    limit: int | None,
) -> _Evaluation:
    """Compile all Candidates locally against one selected Benchmark."""

    compiled = tuple(compile_candidate(recipe) for recipe in recipes)
    linked = tuple(
        link_candidate(value.url4, resource.url4)
        for recipe, value in zip(recipes, compiled, strict=True)
    )
    candidates = []
    for recipe, value, result in zip(recipes, compiled, linked, strict=True):
        candidates.append(
            _compiled_candidate(
                name=recipe.name,
                kind=value.kind,
                models=value.models,
                url4=result.url4,
                operations=value.operations,
                members=value.members,
                parameter_assignments=value.parameter_assignments,
                known_operation_ids=_known_operation_ids(value),
            )
        )
    selected_candidates = tuple(candidates)

    return _compiled_evaluation(
        benchmark=resource.info,
        limit=limit,
        case_count=resource.case_count,
        candidates=selected_candidates,
        required_models=_ordered_unique(
            tuple(model for candidate in selected_candidates for model in candidate.models)
        ),
    )


def _known_operation_ids(candidate: _CompiledCandidate) -> tuple[str, ...]:
    values = tuple(operation.id for operation in candidate.operations) + tuple(
        member.operation_id for member in candidate.members
    )
    return tuple(dict.fromkeys(values))


def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


__all__: list[str] = []
