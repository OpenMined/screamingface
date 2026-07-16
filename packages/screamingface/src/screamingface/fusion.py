"""Public Fusion object compiled to canonical, executable URL4."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml
from url4 import expr, render, src

from screamingface.evaluation import evaluate_sync
from screamingface.models import models as model_catalog
from screamingface.session import require_session


class Fusion:
    def __init__(
        self,
        name: str,
        models: Sequence[str],
        reduce: str = "majority_vote",
        judge: str | None = None,
    ) -> None:
        normalized = "-".join(name.strip().lower().split())
        if not normalized:
            raise ValueError("fusion name must not be empty")
        members = tuple(models)
        if len(members) < 2:
            raise ValueError("a fusion requires at least two models")
        for model in members:
            model_catalog.get(model)
        if reduce != "majority_vote":
            raise ValueError("OME-400 supports only reduce='majority_vote'")
        if judge is not None and judge not in members:
            raise ValueError("judge must be a member of the fusion")
        self.name = normalized
        self.models = members
        self.reduce = reduce
        self.judge = judge
        calls = tuple(src(f"sf-model://{quote(model, safe='/.-')}") for model in members)
        recipe_params = [
            ("sf_version", "1"),
            ("sf_name", normalized),
        ]
        if judge is not None:
            recipe_params.append(("sf_judge", judge))
        self.expression = expr(*calls, intent=reduce, params=recipe_params)
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

        allowed = {"name", "models", "reduce", "judge"}
        unknown = set(document) - allowed
        if unknown:
            fields = ", ".join(sorted(str(field) for field in unknown))
            raise ValueError(f"fusion YAML contains unknown field(s): {fields}")
        missing = {"name", "models"} - set(document)
        if missing:
            fields = ", ".join(sorted(missing))
            raise ValueError(f"fusion YAML is missing required field(s): {fields}")

        name = document["name"]
        models = document["models"]
        reducer = document.get("reduce", "majority_vote")
        judge = document.get("judge")
        if not isinstance(name, str):
            raise ValueError("fusion YAML field 'name' must be a string")
        if not isinstance(models, list) or not all(isinstance(model, str) for model in models):
            raise ValueError("fusion YAML field 'models' must be a list of model ID strings")
        if not isinstance(reducer, str):
            raise ValueError("fusion YAML field 'reduce' must be a string")
        if judge is not None and not isinstance(judge, str):
            raise ValueError("fusion YAML field 'judge' must be a model ID string or null")
        return {"name": name, "models": models, "reduce": reducer, "judge": judge}

    @property
    def url4(self) -> str:
        """Return the canonical, shareable URL4 recipe."""
        return self._url4

    def __repr__(self) -> str:
        rows = [("JUDGE" if model == self.judge else "MEMBER", model) for model in self.models]
        role_width = max(len("ROLE"), *(len(role) for role, _ in rows))
        model_width = max(len("MODEL"), *(len(model) for _, model in rows))
        heading = f"{'ROLE':<{role_width}}  {'MODEL':<{model_width}}"
        divider = f"{'-' * role_width}  {'-' * model_width}"
        lineup = [f"{role:<{role_width}}  {model:<{model_width}}" for role, model in rows]
        return "\n".join(
            [f"Fusion: {self.name}", heading, divider, *lineup, f"Reducer: {self.reduce}"]
        )

    def _repr_html_(self) -> str:
        rows = "".join(
            "<tr>"
            f"<td>{'Judge' if model == self.judge else 'Member'}</td>"
            f"<td><code>{escape(model)}</code></td>"
            "</tr>"
            for model in self.models
        )
        return (
            f"<div><strong>Fusion · {escape(self.name)}</strong>"
            "<table><thead><tr><th>Role</th><th>Model</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
            f"<p>Reducer: <code>{escape(self.reduce)}</code></p></div>"
        )

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
