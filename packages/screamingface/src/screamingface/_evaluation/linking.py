"""Structurally link one Candidate expression into one Benchmark expression."""

from __future__ import annotations

import re
from dataclasses import dataclass, fields, is_dataclass

from url4 import Iteration, Text, build, expr, render, src, struct, text

from screamingface._evaluation.candidate import _MemberExpression
from screamingface.errors import PlanningError

_WHOLE_CANDIDATE = "$candidate"
_SYNTHESIZER = "$candidate_synthesizer"
_MEMBERS = "$candidate_members"
_MEMBER = re.compile(r"\$candidate_member_([1-9][0-9]*)")


@dataclass(frozen=True, slots=True)
class _LinkedCandidate:
    url4: str
    uses_whole_candidate: bool
    uses_synthesizer: bool
    member_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _BindingRequirements:
    whole_candidate: bool
    synthesizer: bool
    member_collection: bool
    member_indices: tuple[int, ...]


def link_candidate(
    candidate_url4: str | None,
    benchmark_url4: str,
    member_expressions: tuple[_MemberExpression, ...] = (),
    synthesizer_expression: str | None = None,
) -> _LinkedCandidate:
    """Bind the universal Candidate surface without interpreting Benchmark behavior."""

    benchmark = build(benchmark_url4)
    requirements = _requirements(benchmark, len(member_expressions))
    if (
        not requirements.whole_candidate
        and not requirements.synthesizer
        and not requirements.member_collection
        and not requirements.member_indices
    ):
        raise PlanningError(
            "Benchmark URL4 does not invoke the Candidate",
            code="invalid_benchmark_resource",
            permanent=True,
        )
    bindings = []
    if requirements.whole_candidate:
        if candidate_url4 is None:
            raise PlanningError(
                "Benchmark invokes the whole Fusion, but it has no synthesizer — "
                "set synthesizer= before Evaluation",
                code="candidate_shape_mismatch",
                permanent=True,
            )
        candidate = build(candidate_url4)
        bindings.append(src(text(render(candidate)), name="candidate", weight=0.0))
    bindings.extend(_synthesizer_bindings(requirements.synthesizer, synthesizer_expression))
    bindings.extend(_static_member_bindings(requirements.member_indices, member_expressions))
    if requirements.member_collection:
        bindings.extend(_member_collection_binding(requirements.member_indices, member_expressions))
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
        uses_synthesizer=requirements.synthesizer,
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
                if (match := _MEMBER.fullmatch(reference)) is not None
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
        assert member.url4 is not None  # sf.Model compilation is always complete
        bindings.append(
            src(
                text(render(build(member.url4))),
                name=f"candidate_member_{index}",
                weight=0.0,
            )
        )
    return bindings


def _member_collection_binding(
    indices: tuple[int, ...],
    members: tuple[_MemberExpression, ...],
) -> list:
    if not members:
        raise PlanningError(
            "Benchmark requires direct Candidate members — use an sf.Fusion",
            code="candidate_shape_mismatch",
            permanent=True,
        )
    # INVARIANT: executable URL4 appears exactly once in the linked artifact, in the
    # ordinary named ``candidate_member_N`` binding above. This native URL4 struct carries
    # only stable references and display metadata; it is neither an opaque encoding nor a
    # second executable representation for Benchmark implementations to decode.
    collection = {
        f"member_{index}": {
            "name": _template_literal(members[index - 1].name),
            "url4": f"$candidate_member_{index}",
        }
        for index in indices
    }
    return [
        src(
            struct(collection),
            name="candidate_members",
            weight=0.0,
        )
    ]


def _template_literal(value: str) -> str:
    """Keep a user-facing name literal when a URL4 struct resolves its references."""

    return value.replace("$", "$$")


def _synthesizer_bindings(uses_synthesizer: bool, expression: str | None) -> list:
    if not uses_synthesizer:
        return []
    if expression is None:
        # INVARIANT: an explicit structural binding is never replaced by a Client,
        # Engine, or Benchmark default. The selected Candidate must actually supply it.
        raise PlanningError(
            "Benchmark requires an explicit Fusion synthesizer, but none was configured — "
            "set synthesizer= on an sf.Fusion",
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
        # INVARIANT: the trailing lookahead keeps unrelated names that merely start with
        # "$candidate" (e.g. the "$candidate_result" plumbing binding) from matching as a
        # bare whole-Candidate reference — that false positive made the linker bind the
        # full Candidate expression as dead text on exams that never invoke it.
        references.update(
            re.findall(
                r"\$candidate(?:_member_[1-9][0-9]*|_members|_synthesizer)?(?![A-Za-z0-9_])",
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
