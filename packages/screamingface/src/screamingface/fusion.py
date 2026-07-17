"""Public Fusion object compiled to canonical, executable URL4."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from html import escape
from pathlib import Path
from typing import Any, cast

import yaml
from url4 import render

from screamingface.compiler import fusion_recipe, render_question
from screamingface.evaluation import evaluate_sync
from screamingface.model_inputs import (
    ModelConfig,
    ModelInput,
    _FusionMember,
    normalize_model_inputs,
)
from screamingface.models import models as model_catalog
from screamingface.reducers import (
    MajorityVote,
    ModelReducer,
    Reducer,
    reducer_from_config,
)
from screamingface.session import require_session


class Fusion:
    def __init__(
        self,
        name: str,
        models: Sequence[ModelInput],
        reducer: Reducer | None = None,
    ) -> None:
        normalized = "-".join(name.strip().lower().split())
        if not normalized:
            raise ValueError("fusion name must not be empty")
        raw_models = tuple(models)
        if len(raw_models) < 2:
            raise ValueError("a fusion requires at least two models")
        members = normalize_model_inputs(raw_models)
        for member in members:
            model_catalog.get(member.model)
        reducer = reducer or MajorityVote()
        if not isinstance(reducer, Reducer):
            raise TypeError(f"unsupported reducer: {type(reducer).__name__}")
        if isinstance(reducer, MajorityVote):
            reducer = _resolve_tie_breaker(reducer, members)
        if isinstance(reducer, ModelReducer):
            model_catalog.get(reducer.model)
        self.name = normalized
        self._members = members
        self.model_ids = tuple(member.model for member in members)
        self.orchestration = "parallel"
        self.reducer = reducer
        self.expression = fusion_recipe(members, reducer)
        self._url4 = render(self.expression)
        # Kept for compatibility with the first OME-400 SDK draft. New code should
        # use ``url4`` so the value is only surfaced when explicitly requested.
        self.url = self._url4

    @classmethod
    def from_yaml(cls, path: str | Path) -> Fusion:
        """Load a fusion recipe from a local YAML mapping without executing it."""
        config_path = Path(path)
        try:
            document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ValueError(f"could not read fusion YAML {config_path}: {exc}") from exc
        except yaml.YAMLError as exc:
            raise ValueError(f"invalid fusion YAML {config_path}: {exc}") from exc

        config = cls._validate_yaml_document(document)
        return cls(**config)

    @staticmethod
    def _validate_yaml_document(document: Any) -> dict[str, Any]:
        if not isinstance(document, Mapping):
            raise ValueError("fusion YAML must contain a mapping")

        allowed = {"name", "models", "reducer", "reduce", "tie_breaker"}
        unknown = set(document) - allowed
        if unknown:
            fields = ", ".join(sorted(str(field) for field in unknown))
            raise ValueError(f"fusion YAML contains unknown field(s): {fields}")
        missing = {"name", "models"} - set(document)
        if missing:
            fields = ", ".join(sorted(missing))
            raise ValueError(f"fusion YAML is missing required field(s): {fields}")

        return _yaml_fusion_config(document)

    @property
    def url4(self) -> str:
        """Return the canonical, shareable URL4 recipe."""
        return self._url4

    @property
    def models(self) -> tuple[ModelInput, ...]:
        """Return canonical model IDs/dictionaries without exposing internal slots."""

        return tuple(member.to_model_input() for member in self._members)

    def request_for(self, prompt: str) -> str:
        """Return the concrete URL4 request expression for one prompt."""
        return render_question(self.expression, prompt)

    def __repr__(self) -> str:
        rows = [
            (_model_role(self.reducer, member).upper(), member.id, member.model)
            for member in self._members
        ]
        role_width = max(len("ROLE"), *(len(role) for role, _, _ in rows))
        model_width = max(len("MODEL"), *(len(model) for _, _, model in rows))
        if self._shows_model_names():
            name_width = max(len("NAME"), *(len(name) for _, name, _ in rows))
            heading = f"{'ROLE':<{role_width}}  {'NAME':<{name_width}}  {'MODEL':<{model_width}}"
            divider = f"{'-' * role_width}  {'-' * name_width}  {'-' * model_width}"
            lineup = [
                f"{role:<{role_width}}  {name:<{name_width}}  {model:<{model_width}}"
                for role, name, model in rows
            ]
        else:
            heading = f"{'ROLE':<{role_width}}  {'MODEL':<{model_width}}"
            divider = f"{'-' * role_width}  {'-' * model_width}"
            lineup = [f"{role:<{role_width}}  {model:<{model_width}}" for role, _, model in rows]
        return "\n".join(
            [f"Fusion: {self.name}", heading, divider, *lineup, f"Reducer: {self.reducer.name}"]
        )

    def _repr_html_(self) -> str:
        show_names = self._shows_model_names()
        rows = "".join(
            "<tr>"
            f"<td>{_model_role(self.reducer, member)}</td>"
            + (f"<td><code>{escape(member.id)}</code></td>" if show_names else "")
            + f"<td><code>{escape(member.model)}</code></td>"
            "</tr>"
            for member in self._members
        )
        reducer_detail = self._reducer_detail_html()
        name_heading = "<th>Name</th>" if show_names else ""
        return (
            f"<div><strong>Fusion · {escape(self.name)}</strong>"
            f"<table><thead><tr><th>Role</th>{name_heading}<th>Model</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
            f"<p>Reducer: <code>{escape(self.reducer.name)}</code>"
            f"{reducer_detail}</p></div>"
        )

    def _reducer_detail_html(self) -> str:
        if isinstance(self.reducer, ModelReducer):
            return f" · reducer model <code>{escape(self.reducer.model)}</code>"
        return ""

    def _shows_model_names(self) -> bool:
        return any(member.id != member.model for member in self._members)

    def evaluate(
        self,
        benchmark: str,
        first: int = 20,
        seed: int = 0,
        *,
        progress: bool | None = None,
    ):
        return evaluate_sync(
            session=require_session(),
            fusion=self,
            benchmark=benchmark,
            first=first,
            seed=seed,
            show_progress=progress,
        )


def _yaml_fusion_config(document: Mapping) -> dict[str, Any]:
    name = document["name"]
    model_inputs = document["models"]
    if not isinstance(name, str):
        raise ValueError("fusion YAML field 'name' must be a string")
    if not isinstance(model_inputs, list) or not all(
        isinstance(model, (str, Mapping)) for model in model_inputs
    ):
        raise ValueError("fusion YAML field 'models' must be a list of model IDs or mappings")

    if "reducer" in document:
        if "reduce" in document or "tie_breaker" in document:
            raise ValueError("fusion YAML cannot combine 'reducer' with legacy reducer fields")
        reducer_config = document["reducer"]
        if not isinstance(reducer_config, Mapping):
            raise ValueError("fusion YAML field 'reducer' must be a mapping")
        reducer = reducer_from_config(cast("Mapping[str, object]", reducer_config))
    else:
        reducer = _legacy_yaml_reducer(document)

    return {
        "name": name,
        "models": cast("list[str | ModelConfig]", model_inputs),
        "reducer": reducer,
    }


def _legacy_yaml_reducer(document: Mapping) -> Reducer:
    reducer = document.get("reduce", "majority_vote")
    tie_breaker = document.get("tie_breaker")
    if not isinstance(reducer, str):
        raise ValueError("fusion YAML field 'reduce' must be a string")
    if tie_breaker is not None and not isinstance(tie_breaker, str):
        raise ValueError("fusion YAML field 'tie_breaker' must be a model ID string or null")
    if reducer != "majority_vote":
        raise ValueError("legacy fusion YAML supports only reduce: majority_vote")
    return MajorityVote(tie_breaker=tie_breaker)


def _model_role(reducer: Reducer, member: _FusionMember) -> str:
    if isinstance(reducer, MajorityVote) and member.id == reducer.tie_breaker:
        return "Tie breaker"
    return "Model"


def _resolve_tie_breaker(
    reducer: MajorityVote,
    members: tuple[_FusionMember, ...],
) -> MajorityVote:
    requested = reducer.tie_breaker
    if requested is None:
        return reducer
    if any(member.id == requested for member in members):
        return reducer
    model_matches = [member for member in members if member.model == requested]
    if len(model_matches) == 1:
        return replace(reducer, tie_breaker=model_matches[0].id)
    if len(model_matches) > 1:
        raise ValueError("tie_breaker model is ambiguous; use a configured model name")
    raise ValueError("tie_breaker must identify a configured fusion model")
