"""Compile shareable and question-bound ScreamingFace URL4 expressions."""

from __future__ import annotations

from collections.abc import Sequence

from url4 import Expression, RelExpr, expr, render, src, struct, text

from screamingface.models import models
from screamingface.reducers import MajorityVote, Reducer, Synthesize

_ANSWER_INTENT = "Answer the multiple-choice question"
_SYNTHESIZE_INTENT = "Synthesize the panel answers into one final answer"
_RESULT_SCHEMA = "screamingface.panel-result.v1"
_FUSION_RESULT_SCHEMA = "screamingface.fusion-result.v1"


def fusion_recipe(model_ids: Sequence[str], reducer: Reducer) -> Expression:
    """Build the unbound URL4 recipe shared by ``Fusion.url4``."""
    calls = tuple(_panel_call(index, model_id) for index, model_id in enumerate(model_ids, 1))
    if isinstance(reducer, MajorityVote):
        return expr(*calls, _panel_result_struct(model_ids))
    synthesis = src(_synthesis_call(model_ids, reducer), name="fusion_answer")
    return expr(*calls, synthesis, _fusion_result_struct(model_ids, reducer))


def bind_question(recipe: Expression, prompt: str) -> Expression:
    """Bind one benchmark prompt without changing the reusable recipe."""
    return expr(src(text(prompt), name="question"), *recipe.sources)


def render_question(recipe: Expression, prompt: str) -> str:
    return render(bind_question(recipe, prompt))


def result_schema() -> str:
    return _RESULT_SCHEMA


def fusion_result_schema() -> str:
    return _FUSION_RESULT_SCHEMA


def _panel_call(index: int, model_id: str):
    route = models.get(model_id).route
    call = RelExpr(path=route, context="$question", intent=text(_ANSWER_INTENT))
    return src(call, name=f"panel_{index}")


def _panel_result_struct(model_ids: Sequence[str]):
    fields: dict[str, str] = {"schema": _RESULT_SCHEMA}
    fields.update(_panel_fields(model_ids))
    return struct(fields)


def _synthesis_call(model_ids: Sequence[str], reducer: Synthesize) -> RelExpr:
    route = models.get(reducer.model).route
    context = "\n\n".join(
        ["Question:\n$question"]
        + [
            f"Panel {index} [{model_id}]:\n$panel_{index}"
            for index, model_id in enumerate(model_ids, 1)
        ]
    )
    return RelExpr(
        path=route,
        context=context,
        intent=text(_SYNTHESIZE_INTENT),
        params=(
            ("temperature", str(reducer.temperature)),
            ("max_tokens", str(reducer.max_tokens)),
        ),
    )


def _fusion_result_struct(model_ids: Sequence[str], reducer: Synthesize):
    fields: dict[str, str] = {"schema": _FUSION_RESULT_SCHEMA}
    fields.update(_panel_fields(model_ids))
    fields.update(
        {
            "reducer": reducer.name,
            "synthesizer_model": reducer.model,
            "answer": "$fusion_answer",
        }
    )
    return struct(fields)


def _panel_fields(model_ids: Sequence[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for index, model_id in enumerate(model_ids, 1):
        fields[f"panel_{index}_model"] = model_id
        fields[f"panel_{index}_answer"] = f"$panel_{index}"
    return fields
