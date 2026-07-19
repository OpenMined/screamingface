"""Compile Fusion definitions into canonical URL4 recipe and case expressions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from url4 import Expression, RelExpr, Text, render, src, struct, text

from screamingface._profile import FUSION_RESULT_SCHEMA
from screamingface._tooling import TOOL_PARAMETER, encoded_tools
from screamingface.errors import UnsupportedReducerError
from screamingface.model_inputs import ParameterValue, _FusionMember
from screamingface.reducers import MajorityVote, Model

if TYPE_CHECKING:
    from screamingface.fusion import Fusion

MAJORITY_VOTE_ROUTE = "/reducers/majority-vote"


def compile_fusion(
    fusion: Fusion,
    *,
    question: str | None = None,
    tools: Sequence[str] = (),
) -> str:
    """Render one parameterized recipe or one concrete case expression."""

    tool_params = _tool_params(tools)
    sources = []
    if question is not None:
        sources.append(src(text(_literal(question)), name="question"))
    sources.extend(_member_source(member, tool_params) for member in fusion._members)

    if isinstance(fusion.reducer, MajorityVote):
        member_answers = {member.id: f"${member.id}" for member in fusion._members}
        sources.append(src(struct(member_answers), name="member_answers"))
        reducer_call = RelExpr(
            path=MAJORITY_VOTE_ROUTE,
            context="$member_answers",
        )
    elif isinstance(fusion.reducer, Model):
        reducer_call = RelExpr(
            path=_model_route(fusion.reducer.model),
            context=_model_reducer_context(fusion._members),
            intent=Text(fusion.reducer.prompt),
            params=_params(fusion.reducer._parameter_items),
        )
    else:
        raise UnsupportedReducerError(f"unsupported reducer {type(fusion.reducer).__name__!r}")

    sources.append(src(reducer_call, name="fusion_answer"))
    sources.append(
        struct(
            {
                "schema": FUSION_RESULT_SCHEMA,
                "members": {
                    member.id: {
                        "model": _literal(member.model),
                        "answer": f"${member.id}",
                    }
                    for member in fusion._members
                },
                "answer": "$fusion_answer",
            }
        )
    )
    return render(Expression(sources=tuple(sources)))


def compile_model_expression(
    *,
    model: str,
    context: str,
    intent: str,
    params: Mapping[str, ParameterValue] | None = None,
) -> str:
    """Render one model request with arbitrary context held in a URL4 binding."""

    items = () if params is None else tuple(params.items())
    return render(
        Expression(
            sources=(
                RelExpr(
                    path=_model_route(model),
                    context="$model_context",
                    intent=Text(_literal(intent)),
                    params=_params(items),
                ),
                src(text(_literal(context)), name="model_context"),
            )
        )
    )


def _member_source(
    member: _FusionMember,
    tool_params: tuple[tuple[str, str], ...],
):
    return src(
        RelExpr(
            path=_model_route(member.model),
            context="$question",
            intent=Text(member.call.prompt),
            params=_params(member.call.parameter_items) + tool_params,
        ),
        name=member.id,
    )


def _model_reducer_context(members: tuple[_FusionMember, ...]) -> str:
    member_sections = []
    for position, member in enumerate(members, 1):
        member_sections.append(f"Panel {position} [{_literal(member.model)}]:\n${member.id}")
    return "Question:\n$question\n\nPanel answers:\n" + "\n\n".join(member_sections)


def _model_route(model: str) -> str:
    return f"/{model}"


def _params(
    items: tuple[tuple[str, ParameterValue], ...],
) -> tuple[tuple[str, str], ...]:
    return tuple((key, _param(value)) for key, value in items)


def _tool_params(tools: Sequence[str]) -> tuple[tuple[str, str], ...]:
    if not tools:
        return ()
    return ((TOOL_PARAMETER, encoded_tools(tools)),)


def _param(value: ParameterValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _literal(value: str) -> str:
    """Protect literal data from URL4's one-pass dollar interpolation."""

    return value.replace("$", "$$")


__all__ = ["MAJORITY_VOTE_ROUTE", "compile_fusion", "compile_model_expression"]
