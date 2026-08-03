"""Compile benchmark-agnostic Model and Fusion values into Candidate URL4."""

from __future__ import annotations

from collections.abc import Mapping
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
    DEFAULT_SYNTHESIZER,
    resolved_params,
)
from screamingface.corrective import MAX_ATTEMPTS, CorrectiveEnsemble
from screamingface.errors import PlanningError
from screamingface.fusion import Fusion
from screamingface.model import Model
from screamingface.operation import OperationInfo
from screamingface.recipe import Recipe


@dataclass(frozen=True, slots=True)
class _CompiledCandidate:
    kind: Literal["model", "fusion", "corrective"]
    url4: str
    models: tuple[str, ...]
    operations: tuple[OperationInfo, ...]
    members: tuple[_MemberProjection, ...]


@dataclass(frozen=True, slots=True)
class _ResolvedRecipe:
    reference: str
    operation_id: str
    name: str
    kind: Literal["model", "fusion", "corrective"]
    models: tuple[str, ...]


def compile_candidate(
    recipe: Recipe,
    actions: Mapping[str, str] | None = None,
) -> _CompiledCandidate:
    """Compile one Candidate once; its external inputs are ``$input`` (+ ``$case``).

    ``actions`` is the benchmark's advertised verifier-action route map — required
    only by recipes that check their own drafts mid-flight (CorrectiveEnsemble).
    """

    return _CandidateCompiler(actions).compile(recipe)


