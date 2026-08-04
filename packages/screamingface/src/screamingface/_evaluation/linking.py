"""Structurally link one Candidate expression into one Benchmark expression."""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, fields, is_dataclass

from url4 import Iteration, Text, build, expr, render, src, text

from screamingface._evaluation.candidate import _MemberExpression
from screamingface.errors import PlanningError

_WHOLE_CANDIDATE = "$candidate"
_SYNTHESIZER = "$candidate_synthesizer"
_MEMBERS = "$candidate_members"
_MODEL_MEMBER = re.compile(r"\$candidate_model_member_([1-9][0-9]*)")


@dataclass(frozen=True, slots=True)
class _LinkedCandidate:
    url4: str
    uses_whole_candidate: bool
    member_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _BindingRequirements:
    whole_candidate: bool
    synthesizer: bool
    member_collection: bool
    member_indices: tuple[int, ...]


def link_candidate(
    candidate_url4: str,
    benchmark_url4: str,
    member_expressions: tuple[_MemberExpression, ...] = (),
    synthesizer_expression: str | None = None,
) -> _LinkedCandidate:
    """Bind the universal Candidate surface without interpreting Benchmark behavior."""

    candidate = build(candidate_url4)
    benchmark = build(benchmark_url4)
    requirements = _requirements(benchmark, len(member_expressions))
    if not requirements.whole_candidate and not requirements.member_indices:
        raise PlanningError(
            "Benchmark URL4 does not invoke the Candidate",
            code="invalid_benchmark_resource",
            permanent=True,
        )
    bindings = []
    if requirements.whole_candidate:
        bindings.append(src(text(render(candidate)), name="candidate", weight=0.0))
    bindings.extend(_synthesizer_bindings(requirements.synthesizer, synthesizer_expression))
    if requirements.member_collection:
        bindings.extend(_member_collection_binding(member_expressions))
    else:
        bindings.extend(_static_member_bindings(requirements.member_indices, member_expressions))
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
        uses_whole_candidate=requirements.whole_candidate,
        member_indices=requirements.member_indices,
    )


def _requirements(benchmark: object, member_count: int) -> _BindingRequirements:
    references = _text_references(benchmark)
    member_collection = _MEMBERS in references
    indices = tuple(
        sorted(
            {
                int(match.group(1))
                for reference in references
                if (match := _MODEL_MEMBER.fullmatch(reference)) is not None
            }
        )
    )
    if member_collection:
        indices = tuple(range(1, member_count + 1))
    return _BindingRequirements(
        whole_candidate=_WHOLE_CANDIDATE in references,
        synthesizer=_SYNTHESIZER in references,
        member_collection=member_collection,
        member_indices=indices,
    )


def _static_member_bindings(
    indices: tuple[int, ...],
    members: tuple[_MemberExpression, ...],
) -> list:
    if indices and (indices != tuple(range(1, len(indices) + 1)) or len(members) != len(indices)):
        raise PlanningError(
            f"Benchmark requires exactly {len(indices)} direct Model members, "
            f"but this Candidate has {len(members)} direct members",
            code="candidate_shape_mismatch",
            permanent=True,
        )
    bindings = []
    for index in indices:
        member = members[index - 1]
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
    return bindings


def _member_collection_binding(members: tuple[_MemberExpression, ...]) -> list:
    if not members:
        raise PlanningError(
            "Benchmark requires direct Candidate members — use an sf.Fusion",
            code="candidate_shape_mismatch",
            permanent=True,
        )
    payload = [
        {
            "key": chr(64 + index),
            "name": member.name,
            "kind": member.kind,
            "expression": render(build(member.url4)),
        }
        for index, member in enumerate(members, 1)
    ]
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    return [
        src(
            text(encoded),
            name="candidate_members",
            weight=0.0,
        )
    ]


def _synthesizer_bindings(uses_synthesizer: bool, expression: str | None) -> list:
    if not uses_synthesizer:
        return []
    if expression is None:
        # WHY loud: on this exam the Fusion's synthesizer serves as the JUDGE (it
        # tie-breaks passing answers and authors feedback — it never writes the
        # answer). A Candidate without one cannot play the protocol.
        raise PlanningError(
            "Benchmark requires the Candidate's synthesizer to act as its judge, "
            "but this Candidate has no synthesizer — use an sf.Fusion",
            code="candidate_shape_mismatch",
            permanent=True,
        )
    return [src(text(render(build(expression))), name="candidate_synthesizer", weight=0.0)]


def _text_references(value: object) -> set[str]:
    """Collect exact URL4 Text references from the parsed Benchmark tree."""

    references: set[str] = set()
    if isinstance(value, Text):
        references.add(value.value)
    elif isinstance(value, str):
        references.update(
            re.findall(
                r"\$candidate(?:_model_member_[1-9][0-9]*|_members|_synthesizer)?",
                value,
            )
        )
    elif isinstance(value, tuple | list):
        for item in value:
            references.update(_text_references(item))
    elif is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            references.update(_text_references(getattr(value, field.name)))
    return references


__all__: list[str] = []
