"""Assemble a complete Evaluation from one Benchmark fetch and local Candidates."""

from __future__ import annotations

from collections.abc import Sequence

from screamingface._evaluation.benchmark import _BenchmarkResource
from screamingface._evaluation.candidate import compile_candidate
from screamingface._evaluation.linking import link_candidate
from screamingface._evaluation.model import (
    _compiled_candidate,
    _compiled_evaluation,
    _Evaluation,
)
from screamingface.recipe import Recipe


def compile_evaluation(
    recipes: Sequence[Recipe],
    benchmark: _BenchmarkResource,
    limit: int | None,
    *,
    default_synthesizer: str,
) -> _Evaluation:
    """Compile all Candidates locally after the Evaluation's only Benchmark fetch."""

    compiled = tuple(
        compile_candidate(recipe, default_synthesizer=default_synthesizer) for recipe in recipes
    )
    candidates = tuple(
        _compiled_candidate(
            name=recipe.name,
            kind=value.kind,
            models=value.models,
            url4=link_candidate(value.url4, benchmark.url4),
            operations=value.operations,
            members=value.members,
        )
        for recipe, value in zip(recipes, compiled, strict=True)
    )

    return _compiled_evaluation(
        benchmark=benchmark.info,
        limit=limit,
        case_count=benchmark.case_count,
        candidates=candidates,
        required_models=_ordered_unique(
            (
                *(model for value in compiled for model in value.models),
                *benchmark.required_models,
            )
        ),
    )


def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


__all__: list[str] = []
