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
MODEL_INPUT_SCHEMA = "screamingface.model-input.v1"


def compile_recipe(
    recipe: Recipe,
    *,
    question: str | None = None,
    tools: Sequence[Tool] = (),
    max_tool_calls: int | None = None,
    tool_policy_route: str | None = None,
) -> str:
    """Render one parameterized Recipe or one concrete case expression."""

    inline_tool_params = _tool_params(tools, max_tool_calls)
    if tool_policy_route is not None and not inline_tool_params:
        raise ValueError("a tool policy route requires benchmark tools")
    compiler = _RecipeCompiler(
        tool_params=(() if tool_policy_route is not None else inline_tool_params),
        tool_policy_reference=("$tool_policy" if tool_policy_route is not None else None),
        question=question,
    )
    return compiler.compile(recipe, tool_policy_route=tool_policy_route)


@dataclass(frozen=True, slots=True)
class _ResolvedInput:
    reference: str
    label: str


class _RecipeCompiler:
    def __init__(
        self,
        *,
        tool_params: tuple[tuple[str, str], ...],
        tool_policy_reference: str | None,
        question: str | None,
    ) -> None:
        self._tool_params = tool_params
        self._tool_policy_reference = tool_policy_reference
        self._sources: list[Node] = []
        if question is not None:
            self._sources.append(src(text(_literal(_url4_text(question))), name="question"))
        self._members: list[_RecipeMember] = []
        self._resolved: dict[int, _ResolvedInput] = {}
        self._active: set[int] = set()
        self._reduction_count = 0
        self._model_input_added = False

    def compile(self, recipe: Recipe, *, tool_policy_route: str | None = None) -> str:
        if tool_policy_route is not None:
            self._sources.append(src(tool_policy_route, name="tool_policy"))
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
        context = "$question"
        if self._tool_policy_reference is not None:
            if not self._model_input_added:
                self._sources.append(
                    src(
                        struct(
                            {
                                "schema": MODEL_INPUT_SCHEMA,
                                "question": "$question",
                                "tool_policy": self._tool_policy_reference,
                            }
                        ),
                        name="model_input",
                    )
                )
                self._model_input_added = True
            context = "$model_input"
        self._sources.append(
            src(_model_call(call, self._tool_params, context=context), name=member.id)
        )
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
                intent=Text(_url4_text(reducer.prompt)),
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
                        intent=Text(_literal(_url4_text(intent))),
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
    grader_kind: str = "exact_choice",
    tools: Sequence[Tool] = (),
    max_tool_calls: int | None = None,
    tool_policy_route: str | None = None,
    first: int | None = None,
) -> str:
    """Render one complete benchmark slice, Recipe, grading, and aggregation graph."""

    inline_tool_params = _tool_params(tools, max_tool_calls)
    if tool_policy_route is not None and not inline_tool_params:
        raise ValueError("a tool policy route requires benchmark tools")
    compiler = _RecipeCompiler(
        tool_params=(() if tool_policy_route is not None else inline_tool_params),
        tool_policy_reference=("$tool_policy" if tool_policy_route is not None else None),
        question=None,
    )
    sources: list[Node] = []
    if tool_policy_route is not None:
        sources.append(src(tool_policy_route, name="tool_policy"))
    sources.append(src("$item.input", name="question"))
    sources.extend(compiler.sources(recipe))
    grade_fields: dict[str, str] = {
        "benchmark_id": _literal(benchmark_id),
        "case_id": "$item.id",
        "reference": "$item.reference",
    }
    if grader_kind == "rubric":
        grade_fields["question"] = "$question"
    elif grader_kind != "exact_choice":
        raise ValueError(f"unsupported benchmark grader {grader_kind!r}")
    sources.extend(
        (
            src(struct(grade_fields), name="grade_input"),
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
    reducer = render(RelExpr(path=aggregator_route, intent=Text("Aggregate benchmark results")))
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


def compile_candidates_benchmark_expression(
    *,
    benchmark_id: str,
    cases_route: str,
    candidate_route: str,
    aggregator_route: str,
    candidates: Sequence[Recipe],
    tool_policy_route: str,
    first: int | None,
) -> str:
    """Render one candidate-set benchmark transaction with an explicit shared DAG spec."""

    specification = _CandidateSpecCompiler().compile(candidates)
    sources: tuple[Node, ...] = (
        src(tool_policy_route, name="tool_policy"),
        src(struct(specification), name="candidate_spec"),
        src(
            struct(
                {
                    "benchmark_id": _literal(benchmark_id),
                    "case_id": "$item.id",
                    "question": "$item.input",
                    "reference": "$item.reference",
                    "tool_policy": "$tool_policy",
                }
            ),
            name="candidate_input",
        ),
        src(
            RelExpr(
                path=candidate_route,
                context="$candidate_spec",
                intent=Text("$candidate_input"),
            ),
            name="case_result",
        ),
    )
    reducer = render(
        RelExpr(
            path=aggregator_route,
            intent=Text("Aggregate candidate benchmark results"),
        )
    )
    return render(
        iterate(
            cases_route,
            body=sources,
            intent=Text("$case_result"),
            reduce=reducer,
            slice=None if first is None else (0, first),
            on_error="collect",
        )
    )


class _CandidateSpecCompiler:
    """Serialize Recipe object identity into an ordered, engine-neutral DAG description."""

    def __init__(self) -> None:
        self._nodes: dict[str, object] = {}
        self._resolved: dict[int, str] = {}
        self._active: set[int] = set()

    def compile(self, candidates: Sequence[Recipe]) -> dict[str, object]:
        values = tuple(candidates)
        if not values:
            raise ValueError("candidate evaluation requires at least one Recipe")
        roots: dict[str, dict[str, str]] = {}
        names: set[str] = set()
        for position, candidate in enumerate(values, 1):
            if not isinstance(candidate, RecipeModel | _fusion_type()):
                raise TypeError("candidates must contain only sf.Model or sf.Fusion values")
            if candidate.name in names:
                raise ValueError(f"duplicate candidate name {candidate.name!r}")
            names.add(candidate.name)
            roots[f"candidate_{position}"] = {
                "name": _safe_struct_text(candidate.name),
                "root": self._recipe(candidate),
            }
        return {
            "schema": "screamingface.candidate-spec.v1",
            "nodes": self._nodes,
            "candidates": roots,
        }

    def _recipe(self, recipe: Recipe) -> str:
        from screamingface.fusion import Fusion

        identity = id(recipe)
        existing = self._resolved.get(identity)
        if existing is not None:
            return existing
        if identity in self._active:
            raise ValueError(f"Recipe graph contains a cycle at {recipe.name!r}")
        self._active.add(identity)
        node_id = f"node_{len(self._nodes) + 1}"
        # Reserve the stable ID before descending so shared descendants cannot steal it.
        self._nodes[node_id] = {}
        if isinstance(recipe, RecipeModel):
            value = _candidate_model(recipe)
        elif isinstance(recipe, Fusion):
            members = {
                f"member_{position}": self._recipe(member)
                for position, member in enumerate(recipe.members, 1)
            }
            value = {
                "kind": "fusion",
                "name": _safe_struct_text(recipe.name),
                "members": members,
                "reducer": _candidate_reducer(recipe.reducer),
            }
        else:  # pragma: no cover - guarded by compile and recursion types
            raise TypeError("candidate must be an sf.Model or sf.Fusion")
        self._nodes[node_id] = value
        self._resolved[identity] = node_id
        self._active.remove(identity)
        return node_id


def _candidate_model(recipe: RecipeModel) -> dict[str, object]:
    return {
        "kind": "model",
        "name": _safe_struct_text(recipe.name),
        "model": _safe_struct_text(recipe.model),
        "prompt": _safe_struct_text(recipe.prompt),
        "params": {
            _safe_struct_text(key): _safe_struct_text(_param(item))
            for key, item in recipe._parameter_items
        },
    }


def _candidate_reducer(reducer: object) -> dict[str, object]:
    if isinstance(reducer, Model):
        return {
            "kind": "model",
            "model": _safe_struct_text(reducer.model),
            "prompt": _safe_struct_text(reducer.prompt),
            "params": {
                _safe_struct_text(key): _safe_struct_text(_param(item))
                for key, item in reducer._parameter_items
            },
        }
    if isinstance(reducer, MajorityVote):
        return {"kind": "majority_vote"}
    raise UnsupportedReducerError(
        f"unsupported reducer {type(reducer).__name__!r} in candidate graph"
    )


def _fusion_type() -> type[object]:
    from screamingface.fusion import Fusion

    return Fusion


def _safe_struct_text(value: str) -> str:
    return _literal(_url4_text(value))


def _model_call(
    call: _ModelCall,
    tool_params: tuple[tuple[str, str], ...],
    *,
    context: str,
) -> RelExpr:
    return RelExpr(
        path=_model_route(call.model),
        context=context,
        intent=Text(_url4_text(call.prompt)),
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


def _url4_text(value: str) -> str:
    """Carry common multiline text through URL4's control-free quoted grammar.

    URL4 quoted text deliberately supports only printable characters. Unicode's
    line separator preserves prompt paragraph boundaries without inventing a
    URL4 escape sequence; tabs become ordinary spaces. Other ASCII controls are
    rejected locally instead of becoming opaque engine parse failures.
    """

    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\n", "\u2028").replace("\t", " ")
    unsupported = next(
        (char for char in normalized if char < " " or char == "\x7f"),
        None,
    )
    if unsupported is not None:
        raise ValueError(
            f"URL4 text contains unsupported control character U+{ord(unsupported):04X}"
        )
    return normalized


__all__ = [
    "MAJORITY_VOTE_ROUTE",
    "MODEL_INPUT_SCHEMA",
    "compile_benchmark_expression",
    "compile_candidates_benchmark_expression",
    "compile_model_expression",
    "compile_recipe",
]
