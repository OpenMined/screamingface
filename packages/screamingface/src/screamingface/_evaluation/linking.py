"""Structurally link one Candidate expression into one Benchmark expression."""

from __future__ import annotations

import re
from dataclasses import dataclass, fields, is_dataclass

from url4 import Iteration, Text, build, expr, render, src, text

from screamingface._evaluation.candidate import _MemberExpression
from screamingface.errors import PlanningError

_WHOLE_CANDIDATE = "$candidate"
_MODEL_MEMBER = re.compile(r"\$candidate_model_member_([1-9][0-9]*)")


@dataclass(frozen=True, slots=True)
class _LinkedCandidate:
    url4: str
    uses_whole_candidate: bool
    member_indices: tuple[int, ...]


def link_candidate(
    candidate_url4: str,
    benchmark_url4: str,
    member_expressions: tuple[_MemberExpression, ...] = (),
) -> _LinkedCandidate:
    """Bind the universal Candidate surface without interpreting Benchmark behavior."""

    candidate = build(candidate_url4)
    benchmark = build(benchmark_url4)
    references = _text_references(benchmark)
    uses_whole = _WHOLE_CANDIDATE in references
    member_indices = tuple(
        sorted(
            {
                int(match.group(1))
                for reference in references
                if (match := _MODEL_MEMBER.fullmatch(reference)) is not None
            }
        )
    )
    if not uses_whole and not member_indices:
        raise PlanningError(
            "Benchmark URL4 does not invoke the Candidate",
            code="invalid_benchmark_resource",
            permanent=True,
        )
    bindings = []
    if uses_whole:
        bindings.append(src(text(render(candidate)), name="candidate", weight=0.0))
    if member_indices and (
        member_indices != tuple(range(1, len(member_indices) + 1))
        or len(member_expressions) != len(member_indices)
    ):
        raise PlanningError(
            f"Benchmark requires exactly {len(member_indices)} direct Model members, "
            f"but this Candidate has {len(member_expressions)} direct members",
            code="candidate_shape_mismatch",
            permanent=True,
        )
    for index in member_indices:
        if index > len(member_expressions):
            raise PlanningError(
                f"Benchmark requires Fusion member {index}, but this Candidate has "
                f"{len(member_expressions)} direct members",
                code="candidate_shape_mismatch",
                permanent=True,
            )
        member = member_expressions[index - 1]
        if member.kind != "model":
            raise PlanningError(
                f"Benchmark requires Fusion member {index} to be an sf.Model",
                code="candidate_shape_mismatch",
                permanent=True,
            )
        bindings.append(
            src(
                text(render(build(member.url4))),
                name=f"candidate_model_member_{index}",
                weight=0.0,
            )
        )
    if isinstance(benchmark, Iteration):
        # The surface grammar greedily reads a top-level ``*(...)`` as a reduce envelope. This
        # ordinary instrumental passthrough gives the iteration an unambiguous nested boundary.
        benchmark = expr(
            src(benchmark, name="benchmark_result", weight=0.0),
            intent=text("$benchmark_result"),
        )
    linked = expr(
        *bindings,
        benchmark,
        intent=text(""),
    )
    return _LinkedCandidate(
        url4=render(linked),
        uses_whole_candidate=uses_whole,
        member_indices=member_indices,
    )


def _text_references(value: object) -> set[str]:
    """Collect exact URL4 Text references from the parsed Benchmark tree."""

    references: set[str] = set()
    if isinstance(value, Text):
        references.add(value.value)
    elif isinstance(value, str):
        references.update(re.findall(r"\$candidate(?:_model_member_[1-9][0-9]*)?", value))
    elif isinstance(value, tuple | list):
        for item in value:
            references.update(_text_references(item))
    elif is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            references.update(_text_references(getattr(value, field.name)))
    return references


__all__: list[str] = []
