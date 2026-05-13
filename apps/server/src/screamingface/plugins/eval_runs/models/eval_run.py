"""EvalRun — one row per benchmark run."""

from __future__ import annotations

from tortoise import fields

from screamingface.plugins.state.base import BaseModel


class BaseEvalRun(BaseModel):
    class Meta:
        abstract = True

    spec_name = fields.CharField(max_length=128)
    url4_expression = fields.TextField()
    started_at = fields.DatetimeField()
    finished_at = fields.DatetimeField(null=True)
    status = fields.CharField(max_length=16, default="running")
    accuracy = fields.FloatField(null=True)
    total_questions = fields.IntField(null=True)
    correct_questions = fields.IntField(null=True)
    error = fields.TextField(null=True)

    def __str__(self) -> str:
        return f"{self.spec_name} ({self.status})"


class EvalRun(BaseEvalRun):
    class Meta:
        table = "eval_run"
        table_description = "Eval/benchmark runs"
        ordering = ["-started_at"]
        indexes = (("started_at",), ("spec_name",))
