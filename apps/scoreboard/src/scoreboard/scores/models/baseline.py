from __future__ import annotations

import uuid

from tortoise import fields

from .base import BaseScoreboardModel


class BaseBaseline(BaseScoreboardModel):
    class Meta:
        abstract = True

    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)
    model_name = fields.CharField(max_length=255)
    accuracy = fields.FloatField()
    source = fields.CharField(max_length=64)
    source_url = fields.CharField(max_length=2048, null=True)
    imported_at = fields.DatetimeField(auto_now_add=True)
    metadata = fields.JSONField(null=True)


class Baseline(BaseBaseline):
    class Meta:
        table = "baselines"
        unique_together = (("benchmark", "model_name", "source"),)

    benchmark = fields.ForeignKeyField(
        "models.Benchmark",
        related_name="baselines",
        on_delete=fields.OnDelete.RESTRICT,
    )
