"""Bind one complete Candidate Recipe into one Benchmark expression."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass

from url4 import Iteration, Text, VarRef, build, expr, render, src, text

from screamingface.errors import PlanningError

_WHOLE_CANDIDATE = "$candidate"
_CANDIDATE_REFERENCE = re.compile(
    r"(?<!\$)\$candidate(?:_members|_synthesizer|_member_[A-Za-z0-9_]+)?(?![A-Za-z0-9_])"
)


@dataclass(frozen=True, slots=True)
class _LinkedCandidate:
    url4: str


def link_candidate(candidate_url4: str, benchmark_url4: str) -> _LinkedCandidate:
    """Bind the sole public Candidate seam without interpreting Benchmark behavior."""

    benchmark = build(benchmark_url4)
    references = _text_references(benchmark)
    if _WHOLE_CANDIDATE not in references:
        structural = sorted(value for value in references if value.startswith("$candidate_"))
        if structural:
            names = ", ".join(structural)
            raise PlanningError(
                f"Benchmark uses unsupported structural Candidate bindings: {names}; "
                "Benchmarks must consume one complete $candidate Recipe",
                code="candidate_shape_mismatch",
                permanent=True,
            )
        raise PlanningError(
            "Benchmark URL4 does not invoke the Candidate",
            code="invalid_benchmark_resource",
            permanent=True,
        )
    unsupported = sorted(value for value in references if value != _WHOLE_CANDIDATE)
    if unsupported:
        names = ", ".join(unsupported)
        raise PlanningError(
            f"Benchmark uses unsupported structural Candidate bindings: {names}; "
            "Benchmarks must consume one complete $candidate Recipe",
            code="candidate_shape_mismatch",
            permanent=True,
        )

    candidate = build(candidate_url4)
    binding = src(text(render(candidate)), name="candidate", weight=0.0)
    if isinstance(benchmark, Iteration):
        benchmark = expr(
            src(benchmark, name="benchmark_result", weight=0.0),
            intent=text("$benchmark_result"),
        )
    return _LinkedCandidate(url4=render(expr(binding, benchmark, intent=text(""))))


def _text_references(value: object) -> set[str]:
    leaf = _leaf_references(value)
    if leaf is not None:
        return leaf
    selected: set[str] = set()
    for child in _children(value):
        selected.update(_text_references(child))
    return selected


def _leaf_references(value: object) -> set[str] | None:
    selected = None
    if isinstance(value, Text):
        selected = _references(value.value)
    elif isinstance(value, VarRef):
        selected = _references(f"${value.name}") | _text_references(value.path)
    elif isinstance(value, str):
        selected = _references(value)
    return selected


def _children(value: object) -> tuple[object, ...]:
    selected: tuple[object, ...] = ()
    if isinstance(value, tuple | list):
        selected = tuple(value)
    elif isinstance(value, Mapping):
        selected = tuple(item for pair in value.items() for item in pair)
    elif is_dataclass(value) and not isinstance(value, type):
        selected = tuple(getattr(value, field.name) for field in fields(value))
    return selected


def _references(value: str) -> set[str]:
    return set(_CANDIDATE_REFERENCE.findall(value))


__all__: list[str] = []
