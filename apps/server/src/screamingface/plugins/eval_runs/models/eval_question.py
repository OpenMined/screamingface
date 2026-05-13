"""EvalQuestion — one row per question evaluated within a run."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tortoise import fields

from screamingface.plugins.state.base import BaseModel

if TYPE_CHECKING:
    from screamingface.plugins.eval_runs.models.eval_run import EvalRun


class BaseEvalQuestion(BaseModel):
    class Meta:
        abstract = True

    idx = fields.IntField()
    question = fields.TextField()
    expected = fields.TextField()
    predicted = fields.TextField(null=True)
    correct = fields.BooleanField(null=True)
    raw_output = fields.TextField(null=True)
    error = fields.TextField(null=True)


class EvalQuestion(BaseEvalQuestion):
    class Meta(BaseEvalQuestion.Meta):
        abstract = False
        table = "eval_question"
        unique_together = (("run", "idx"),)

    run: fields.ForeignKeyRelation[EvalRun] = fields.ForeignKeyField(
        "eval_runs.EvalRun",
        related_name="questions",
        on_delete=fields.CASCADE,
    )
