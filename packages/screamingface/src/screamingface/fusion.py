"""Public Fusion object compiled to canonical, executable URL4."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
from pathlib import Path
from typing import Any

import yaml
from url4 import render

from screamingface.compiler import fusion_recipe, render_question
from screamingface.evaluation import evaluate_sync
from screamingface.models import models as model_catalog
from screamingface.reducers import MajorityVote, Reducer, Synthesize
from screamingface.session import require_session


class Fusion:
    def __init__(
        self,
        name: str,
        models: Sequence[str],
        reducer: Reducer | None = None,
    ) -> None:
        normalized = "-".join(name.strip().lower().split())
        if not normalized:
            raise ValueError("fusion name must not be empty")
        members = tuple(models)
        if len(members) < 2:
            raise ValueError("a fusion requires at least two models")
        for model in members:
            model_catalog.get(model)
        reducer = reducer or MajorityVote()
        if not isinstance(reducer, (MajorityVote, Synthesize)):
            raise TypeError(f"unsupported reducer: {type(reducer).__name__}")
        if isinstance(reducer, MajorityVote) and (
            reducer.tie_breaker is not None and reducer.tie_breaker not in members
        ):
            raise ValueError("tie_breaker must be a member of the fusion")
        if isinstance(reducer, Synthesize):
            model_catalog.get(reducer.model)
        self.name = normalized
        self.models = members
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

        allowed = {"name", "models", "reduce", "tie_breaker"}
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

    def request_for(self, prompt: str) -> str:
        """Return the concrete URL4 request expression for one prompt."""
        return render_question(self.expression, prompt)

    def __repr__(self) -> str:
        rows = [(_member_role(self.reducer, model).upper(), model) for model in self.models]
        role_width = max(len("ROLE"), *(len(role) for role, _ in rows))
        model_width = max(len("MODEL"), *(len(model) for _, model in rows))
        heading = f"{'ROLE':<{role_width}}  {'MODEL':<{model_width}}"
        divider = f"{'-' * role_width}  {'-' * model_width}"
        lineup = [f"{role:<{role_width}}  {model:<{model_width}}" for role, model in rows]
        return "\n".join(
            [f"Fusion: {self.name}", heading, divider, *lineup, f"Reducer: {self.reducer.name}"]
        )

    def _repr_html_(self) -> str:
        rows = "".join(
            "<tr>"
            f"<td>{_member_role(self.reducer, model)}</td>"
            f"<td><code>{escape(model)}</code></td>"
            "</tr>"
            for model in self.models
        )
        reducer_detail = self._reducer_detail_html()
        return (
            f"<div><strong>Fusion · {escape(self.name)}</strong>"
            "<table><thead><tr><th>Role</th><th>Model</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
            f"<p>Reducer: <code>{escape(self.reducer.name)}</code>"
            f"{reducer_detail}</p></div>"
        )

    def _reducer_detail_html(self) -> str:
        if isinstance(self.reducer, Synthesize):
            return f" · synthesizer <code>{escape(self.reducer.model)}</code>"
        return ""

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
    model_ids = document["models"]
    reducer = document.get("reduce", "majority_vote")
    tie_breaker = document.get("tie_breaker")
    if not isinstance(name, str):
        raise ValueError("fusion YAML field 'name' must be a string")
    if not isinstance(model_ids, list) or not all(isinstance(model, str) for model in model_ids):
        raise ValueError("fusion YAML field 'models' must be a list of model ID strings")
    if not isinstance(reducer, str):
        raise ValueError("fusion YAML field 'reduce' must be a string")
    if tie_breaker is not None and not isinstance(tie_breaker, str):
        raise ValueError("fusion YAML field 'tie_breaker' must be a model ID string or null")
    if reducer != "majority_vote":
        raise ValueError("fusion YAML supports only reduce: majority_vote")
    return {
        "name": name,
        "models": model_ids,
        "reducer": MajorityVote(tie_breaker=tie_breaker),
    }


def _member_role(reducer: Reducer, model: str) -> str:
    if isinstance(reducer, MajorityVote) and model == reducer.tie_breaker:
        return "Tie breaker"
    return "Member"
