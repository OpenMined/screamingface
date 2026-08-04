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
from screamingface.operation import OperationInfo
from screamingface.recipe import Recipe


def compile_evaluation(
    recipes: Sequence[Recipe],
    resource: _BenchmarkResource,
    limit: int | None,
    *,
    default_synthesizer: str,
) -> _Evaluation:
    """Compile all Candidates locally against one selected Benchmark Variant."""

    compiled = tuple(
        compile_candidate(recipe, default_synthesizer=default_synthesizer) for recipe in recipes
    )
    linked = tuple(
        link_candidate(
            value.url4,
            resource.url4,
            value.member_expressions,
            value.synthesizer_expression,
        )
        for recipe, value in zip(recipes, compiled, strict=True)
    )
    candidates = tuple(
        _compiled_candidate(
            name=recipe.name,
            kind=value.kind,
            models=_linked_models(value, result.uses_whole_candidate, result.member_indices),
            url4=result.url4,
            operations=_linked_operations(
                value, result.uses_whole_candidate, result.member_indices
            ),
            members=value.members,
        )
        for recipe, value, result in zip(recipes, compiled, linked, strict=True)
    )

    return _compiled_evaluation(
        benchmark=resource.info,
        limit=limit,
        case_count=resource.case_count,
        candidates=candidates,
        required_models=_ordered_unique(
            (
                *(model for candidate in candidates for model in candidate.models),
                *resource.required_models,
            )
        ),
    )


def _linked_models(
    candidate: _CompiledCandidate,
    uses_whole_candidate: bool,
    member_indices: tuple[int, ...],
) -> tuple[str, ...]:
    if uses_whole_candidate:
        return candidate.models
    return _ordered_unique(
        tuple(model for index in member_indices for model in candidate.members[index - 1].models)
    )


def _linked_operations(
    candidate: _CompiledCandidate,
    uses_whole_candidate: bool,
    member_indices: tuple[int, ...],
) -> tuple[OperationInfo, ...]:
    if uses_whole_candidate:
        return candidate.operations
    operation_ids = {candidate.members[index - 1].operation_id for index in member_indices}
    return tuple(operation for operation in candidate.operations if operation.id in operation_ids)


def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


__all__: list[str] = []
