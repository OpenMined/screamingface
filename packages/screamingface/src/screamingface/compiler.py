"""Compile shareable and question-bound ScreamingFace URL4 expressions."""

from __future__ import annotations

from collections.abc import Sequence

from url4 import Expression, RelExpr, expr, render, src, struct, text

from screamingface.models import models

_ANSWER_INTENT = "Answer the multiple-choice question"
_RESULT_SCHEMA = "screamingface.panel-result.v1"


def fusion_recipe(model_ids: Sequence[str]) -> Expression:
    """Build the unbound URL4 recipe shared by ``Fusion.url4``."""
    calls = tuple(_panel_call(index, model_id) for index, model_id in enumerate(model_ids, 1))
    return expr(*calls, _result_struct(model_ids))


def bind_question(recipe: Expression, prompt: str) -> Expression:
    """Bind one benchmark prompt without changing the reusable recipe."""
    return expr(src(text(prompt), name="question"), *recipe.sources)


def render_question(recipe: Expression, prompt: str) -> str:
    return render(bind_question(recipe, prompt))


def result_schema() -> str:
    return _RESULT_SCHEMA


def _panel_call(index: int, model_id: str):
    route = models.get(model_id).route
    call = RelExpr(path=route, context="$question", intent=text(_ANSWER_INTENT))
    return src(call, name=f"panel_{index}")


def _result_struct(model_ids: Sequence[str]):
    fields: dict[str, str] = {"schema": _RESULT_SCHEMA}
    for index, model_id in enumerate(model_ids, 1):
        fields[f"panel_{index}_model"] = model_id
        fields[f"panel_{index}_answer"] = f"$panel_{index}"
    return struct(fields)
