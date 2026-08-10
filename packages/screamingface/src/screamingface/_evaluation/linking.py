"""Structurally link one Candidate expression into one Benchmark expression."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass

from url4 import Iteration, Text, VarRef, build, expr, render, src, struct, text

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
    rendered = render(linked)
    _require_every_reference_bound(rendered, requirements)
    return _LinkedCandidate(
        url4=rendered,
        uses_whole_candidate=requirements.whole_candidate,
        uses_synthesizer=requirements.synthesizer,
        member_indices=requirements.member_indices,
    )


def _require_every_reference_bound(rendered: str, requirements: _BindingRequirements) -> None:
    """Refuse to ship a linked artifact that still names something nothing binds.

    INVARIANT: every ``$candidate*`` reference in the shipped artifact resolves to a binding
    emitted above. This is checked on the RENDERED surface rather than the parsed tree on
    purpose: ``_requirements`` reasons over an AST where a reference has several shapes and
    the node set can grow upstream, while ``render`` collapses them all into one form. The
    check is therefore representation-independent — it closes the whole class of
    walker-blindness bugs rather than the one shape that motivated it, and it turns a
    mid-Run failure into a plan-time one, before the Candidate has been paid for.
    """

    bound = {f"$candidate_member_{index}" for index in requirements.member_indices}
    if requirements.whole_candidate:
        bound.add(_WHOLE_CANDIDATE)
    if requirements.synthesizer:
        bound.add(_SYNTHESIZER)
    if requirements.member_collection:
        bound.add(_MEMBERS)
    unresolved = _candidate_references(rendered) - bound
    if unresolved:
        names = ", ".join(sorted(unresolved))
        raise PlanningError(
            f"Benchmark URL4 references {names}, which this Candidate does not bind",
            code="candidate_shape_mismatch",
            permanent=True,
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
    """Collect exact URL4 Candidate references from the parsed Benchmark tree."""

    if isinstance(value, Text | str | VarRef):
        return _reference_site(value)
    return _nested_references(value)


def _reference_site(value: Text | str | VarRef) -> set[str]:
    """Read the references a single leaf node carries."""

    if isinstance(value, Text):
        return _candidate_references(value.value)
    if isinstance(value, VarRef):
        # WHY: a reference SITE is either a VarRef or a "$name" embedded in Text. URL4 parses
        # a reference in SOURCE position into a VarRef and strips the "$" sigil, so the name
        # arrives as a bare string the matcher can never recognise — this puts the sigil back.
        # A binding SITE (Binding.name) is also a bare string, but one the parser cannot
        # prefix, which is exactly why the matcher keys on the sigil and ignores it.
        # INVARIANT: path segments select fields on the RESOLVED value and are never part of
        # the reference name — "$candidate_member_1.answers" names member 1, not "…_1.answers".
        return _candidate_references(f"${value.name}") | _text_references(value.path)
    return _candidate_references(value)


def _nested_references(value: object) -> set[str]:
    """Walk whatever children a non-leaf node exposes."""

    references: set[str] = set()
    if isinstance(value, tuple | list):
        for item in value:
            references.update(_text_references(item))
    elif isinstance(value, Mapping):
        # Source.weight and Source.budgets may hold a mapping, which halts an
        # attribute-only walk.
        for key, item in value.items():
            references.update(_text_references(key))
            references.update(_text_references(item))
    elif is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            references.update(_text_references(getattr(value, field.name)))
    return references


def _candidate_references(value: str) -> set[str]:
    # INVARIANT: the trailing lookahead keeps unrelated names that merely start with
    # "$candidate" (e.g. the "$candidate_result" plumbing binding) from matching as a
    # bare whole-Candidate reference — that false positive made the linker bind the
    # full Candidate expression as dead text on exams that never invoke it.
    # INVARIANT: the leading lookbehind keeps an ESCAPED "$$candidate" literal from matching.
    # "$$" is URL4's escape for a literal "$", and _template_literal depends on it to keep a
    # user-facing member name literal — reading the escape back as a reference would both
    # invent an invocation the Benchmark never wrote and break the unresolved-reference check.
    return set(
        re.findall(
            r"(?<!\$)\$candidate(?:_member_[1-9][0-9]*|_members|_synthesizer)?(?![A-Za-z0-9_])",
            value,
        )
    )


__all__: list[str] = []
