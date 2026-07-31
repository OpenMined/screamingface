"""Compile one explicit Candidate Benchmark URL4 for SF Engine."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from url4 import Node, RelExpr, Text, iterate, render, src, struct

from screamingface._benchmark_manifest import _BenchmarkManifest
from screamingface.fusion import Fusion
from screamingface.model import Model
from screamingface.recipe import Recipe


@dataclass(frozen=True, slots=True)
class _OperationSpec:
    id: str
    kind: str
    label: str
    depends_on: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _MemberSpec:
    operation_id: str
    name: str
    kind: Literal["model", "fusion"]
    models: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _CompiledBenchmark:
    kind: Literal["model", "fusion"]
    url4: str
    models: tuple[str, ...]
    operations: tuple[_OperationSpec, ...]
    members: tuple[_MemberSpec, ...]
    model_calls_per_case: int
    synthesis_calls_per_case: int


@dataclass(frozen=True, slots=True)
class _ResolvedRecipe:
    reference: str
    operation_id: str
    name: str
    kind: Literal["model", "fusion"]
    models: tuple[str, ...]


def compile_benchmark(
    recipe: Recipe,
    manifest: _BenchmarkManifest,
    *,
    limit: int | None,
) -> _CompiledBenchmark:
    """Compile Load → Run → Grade → Aggregate as one Candidate URL4."""

    graph = _RecipeCompiler(manifest).compile(recipe)
    judge_jobs = _action_call(
        manifest,
        context=_structured_context(
            {
                "benchmark": manifest.info.id,
                "action": "grading_inputs",
                "case": "$item",
                "answer": graph.root.reference,
            }
        ),
        intent="Prepare rubric judge inputs.",
    )
    judgments = iterate(
        judge_jobs,
        body=(
            src("$item.context", name="judge_context", weight=0.0),
            src(
                RelExpr(
                    path=_model_route(manifest.judge_model),
                    context="$judge_context",
                    intent=Text(_url4_text(manifest.judge_instructions)),
                    params=manifest.judge_params,
                ),
                name="response",
                weight=0.0,
            ),
            src(
                struct(
                    {
                        "criterion_id": "$item.criterion_id",
                        "run": "$item.run",
                        "response": "$response",
                    }
                ),
                name="judgment",
                weight=0.0,
            ),
        ),
        intent=Text("$judgment"),
    )
    body = (
        src("$item.input", name="question", weight=0.0),
        *graph.sources,
        src(judgments, name="judgments", weight=0.0),
        src(
            _action_call(
                manifest,
                context=_structured_context(
                    {
                        "benchmark": manifest.info.id,
                        "action": "grade",
                        "case": "$item",
                        "judgments": "$judgments",
                    }
                ),
                intent="Grade the Candidate answer.",
            ),
            name="case_grade",
            weight=0.0,
        ),
    )
    reducer = render(
        _action_call(
            manifest,
            context=_control_json(manifest, "aggregate"),
            intent="Aggregate Candidate case grades.",
        )
    )
    judge = _OperationSpec(
        id="op_judge",
        kind="judge",
        label=f"{manifest.info.title} rubric judges",
        depends_on=(graph.root.operation_id,),
    )
    grade = _OperationSpec(
        id="op_grade",
        kind="grading",
        label=f"{manifest.info.title} deterministic scoring",
        depends_on=(judge.id,),
    )
    aggregate = _OperationSpec(
        id="op_aggregate",
        kind="aggregation",
        label=f"{manifest.info.title} mean aggregation",
        depends_on=(grade.id,),
    )
    operations = (*graph.operations, judge, grade, aggregate)
    return _CompiledBenchmark(
        kind=graph.root.kind,
        url4=render(
            iterate(
                _action_call(
                    manifest,
                    context=_control_json(manifest, "load"),
                    intent="Load Benchmark cases.",
                ),
                body=body,
                intent=Text("$case_grade"),
                reduce=reducer,
                slice=None if limit is None else (0, limit),
                on_error="fail",
            )
        ),
        models=graph.root.models,
        operations=operations,
        members=graph.members,
        model_calls_per_case=sum(operation.kind == "model" for operation in graph.operations),
        synthesis_calls_per_case=sum(
            operation.kind == "synthesis" for operation in graph.operations
        ),
    )


@dataclass(frozen=True, slots=True)
class _RecipeGraph:
    root: _ResolvedRecipe
    sources: tuple[Node, ...]
    operations: tuple[_OperationSpec, ...]
    members: tuple[_MemberSpec, ...]


class _RecipeCompiler:
    """Compile content-equivalent Models into one shared, flat URL4 Recipe DAG."""

    def __init__(self, manifest: _BenchmarkManifest) -> None:
        self._manifest = manifest
        self._sources: list[Node] = []
        self._operations: list[_OperationSpec] = []
        self._resolved: dict[int, _ResolvedRecipe] = {}
        self._models_by_content: dict[tuple[str, str | None], _ResolvedRecipe] = {}
        self._active: set[int] = set()
        self._model_count = 0
        self._synthesis_count = 0

    def compile(self, recipe: Recipe) -> _RecipeGraph:
        root = self._recipe(recipe)
        members = ()
        if isinstance(recipe, Fusion):
            members = tuple(
                _MemberSpec(
                    operation_id=self._resolved[id(member)].operation_id,
                    name=member.name,
                    kind=self._resolved[id(member)].kind,
                    models=self._resolved[id(member)].models,
                )
                for member in recipe.members
            )
        return _RecipeGraph(
            root=root,
            sources=tuple(self._sources),
            operations=tuple(self._operations),
            members=members,
        )

    def _recipe(self, recipe: Recipe) -> _ResolvedRecipe:
        identity = id(recipe)
        if resolved := self._resolved.get(identity):
            return resolved
        if identity in self._active:
            raise ValueError(f"Recipe graph contains a cycle at {recipe.name!r}")
        self._active.add(identity)
        if isinstance(recipe, Model):
            resolved = self._model(recipe)
        elif isinstance(recipe, Fusion):
            members = tuple(self._recipe(member) for member in recipe.members)
            resolved = self._fusion(recipe, members)
        else:  # pragma: no cover - Recipe is sealed by public validation
            raise TypeError("recipe must be an sf.Model or sf.Fusion")
        self._active.remove(identity)
        self._resolved[identity] = resolved
        return resolved

    def _model(self, model: Model) -> _ResolvedRecipe:
        content = (model.model, model._sample_id)
        if resolved := self._models_by_content.get(content):
            return resolved
        self._model_count += 1
        binding = f"model_{self._model_count}"
        operation_id = f"op_{binding}"
        self._sources.append(
            src(
                RelExpr(
                    path=_model_route(model.model),
                    context="$question",
                    intent=Text(_url4_text(self._manifest.answer_instructions)),
                    params=self._manifest.answer_params,
                ),
                name=binding,
                weight=0.0,
            )
        )
        self._operations.append(
            _OperationSpec(
                id=operation_id,
                kind="model",
                label=f"{model.name} answer",
                depends_on=(),
            )
        )
        resolved = _ResolvedRecipe(
            reference=f"${binding}",
            operation_id=operation_id,
            name=model.name,
            kind="model",
            models=(model.model,),
        )
        self._models_by_content[content] = resolved
        return resolved

    def _fusion(
        self,
        fusion: Fusion,
        members: tuple[_ResolvedRecipe, ...],
    ) -> _ResolvedRecipe:
        self._synthesis_count += 1
        binding = f"synthesis_{self._synthesis_count}"
        operation_id = f"op_{binding}"
        self._sources.append(
            src(
                RelExpr(
                    path=_model_route(self._manifest.synthesis_model),
                    context=_structured_context(
                        {
                            "question": "$question",
                            "members": {
                                f"member_{index}": {
                                    "name": member.name,
                                    "answer": member.reference,
                                }
                                for index, member in enumerate(members, 1)
                            },
                        }
                    ),
                    intent=Text(_url4_text(self._manifest.synthesis_instructions)),
                    params=self._manifest.synthesis_params,
                ),
                name=binding,
                weight=0.0,
            )
        )
        self._operations.append(
            _OperationSpec(
                id=operation_id,
                kind="synthesis",
                label=f"{fusion.name} synthesis",
                depends_on=tuple(member.operation_id for member in members),
            )
        )
        return _ResolvedRecipe(
            reference=f"${binding}",
            operation_id=operation_id,
            name=fusion.name,
            kind="fusion",
            models=_ordered_unique(
                (
                    *(model for member in members for model in member.models),
                    self._manifest.synthesis_model,
                )
            ),
        )


def _action_call(
    manifest: _BenchmarkManifest,
    *,
    context: str,
    intent: str,
) -> RelExpr:
    return RelExpr(
        path=manifest.route,
        context=context,
        intent=Text(intent),
    )


def _control_json(manifest: _BenchmarkManifest, action: str) -> str:
    return json.dumps(
        {"benchmark": manifest.info.id, "action": action},
        separators=(",", ":"),
    )


def _structured_context(value: dict[str, object]) -> str:
    return render(src(struct(value), name="payload"))


def _model_route(model: str) -> str:
    return "/" + model.removeprefix("/")


def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _parameter(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _url4_text(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\n", "\u2028").replace("\t", " ")
    unsupported = next(
        (character for character in normalized if character < " " or character == "\x7f"),
        None,
    )
    if unsupported is not None:
        raise ValueError(
            f"URL4 text contains unsupported control character U+{ord(unsupported):04X}"
        )
    return normalized.replace("$", "$$")


__all__: list[str] = []
