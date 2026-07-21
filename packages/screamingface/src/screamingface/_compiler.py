"""Compile recursive Fusion definitions into canonical URL4 expressions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from url4 import Expression, Node, RelExpr, Text, render, src, struct, text

from screamingface._profile import FUSION_RESULT_SCHEMA
from screamingface._tooling import TOOL_PARAMETER
from screamingface.errors import UnsupportedReducerError
from screamingface.model_inputs import ParameterValue, _FusionMember, _ModelCall, make_model_call
from screamingface.reducers import MajorityVote, Model
from screamingface.tools import Tool, _tool_ids

if TYPE_CHECKING:
    from screamingface.fusion import Fusion

MAJORITY_VOTE_ROUTE = "/reducers/majority-vote"
_DEFAULT_PROMPT = "Answer the question."


def compile_fusion(
    fusion: Fusion,
    *,
    question: str | None = None,
    tools: Sequence[Tool] = (),
    max_tool_rounds: int | None = None,
) -> str:
    """Render one parameterized recursive recipe or one concrete case expression."""

    compiler = _FusionCompiler(
        tool_params=_tool_params(tools, max_tool_rounds),
        question=question,
    )
    return compiler.compile(fusion)


@dataclass(frozen=True, slots=True)
class _ResolvedInput:
    reference: str
    label: str


class _FusionCompiler:
    def __init__(
        self,
        *,
        tool_params: tuple[tuple[str, str], ...],
        question: str | None,
    ) -> None:
        self._tool_params = tool_params
        self._sources: list[Node] = []
        if question is not None:
            self._sources.append(src(text(_literal(question)), name="question"))
        self._members: list[_FusionMember] = []
        self._resolved: dict[int, _ResolvedInput] = {}
        self._active: set[int] = set()
        self._fusion_count = 0

    def compile(self, fusion: Fusion) -> str:
        root = self._fusion(fusion, is_root=True)
        self._sources.append(
            struct(
                {
                    "schema": FUSION_RESULT_SCHEMA,
                    "members": {
                        member.id: {
                            "model": _literal(member.model),
                            "answer": f"${member.id}",
                        }
                        for member in self._members
                    },
                    "answer": root.reference,
                }
            )
        )
        return render(Expression(sources=tuple(self._sources)))

    def _fusion(self, fusion: Fusion, *, is_root: bool = False) -> _ResolvedInput:
        identity = id(fusion)
        existing = self._resolved.get(identity)
        if existing is not None:
            return existing
        if identity in self._active:
            raise ValueError(f"Fusion graph contains a cycle at {fusion.name!r}")
        self._active.add(identity)
        if fusion.model is not None:
            assert fusion.prompt is not None
            resolved = self._atomic(
                _ModelCall(fusion.model, fusion.prompt, fusion._parameter_items),
                label=fusion.model,
            )
        else:
            inputs = tuple(self._input(value) for value in fusion.inputs)
            resolved = self._reduce(fusion, inputs, is_root=is_root)
        self._active.remove(identity)
        self._resolved[identity] = resolved
        return resolved

    def _input(self, value: str | Fusion) -> _ResolvedInput:
        if isinstance(value, str):
            return self._atomic(
                make_model_call(model=value, prompt=_DEFAULT_PROMPT),
                label=value.strip(),
            )
        return self._fusion(value)

    def _atomic(self, call: _ModelCall, *, label: str) -> _ResolvedInput:
        member = _FusionMember(id=f"member_{len(self._members) + 1}", call=call)
        self._members.append(member)
        self._sources.append(src(_model_call(call, self._tool_params), name=member.id))
        return _ResolvedInput(f"${member.id}", label)

    def _reduce(
        self,
        fusion: Fusion,
        inputs: tuple[_ResolvedInput, ...],
        *,
        is_root: bool,
    ) -> _ResolvedInput:
        reducer = fusion.reducer
        if reducer is None:
            raise UnsupportedReducerError("a composite Fusion requires a reducer")
        self._fusion_count += 1
        index = self._fusion_count
        answer_name = "fusion_answer" if is_root else f"fusion_{index}"
        if isinstance(reducer, MajorityVote):
            answers_name = "member_answers" if is_root else f"fusion_inputs_{index}"
            self._sources.append(
                src(
                    struct(
                        {
                            f"member_{position}": value.reference
                            for position, value in enumerate(inputs, 1)
                        }
                    ),
                    name=answers_name,
                )
            )
            call = RelExpr(path=MAJORITY_VOTE_ROUTE, context=f"${answers_name}")
        elif isinstance(reducer, Model):
            call = RelExpr(
                path=_model_route(reducer.model),
                context=_model_reducer_context(inputs),
                intent=Text(reducer.prompt),
                params=_params(reducer._parameter_items),
            )
        else:
            raise UnsupportedReducerError(f"unsupported reducer {type(reducer).__name__!r}")
        self._sources.append(src(call, name=answer_name))
        return _ResolvedInput(f"${answer_name}", fusion.name)


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


def _model_call(
    call: _ModelCall,
    tool_params: tuple[tuple[str, str], ...],
) -> RelExpr:
    return RelExpr(
        path=_model_route(call.model),
        context="$question",
        intent=Text(call.prompt),
        params=_params(call.parameter_items) + tool_params,
    )


def _model_reducer_context(inputs: tuple[_ResolvedInput, ...]) -> str:
    sections = [
        f"Panel {position} [{_literal(value.label)}]:\n{value.reference}"
        for position, value in enumerate(inputs, 1)
    ]
    return "Question:\n$question\n\nPanel answers:\n" + "\n\n".join(sections)


def _model_route(model: str) -> str:
    return f"/{model}"


def _params(
    items: tuple[tuple[str, ParameterValue], ...],
) -> tuple[tuple[str, str], ...]:
    return tuple((key, _param(value)) for key, value in items)


def _tool_params(tools: Sequence[Tool], max_tool_rounds: int | None) -> tuple[tuple[str, str], ...]:
    if not tools:
        if max_tool_rounds is not None:
            raise ValueError("max_tool_rounds must be None when tools are empty")
        return ()
    if isinstance(max_tool_rounds, bool) or not isinstance(max_tool_rounds, int):
        raise ValueError("max_tool_rounds is required when tools are configured")
    if max_tool_rounds < 1:
        raise ValueError("max_tool_rounds must be a positive integer")
    typed_tools = tuple(tools)
    values: list[tuple[str, str]] = [
        (TOOL_PARAMETER, "+".join(_tool_ids(typed_tools))),
        ("max_tool_rounds", str(max_tool_rounds)),
    ]
    for tool in typed_tools:
        values.extend((key, _param(value)) for key, value in tool._parameter_items())
    return tuple(values)


def _param(value: ParameterValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _literal(value: str) -> str:
    """Protect literal data from URL4's one-pass dollar interpolation."""

    return value.replace("$", "$$")


__all__ = ["MAJORITY_VOTE_ROUTE", "compile_fusion", "compile_model_expression"]
