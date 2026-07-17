"""Compile shareable and question-bound ScreamingFace URL4 expressions."""

from __future__ import annotations

from collections.abc import Sequence
from functools import singledispatch

from url4 import Expression, RelExpr, expr, render, src, struct, text

from screamingface.model_inputs import (
    ParameterValue,
    _FusionMember,
    _make_model_call,
    _ModelCall,
)
from screamingface.models import models
from screamingface.reducers import MajorityVote, ModelReducer, Reducer

_PANEL_RESULT_SCHEMA = "screamingface.panel-result.v2"
_FUSION_RESULT_SCHEMA = "screamingface.fusion-result.v2"


def fusion_recipe(
    members: Sequence[_FusionMember],
    reducer: Reducer,
    *,
    tools: Sequence[str] = (),
) -> Expression:
    """Build the unbound URL4 recipe shared by ``Fusion.url4``."""

    panel_params = (("tools", ",".join(tools)),) if tools else ()
    calls = tuple(
        _panel_call(index, member, panel_params=panel_params)
        for index, member in enumerate(members, 1)
    )
    return expr(*calls, *_reducer_sources(reducer, tuple(members)))


def bind_question(recipe: Expression, prompt: str) -> Expression:
    """Bind one benchmark prompt without changing the reusable recipe."""

    return expr(src(text(prompt), name="question"), *recipe.sources)


def render_question(recipe: Expression, prompt: str) -> str:
    return render(bind_question(recipe, prompt))


def result_schema() -> str:
    return _PANEL_RESULT_SCHEMA


def fusion_result_schema() -> str:
    return _FUSION_RESULT_SCHEMA


def render_model_request(
    *,
    model: str,
    intent: str,
    context: str | None = None,
    params: dict[str, ParameterValue] | None = None,
) -> str:
    """Render one internal model call through the same URL4 path as a fusion.

    When ``context`` is provided it is bound as URL4 data and passed separately
    from the model intent. Model-route adapters can therefore preserve distinct
    user/context and system/intent messages without ScreamingFace contacting a
    provider directly.
    """

    models.get(model)
    call = _make_model_call(model=model, prompt=intent, params=params)
    if context is None:
        return render(_url4_model_call(call))
    context_name = "model_context"
    return render(
        expr(
            src(text(context), name=context_name),
            _url4_model_call(call, context=f"${context_name}"),
        )
    )


def _panel_call(
    index: int,
    member: _FusionMember,
    *,
    panel_params: tuple[tuple[str, str], ...],
):
    return src(
        _url4_model_call(member.call, additional_params=panel_params),
        name=f"panel_{index}",
    )


@singledispatch
def _reducer_sources(reducer: Reducer, members: tuple[_FusionMember, ...]) -> tuple:
    raise TypeError(f"unsupported reducer: {type(reducer).__name__}")


@_reducer_sources.register
def _(reducer: MajorityVote, members: tuple[_FusionMember, ...]) -> tuple:
    del reducer
    return (_panel_result_struct(members),)


@_reducer_sources.register
def _(reducer: ModelReducer, members: tuple[_FusionMember, ...]) -> tuple:
    panel_answers = src(_panel_answers_struct(members), name="panel_answers")
    answer = src(_model_reducer_call(reducer), name="fusion_answer")
    result = _fusion_result_struct(members, reducer)
    return panel_answers, answer, result


def _panel_result_struct(members: Sequence[_FusionMember]):
    fields: dict[str, str] = {"schema": _PANEL_RESULT_SCHEMA}
    fields.update(_panel_fields(members))
    return struct(fields)


def _panel_answers_struct(members: Sequence[_FusionMember]):
    fields: dict[str, str] = {}
    for index, member in enumerate(members, 1):
        fields[f"panel_{index}_id"] = member.id
        fields[f"panel_{index}_model"] = member.model
        fields[f"panel_{index}_answer"] = f"$panel_{index}"
    return struct(fields)


def _model_reducer_call(reducer: ModelReducer) -> RelExpr:
    return _url4_model_call(reducer._call)


def _url4_model_call(
    call: _ModelCall,
    *,
    context: str | None = None,
    additional_params: tuple[tuple[str, str], ...] = (),
) -> RelExpr:
    route = models.get(call.model).route
    return RelExpr(
        path=route,
        context=context,
        intent=text(call.prompt),
        params=(*additional_params, *_url4_params(call.parameter_items)),
    )


def _fusion_result_struct(members: Sequence[_FusionMember], reducer: ModelReducer):
    fields: dict[str, str] = {"schema": _FUSION_RESULT_SCHEMA}
    fields.update(_panel_fields(members))
    fields.update(
        {
            "reducer": reducer.kind,
            "reducer_model": reducer.model,
            "answer": "$fusion_answer",
        }
    )
    return struct(fields)


def _panel_fields(members: Sequence[_FusionMember]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for index, member in enumerate(members, 1):
        fields[f"panel_{index}_id"] = member.id
        fields[f"panel_{index}_model"] = member.model
        fields[f"panel_{index}_answer"] = f"$panel_{index}"
    return fields


def _url4_params(
    items: tuple[tuple[str, ParameterValue], ...],
) -> tuple[tuple[str, str], ...]:
    return tuple((key, _parameter_text(value)) for key, value in items)


def _parameter_text(value: ParameterValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