class _CandidateCompiler:
    """Flatten one immutable Recipe into a shared, content-deduplicated URL4 DAG."""

    def __init__(self, actions: Mapping[str, str] | None = None) -> None:
        self._actions = actions
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
        elif isinstance(recipe, CorrectiveEnsemble):
            resolved = self._corrective(recipe)
        else:  # pragma: no cover - the public validation seals Recipe variants
            raise TypeError("candidate must be an sf.Model, sf.Fusion, or sf.CorrectiveEnsemble")
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
        synthesizer = _canonical_model(fusion.synthesizer or DEFAULT_SYNTHESIZER)
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

    def _corrective(self, ensemble: CorrectiveEnsemble) -> _ResolvedRecipe:
        actions = self._verifier_actions(ensemble)
        letters = "abcd"[: len(ensemble.members)]
        for attempt in range(1, MAX_ATTEMPTS + 1):
            for letter, member in zip(letters, ensemble.members, strict=True):
                self._corrective_member(actions, letter, member, attempt)
            self._corrective_selection(actions, ensemble, letters, attempt)
        self._sources.append(
            src(
                RelExpr(
                    path=actions["finalize"],
                    context=_action_payload(
                        {
                            key: value
                            for attempt in range(1, MAX_ATTEMPTS + 1)
                            for key, value in (
                                (f"s{attempt}", f"$ce_sel_{attempt}"),
                                (f"f{attempt}", f"$ce_selfb_{attempt}"),
                            )
                        }
                    ),
                    intent=Text("finalize"),
                ),
                name="ce_final",
                weight=0.0,
            )
        )
        member_ops = []
        for letter, member in zip(letters, ensemble.members, strict=True):
            operation_id = f"op_ce_member_{letter}"
            self._operations.append(
                _compiled_operation(
                    id=operation_id,
                    kind="model",
                    label=f"{member.name} member",
                    depends_on=(),
                )
            )
            member_ops.append((operation_id, member))
        judge_route = _canonical_model(ensemble.judge.model)
        self._operations.append(
            _compiled_operation(
                id="op_ce_judge",
                kind="synthesis",
                label=f"{ensemble.judge.name} judge",
                depends_on=tuple(operation_id for operation_id, _ in member_ops),
            )
        )
        return _ResolvedRecipe(
            reference="$ce_final",
            operation_id="op_ce_judge",
            name=ensemble.name,
            kind="corrective",
            models=_ordered_unique(
                (
                    *(_canonical_model(member.model) for member in ensemble.members),
                    judge_route,
                )
            ),
        )

    def _verifier_actions(self, ensemble: CorrectiveEnsemble) -> Mapping[str, str]:
        required = ("check", "select", "finalize")
        actions = self._actions or {}
        if not all(isinstance(actions.get(name), str) for name in required):
            raise PlanningError(
                f"Candidate {ensemble.name!r} requires a verifier benchmark: "
                "CorrectiveEnsemble checks its drafts against the benchmark's own "
                "checker, and this benchmark advertises no check/select/finalize "
                "actions. Evaluate it against a verifier benchmark such as "
                "benchmark='ifeval', method='single_pass'.",
                code="benchmark_without_verifier",
                permanent=True,
            )
        return actions

    def _corrective_member(
        self,
        actions: Mapping[str, str],
        letter: str,
        member: Model,
        attempt: int,
    ) -> None:
        if attempt == 1:
            member_context = "$input"
        else:
            previous = attempt - 1
            member_context = _structured_context(
                {
                    "request": "$input",
                    "your_previous_answer": f"$ce_ans_{letter}_{previous}",
                    "checker_feedback": f"$ce_fb_{letter}_{previous}",
                    "task": _RETRY_TASK,
                }
            )
        self._sources.append(
            src(
                RelExpr(
                    path=_model_route(_canonical_model(member.model)),
                    context=member_context,
                    intent=Text(_url4_text(member.prompt or DEFAULT_ANSWER_PROMPT)),
                    params=resolved_params(member.params),
                ),
                name=f"ce_ans_{letter}_{attempt}",
                weight=0.0,
            )
        )
        # INVARIANT: members only ever see the feedback TEXT — the raw check record
        # (which names the private instruction ids) flows exclusively between engine
        # routes, so a member cannot learn the forgery template.
        self._sources.append(
            src(
                RelExpr(
                    path=actions["check"],
                    context=f"$ce_ans_{letter}_{attempt}",
                    intent=Text("$case"),
                ),
                name=f"ce_chk_{letter}_{attempt}",
                weight=0.0,
            )
        )
        self._sources.append(
            src(
                RelExpr(
                    path=actions["check"],
                    context=f"$ce_chk_{letter}_{attempt}",
                    intent=Text("feedback"),
                ),
                name=f"ce_fb_{letter}_{attempt}",
                weight=0.0,
            )
        )

    def _corrective_selection(
        self,
        actions: Mapping[str, str],
        ensemble: CorrectiveEnsemble,
        letters: str,
        attempt: int,
    ) -> None:
        self._sources.append(
            src(
                RelExpr(
                    path=_model_route(_canonical_model(ensemble.judge.model)),
                    context=_structured_context(
                        {
                            "request": "$input",
                            "candidates": {
                                letter: {
                                    "answer": f"$ce_ans_{letter}_{attempt}",
                                    "verdict": f"$ce_fb_{letter}_{attempt}",
                                }
                                for letter in letters
                            },
                        }
                    ),
                    intent=Text(_url4_text(_JUDGE_PROMPT)),
                    params=resolved_params(ensemble.judge.params),
                ),
                name=f"ce_judge_{attempt}",
                weight=0.0,
            )
        )
        self._sources.append(
            src(
                RelExpr(
                    path=actions["select"],
                    context=_action_payload(
                        {
                            "pick": f"$ce_judge_{attempt}",
                            **{letter: f"$ce_ans_{letter}_{attempt}" for letter in letters},
                        }
                    ),
                    intent=Text("select"),
                ),
                name=f"ce_sel_{attempt}",
                weight=0.0,
            )
        )
        self._sources.append(
            src(
                RelExpr(
                    path=actions["check"],
                    context=f"$ce_sel_{attempt}",
                    intent=Text("$case"),
                ),
                name=f"ce_selchk_{attempt}",
                weight=0.0,
            )
        )
        self._sources.append(
            src(
                RelExpr(
                    path=actions["check"],
                    context=f"$ce_selchk_{attempt}",
                    intent=Text("feedback"),
                ),
                name=f"ce_selfb_{attempt}",
                weight=0.0,
            )
        )


_RETRY_TASK = (
    "Your previous answer failed the checker feedback above. Write a completely new "
    "answer to the request that satisfies every stated requirement."
)
_JUDGE_PROMPT = (
    "Pick the best candidate answer for the request. Prefer candidates whose verdict "
    "is PASSED. Reply with exactly one letter naming your pick and nothing else."
)


def _action_payload(value: dict[str, object]) -> str:
    # WHY bare struct (no named-src wrapper): _structured_context's `src` envelope is
    # resolved by MODEL-call lowering; a deterministic endpoint receives it as empty
    # context. `render(struct(...))` reaches endpoints as escaped JSON (probe-proven).
    return render(struct(value))


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
