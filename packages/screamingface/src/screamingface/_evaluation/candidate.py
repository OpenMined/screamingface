"""Compile benchmark-agnostic Model and Fusion values into Candidate URL4."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from url4 import Node, RelExpr, RenderError, Text, expr, render, src

from screamingface._evaluation.model import (
    _compiled_operation,
    _member_projection,
    _MemberProjection,
    _model_parameter_assignment,
    _ModelParameterAssignment,
)
from screamingface._evaluation.policy import (
    DEFAULT_ANSWER_PROMPT,
    DEFAULT_SYNTHESIS_PROMPT,
    resolved_params,
)
from screamingface.errors import PlanningError
from screamingface.fusion import Fusion
from screamingface.model import Model
from screamingface.operation import OperationInfo
from screamingface.recipe import Recipe


@dataclass(frozen=True, slots=True)
class _CompiledCandidate:
    kind: Literal["model", "fusion"]
    url4: str | None
    models: tuple[str, ...]
    operations: tuple[OperationInfo, ...]
    members: tuple[_MemberProjection, ...]
    member_expressions: tuple[_MemberExpression, ...]
    parameter_assignments: tuple[_ModelParameterAssignment, ...]
    # WHY: a structural Benchmark may bind this component separately through
    # `$candidate_synthesizer`; a solo Model has no such component.
    synthesizer: _SynthesizerExpression | None


@dataclass(frozen=True, slots=True)
class _MemberExpression:
    """One direct Fusion member exposed through the universal binding contract."""

    name: str
    kind: Literal["model", "fusion"]
    url4: str | None


@dataclass(frozen=True, slots=True)
class _SynthesizerExpression:
    """The explicit Fusion component exposed by `$candidate_synthesizer`."""

    model: str
    operation: OperationInfo
    parameter_assignment: _ModelParameterAssignment | None
    url4: str


@dataclass(frozen=True, slots=True)
class _ResolvedRecipe:
    reference: str
    operation_id: str
    name: str
    kind: Literal["model", "fusion"]
    models: tuple[str, ...]


def compile_candidate(recipe: Recipe) -> _CompiledCandidate:
    """Compile a Candidate, retaining structural members when a Fusion is incomplete."""

    try:
        return _CandidateCompiler().compile(recipe)
    except RenderError as exc:
        raise PlanningError(
            "The SDK could not encode Candidate generation parameters for the SF Engine",
            code="invalid_candidate_parameter",
            permanent=True,
            details={"reason": str(exc)},
        ) from exc


class _CandidateCompiler:
    """Flatten one immutable Recipe into a shared, content-deduplicated URL4 DAG."""

    def __init__(self) -> None:
        self._sources: list[Node] = []
        self._operations: list[OperationInfo] = []
        self._parameter_assignments: list[_ModelParameterAssignment] = []
        self._resolved: dict[int, _ResolvedRecipe] = {}
        self._models_by_content: dict[tuple[object, ...], _ResolvedRecipe] = {}
        self._active: set[int] = set()
        self._model_count = 0
        self._synthesis_count = 0

    def compile(self, recipe: Recipe, *, synthesis_root: bool = False) -> _CompiledCandidate:
        root = self._recipe(recipe, synthesis=synthesis_root)
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
        member_expressions = (
            tuple(
                _MemberExpression(
                    name=member.name,
                    kind="model" if isinstance(member, Model) else "fusion",
                    url4=compile_candidate(member).url4,
                )
                for member in recipe.members
            )
            if isinstance(recipe, Fusion)
            else ()
        )
        synthesizer = None
        if isinstance(recipe, Fusion) and recipe.synthesizer is not None:
            synthesizer_model = _canonical_model(recipe.synthesizer)
            # INVARIANT: structural Benchmarks own their Judge instructions, while the
            # Candidate still owns the selected model's generation parameters. Reusing
            # `recipe.prompt` here would leak ordinary blending policy into a different
            # Benchmark role; dropping `recipe.params` would silently change the system.
            expression = _CandidateCompiler().compile(
                Model(synthesizer_model, params=recipe.params),
                synthesis_root=True,
            )
            assert expression.url4 is not None
            operation_id = "op_candidate_synthesizer"
            synthesizer = _SynthesizerExpression(
                model=synthesizer_model,
                operation=_compiled_operation(
                    id=operation_id,
                    kind="synthesis",
                    label=f"{recipe.name} synthesizer",
                    depends_on=(),
                ),
                parameter_assignment=(
                    _model_parameter_assignment(
                        operation_id=operation_id,
                        model=synthesizer_model,
                        params=recipe.params,
                    )
                    if recipe.params
                    else None
                ),
                url4=expression.url4,
            )
        return _CompiledCandidate(
            kind=root.kind,
            url4=(
                render(expr(*self._sources, intent=Text(root.reference)))
                if root.reference
                else None
            ),
            models=root.models,
            operations=tuple(self._operations),
            members=members,
            member_expressions=member_expressions,
            synthesizer=synthesizer,
            parameter_assignments=tuple(self._parameter_assignments),
        )

    def _recipe(
        self,
        recipe: Recipe,
        *,
        synthesis: bool = False,
    ) -> _ResolvedRecipe:
        identity = id(recipe)
        if resolved := self._resolved.get(identity):
            return resolved
        if identity in self._active:
            raise ValueError(f"Candidate graph contains a cycle at {recipe.name!r}")
        self._active.add(identity)
        if isinstance(recipe, Model):
            resolved = self._model(recipe, synthesis=synthesis)
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

    def _model(
        self,
        model: Model,
        *,
        synthesis: bool,
    ) -> _ResolvedRecipe:
        prompt = model.prompt or DEFAULT_ANSWER_PROMPT
        params = _synthesis_params(model.params) if synthesis else resolved_params(model.params)
        route = _canonical_model(model.model)
        content = (route, model._sample_id, prompt, params)
        if resolved := self._models_by_content.get(content):
            self._record_parameter_assignment(resolved.operation_id, route, model.params)
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
        self._record_parameter_assignment(operation_id, route, model.params)
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
        models = tuple(model for member in members for model in member.models)
        if fusion.synthesizer is None or any(not member.reference for member in members):
            return _ResolvedRecipe(
                reference="",
                operation_id=operation_id,
                name=fusion.name,
                kind="fusion",
                models=_ordered_unique(models),
            )
        synthesizer = _canonical_model(fusion.synthesizer)
        prompt = fusion.prompt or DEFAULT_SYNTHESIS_PROMPT
        member_name_refs: list[str] = []
        for index, member in enumerate(members, 1):
            name_binding = f"{binding}_member_{index}_name"
            # Keep labels out of raw URL4 syntax: public Recipe names may legitimately contain
            # `$` or `)`, which must remain model-visible text rather than become interpolation
            # or close the synthesis context.
            self._sources.append(src(Text(_url4_text(member.name)), name=name_binding))
            member_name_refs.append(f"${name_binding}")
        self._sources.append(
            src(
                RelExpr(
                    path=_model_route(synthesizer),
                    context=_fusion_context(members, tuple(member_name_refs)),
                    intent=Text(_url4_text(prompt)),
                    params=_synthesis_params(fusion.params),
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
        self._record_parameter_assignment(operation_id, synthesizer, fusion.params)
        return _ResolvedRecipe(
            reference=f"${binding}",
            operation_id=operation_id,
            name=fusion.name,
            kind="fusion",
            models=_ordered_unique((*models, synthesizer)),
        )

    def _record_parameter_assignment(
        self,
        operation_id: str,
        model: str,
        params: Mapping[str, str | int | float | bool],
    ) -> None:
        if not params:
            return
        self._parameter_assignments.append(
            _model_parameter_assignment(
                operation_id=operation_id,
                model=model,
                params=params,
            )
        )


def _fusion_context(
    members: tuple[_ResolvedRecipe, ...],
    member_name_refs: tuple[str, ...],
) -> str:
    line = "\u2028"
    section_separator = line * 2
    sections = [
        f"=== Model {index} ({name_ref}) ==={line}{member.reference}"
        for index, (member, name_ref) in enumerate(
            zip(members, member_name_refs, strict=True),
            1,
        )
    ]
    return (
        f"Question:{line}$input{line}{line}"
        f"Panel answers (one per model):{line}"
        f"{section_separator.join(sections)}"
    )


def _synthesis_params(
    overrides: Mapping[str, str | int | float | bool],
) -> tuple[tuple[str, str], ...]:
    """Keep every Fusion writer retrieval-free, independent of Benchmark policy."""

    return (*resolved_params(overrides), ("web_search", "false"))


def _canonical_model(model: str) -> str:
    return model.removeprefix("/")


def _model_route(model: str) -> str:
    if _MODEL_ROUTE_RE.fullmatch(model) is None:
        raise PlanningError(
            f"Model {model!r} cannot be addressed by this Engine because its id is not a "
            "valid URL4 expression path. Choose a model returned by `sf.models.list()`.",
            code="invalid_model_route",
            permanent=True,
            details={"model": model},
        )
    return "/" + model


_MODEL_ROUTE_RE = re.compile(r"[A-Za-z0-9\-_.~]+(?:/[A-Za-z0-9\-_.~]+)*", re.ASCII)


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
