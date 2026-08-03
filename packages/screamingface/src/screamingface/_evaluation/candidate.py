"""Compile benchmark-agnostic Model and Fusion values into Candidate URL4."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from url4 import Node, RelExpr, Text, expr, render, src, struct

from screamingface._evaluation.model import (
    _compiled_operation,
    _member_projection,
    _MemberProjection,
)
from screamingface._evaluation.policy import (
    DEFAULT_ANSWER_PROMPT,
    DEFAULT_SYNTHESIS_PROMPT,
    resolved_params,
)
from screamingface.fusion import Fusion
from screamingface.model import Model
from screamingface.operation import OperationInfo
from screamingface.recipe import Recipe


@dataclass(frozen=True, slots=True)
class _CompiledCandidate:
    kind: Literal["model", "fusion"]
    url4: str
    models: tuple[str, ...]
    operations: tuple[OperationInfo, ...]
    members: tuple[_MemberProjection, ...]


@dataclass(frozen=True, slots=True)
class _ResolvedRecipe:
    reference: str
    operation_id: str
    name: str
    kind: Literal["model", "fusion"]
    models: tuple[str, ...]


def compile_candidate(recipe: Recipe, *, default_synthesizer: str) -> _CompiledCandidate:
    """Compile one Candidate once; its only external input is ``$input``."""

    return _CandidateCompiler(default_synthesizer).compile(recipe)


class _CandidateCompiler:
    """Flatten one immutable Recipe into a shared, content-deduplicated URL4 DAG."""

    def __init__(self, default_synthesizer: str) -> None:
        self._default_synthesizer = _canonical_model(default_synthesizer)
        self._sources: list[Node] = []
        self._operations: list[OperationInfo] = []
        self._resolved: dict[int, _ResolvedRecipe] = {}
        self._models_by_content: dict[tuple[object, ...], _ResolvedRecipe] = {}
        self._active: set[int] = set()
        self._model_count = 0
        self._synthesis_count = 0

    def compile(self, recipe: Recipe) -> _CompiledCandidate:
        root = self._recipe(recipe)
        members: tuple[_MemberProjection, ...] = ()
        if isinstance(recipe, Fusion):
            members = tuple(
                _member_projection(
                    operation_id=self._resolved[id(member)].operation_id,
                    name=member.name,
                    kind=self._resolved[id(member)].kind,
                    models=self._resolved[id(member)].models,
                )
                for member in recipe.members
            )
        return _CompiledCandidate(
            kind=root.kind,
            url4=render(expr(*self._sources, intent=Text(root.reference))),
            models=root.models,
            operations=tuple(self._operations),
            members=members,
        )

    def _recipe(self, recipe: Recipe) -> _ResolvedRecipe:
        identity = id(recipe)
        if resolved := self._resolved.get(identity):
            return resolved
        if identity in self._active:
            raise ValueError(f"Candidate graph contains a cycle at {recipe.name!r}")
        self._active.add(identity)
        if isinstance(recipe, Model):
            resolved = self._model(recipe)
        elif isinstance(recipe, Fusion):
            resolved = self._fusion(
                recipe,
                tuple(self._recipe(member) for member in recipe.members),
            )
        else:  # pragma: no cover - the public validation seals Recipe variants
            raise TypeError("candidate must be an sf.Model or sf.Fusion")
        self._active.remove(identity)
        self._resolved[identity] = resolved
        return resolved

    def _model(self, model: Model) -> _ResolvedRecipe:
        prompt = model.prompt or DEFAULT_ANSWER_PROMPT
        params = resolved_params(model.params)
        route = _canonical_model(model.model)
        content = (route, model._sample_id, prompt, params)
        if resolved := self._models_by_content.get(content):
            return resolved

        self._model_count += 1
        binding = f"model_{self._model_count}"
        operation_id = f"op_{binding}"
        self._sources.append(
            src(
                RelExpr(
                    path=_model_route(route),
                    context="$input",
                    intent=Text(_url4_text(prompt)),
                    params=params,
                ),
                name=binding,
                weight=0.0,
            )
        )
        self._operations.append(
            _compiled_operation(
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
            models=(route,),
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
        synthesizer = _canonical_model(fusion.synthesizer or self._default_synthesizer)
        prompt = fusion.prompt or DEFAULT_SYNTHESIS_PROMPT
        self._sources.append(
            src(
                RelExpr(
                    path=_model_route(synthesizer),
                    context=_structured_context(
                        {
                            "question": "$input",
                            "members": {
                                f"member_{index}": {
                                    "name": member.name,
                                    "answer": member.reference,
                                }
                                for index, member in enumerate(members, 1)
                            },
                        }
                    ),
                    intent=Text(_url4_text(prompt)),
                    params=resolved_params(fusion.params),
                ),
                name=binding,
                weight=0.0,
            )
        )
        self._operations.append(
            _compiled_operation(
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
                (*(model for member in members for model in member.models), synthesizer)
            ),
        )


def _structured_context(value: dict[str, object]) -> str:
    return render(src(struct(value), name="payload"))


def _canonical_model(model: str) -> str:
    return model.removeprefix("/")


def _model_route(model: str) -> str:
    return "/" + model


def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _url4_text(value: str) -> str:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\n", "\u2028").replace("\t", " ")
    unsupported = next(
        (character for character in normalized if character < " " or character == "\x7f"),
        None,
    )
    if unsupported is not None:
        raise ValueError(
            f"Candidate prompt contains unsupported control character U+{ord(unsupported):04X}"
        )
    return normalized.replace("$", "$$")


__all__: list[str] = []
