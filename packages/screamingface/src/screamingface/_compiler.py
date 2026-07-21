"""Compile Recipe graphs into canonical URL4 expressions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from url4 import Expression, Node, RelExpr, Text, iterate, render, src, struct, text

from screamingface._profile import RECIPE_RESULT_SCHEMA
from screamingface._tooling import TOOL_PARAMETER
from screamingface.errors import UnsupportedReducerError
from screamingface.model import Model as RecipeModel
from screamingface.model_inputs import ParameterValue, _ModelCall, _RecipeMember
from screamingface.reducers import MajorityVote, Model
from screamingface.tools import Tool, _tool_ids

if TYPE_CHECKING:
    from screamingface.fusion import Fusion
    from screamingface.recipe import Recipe

MAJORITY_VOTE_ROUTE = "/reducers/majority-vote/1"


def compile_recipe(
    recipe: Recipe,
    *,
    question: str | None = None,
    tools: Sequence[Tool] = (),
    max_tool_calls: int | None = None,
) -> str:
    """Render one parameterized Recipe or one concrete case expression."""

    compiler = _RecipeCompiler(
        tool_params=_tool_params(tools, max_tool_calls),
        question=question,
    )
    return compiler.compile(recipe)


@dataclass(frozen=True, slots=True)
class _ResolvedInput:
    reference: str
    label: str


class _RecipeCompiler:
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
        self._members: list[_RecipeMember] = []
        self._resolved: dict[int, _ResolvedInput] = {}
        self._active: set[int] = set()
        self._reduction_count = 0

    def compile(self, recipe: Recipe) -> str:
        return render(
            Expression(
                sources=self.sources(recipe),
                intent=Text("$recipe_result"),
            )
        )

    def sources(self, recipe: Recipe) -> tuple[Node, ...]:
        """Return the named Recipe graph for an enclosing URL4 computation."""

        root = self._recipe(recipe, is_root=True)
        self._sources.append(
            src(
                struct(
                    {
                        "schema": RECIPE_RESULT_SCHEMA,
                        "members": {
                            member.id: {
                                "model": _literal(member.model),
                                "answer": f"${member.id}",
                            }
                            for member in self._members
                        },
                        "answer": root.reference,
                    }
                ),
                name="recipe_result",
            )
        )
        return tuple(self._sources)

    def _recipe(self, recipe: Recipe, *, is_root: bool = False) -> _ResolvedInput:
        from screamingface.fusion import Fusion

        identity = id(recipe)
        existing = self._resolved.get(identity)
        if existing is not None:
            return existing
        if identity in self._active:
            raise ValueError(f"Recipe graph contains a cycle at {recipe.name!r}")
        self._active.add(identity)
        if isinstance(recipe, RecipeModel):
            resolved = self._atomic(recipe._call, label=recipe.model)
        elif isinstance(recipe, Fusion):
            members = tuple(self._recipe(value) for value in recipe.members)
            resolved = self._reduce(recipe, members, is_root=is_root)
        else:
            raise TypeError("recipe must be an sf.Model or sf.Fusion")
        self._active.remove(identity)
        self._resolved[identity] = resolved
        return resolved

    def _atomic(self, call: _ModelCall, *, label: str) -> _ResolvedInput:
        member = _RecipeMember(id=f"member_{len(self._members) + 1}", call=call)
        self._members.append(member)
        self._sources.append(src(_model_call(call, self._tool_params), name=member.id))
        return _ResolvedInput(f"${member.id}", label)

    def _reduce(
        self,
        fusion: Fusion,
        members: tuple[_ResolvedInput, ...],
        *,
        is_root: bool,
    ) -> _ResolvedInput:
        reducer = fusion.reducer
        if reducer is None:
            raise UnsupportedReducerError("a composite Fusion requires a reducer")
        self._reduction_count += 1
        index = self._reduction_count
        answer_name = "recipe_answer" if is_root else f"recipe_{index}"
        if isinstance(reducer, MajorityVote):
            answers_name = "member_answers" if is_root else f"recipe_members_{index}"
            self._sources.append(
                src(
                    struct(
                        {
                            f"member_{position}": value.reference
                            for position, value in enumerate(members, 1)
                        }
                    ),
                    name=answers_name,
                )
            )
            call = RelExpr(
                path=MAJORITY_VOTE_ROUTE,
                intent=Text(f"${answers_name}"),
            )
        elif isinstance(reducer, Model):
            call = RelExpr(
                path=_model_route(reducer.model),
                context=_model_reducer_context(members),
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
                src(text(_literal(context)), name="model_context"),
                src(
                    RelExpr(
                        path=_model_route(model),
                        context="$model_context",
                        intent=Text(_literal(intent)),
                        params=_params(items),
                    ),
                    name="model_result",
                ),
            ),
            intent=Text("$model_result"),
        )
    )


def compile_benchmark_expression(
    *,
    benchmark_id: str,
    cases_route: str,
    grader_route: str,
    aggregator_route: str,
    recipe: Recipe,
    tools: Sequence[Tool] = (),
    max_tool_calls: int | None = None,
    first: int | None = None,
) -> str:
    """Render one complete benchmark slice, Recipe, grading, and aggregation graph."""

    compiler = _RecipeCompiler(
        tool_params=_tool_params(tools, max_tool_calls),
        question=None,
    )
    sources: list[Node] = [src("$item.input", name="question")]
    sources.extend(compiler.sources(recipe))
    sources.extend(
        (
            src(
                struct(
                    {
                        "benchmark_id": _literal(benchmark_id),
                        "case_id": "$item.id",
                        "reference": "$item.reference",
                    }
                ),
                name="grade_input",
            ),
            src(
                RelExpr(
                    path=grader_route,
                    context="$recipe_result",
                    intent=Text("$grade_input"),
                ),
                name="case_result",
            ),
        )
    )
    reducer = render(
        RelExpr(
            path=aggregator_route,
            intent=Text("Aggregate benchmark results"),
        )
    )
    return render(
        iterate(
            cases_route,
            body=tuple(sources),
            intent=Text("$case_result"),
            reduce=reducer,
            slice=None if first is None else (0, first),
            on_error="collect",
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


def _tool_params(tools: Sequence[Tool], max_tool_calls: int | None) -> tuple[tuple[str, str], ...]:
    if not tools:
        if max_tool_calls is not None:
            raise ValueError("max_tool_calls must be None when tools are empty")
        return ()
    if isinstance(max_tool_calls, bool) or not isinstance(max_tool_calls, int):
        raise ValueError("max_tool_calls is required when tools are configured")
    if not 1 <= max_tool_calls <= 32:
        raise ValueError("max_tool_calls must be a positive integer from 1 to 32")
    typed_tools = tuple(tools)
    values: list[tuple[str, str]] = [
        (TOOL_PARAMETER, ":".join(_tool_ids(typed_tools))),
        ("tools.max_calls", str(max_tool_calls)),
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


__all__ = [
    "MAJORITY_VOTE_ROUTE",
    "compile_benchmark_expression",
    "compile_model_expression",
    "compile_recipe",
]
