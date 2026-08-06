"""Assemble a complete Evaluation from one Benchmark fetch and local Candidates."""

from __future__ import annotations

from collections.abc import Sequence

from screamingface._evaluation.benchmark import _BenchmarkResource
from screamingface._evaluation.candidate import (
    _CompiledCandidate,
    _SynthesizerExpression,
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
) -> _Evaluation:
    """Compile all Candidates locally against one selected Benchmark."""

    compiled = tuple(compile_candidate(recipe) for recipe in recipes)
    linked = tuple(
        link_candidate(
            value.url4,
            resource.url4,
            value.member_expressions,
            value.synthesizer.url4 if value.synthesizer is not None else None,
        )
        for recipe, value in zip(recipes, compiled, strict=True)
    )
    candidates = []
    for recipe, value, result in zip(recipes, compiled, linked, strict=True):
        operations = _linked_operations(
            value,
            result.uses_whole_candidate,
            result.uses_synthesizer,
            result.member_indices,
        )
        operation_ids = {operation.id for operation in operations}
        parameter_assignments = [
            assignment
            for assignment in value.parameter_assignments
            if assignment.operation_id in operation_ids
        ]
        if (
            result.uses_synthesizer
            and value.synthesizer is not None
            and value.synthesizer.parameter_assignment is not None
        ):
            parameter_assignments.append(value.synthesizer.parameter_assignment)
        candidates.append(
            _compiled_candidate(
                name=recipe.name,
                kind=value.kind,
                models=_linked_models(
                    value,
                    result.uses_whole_candidate,
                    result.uses_synthesizer,
                    result.member_indices,
                ),
                url4=result.url4,
                operations=operations,
                members=value.members,
                parameter_assignments=parameter_assignments,
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


def _linked_models(
    candidate: _CompiledCandidate,
    uses_whole_candidate: bool,
    uses_synthesizer: bool,
    member_indices: tuple[int, ...],
) -> tuple[str, ...]:
    if uses_whole_candidate:
        return candidate.models
    selected = tuple(
        model for index in member_indices for model in candidate.members[index - 1].models
    )
    if uses_synthesizer:
        selected += (_synthesizer(candidate).model,)
    return _ordered_unique(selected)


def _linked_operations(
    candidate: _CompiledCandidate,
    uses_whole_candidate: bool,
    uses_synthesizer: bool,
    member_indices: tuple[int, ...],
) -> tuple[OperationInfo, ...]:
    if uses_whole_candidate:
        selected = candidate.operations
        if uses_synthesizer:
            selected += (_synthesizer(candidate).operation,)
        return selected
    operation_ids = {candidate.members[index - 1].operation_id for index in member_indices}
    if uses_synthesizer:
        operation_ids.add(_synthesizer(candidate).operation.id)
    selected = tuple(
        operation for operation in candidate.operations if operation.id in operation_ids
    )
    if uses_synthesizer:
        selected += (_synthesizer(candidate).operation,)
    return selected


def _synthesizer(candidate: _CompiledCandidate) -> _SynthesizerExpression:
    if candidate.synthesizer is None:  # pragma: no cover - linker seals this mismatch first
        raise RuntimeError("linked Candidate requires a synthesizer component")
    return candidate.synthesizer


def _known_operation_ids(candidate: _CompiledCandidate) -> tuple[str, ...]:
    values = tuple(operation.id for operation in candidate.operations) + tuple(
        member.operation_id for member in candidate.members
    )
    if candidate.synthesizer is not None:
        values += (candidate.synthesizer.operation.id,)
    return tuple(dict.fromkeys(values))


def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


__all__: list[str] = []
