from __future__ import annotations

import uuid

from tortoise import fields

from .base import BaseScoreboardModel


class BaseScore(BaseScoreboardModel):
    class Meta:
        abstract = True

    id = fields.UUIDField(primary_key=True, default=uuid.uuid4)
    version = fields.IntField(default=1)
    spec_id = fields.CharField(max_length=255, db_index=True)
    url4_expression = fields.TextField()
    submitted_by = fields.CharField(max_length=255, null=True)
    submitted_at = fields.DatetimeField(auto_now_add=True)
    accuracy = fields.FloatField()
    total_questions = fields.IntField()
    correct_questions = fields.IntField()
    ran_with_providers = fields.JSONField()
    ran_at_local = fields.DatetimeField(null=True)
    client_name = fields.CharField(max_length=128, null=True)
    client_version = fields.CharField(max_length=64, null=True)
    client_platform = fields.CharField(max_length=32, null=True)
    verified_by_openmined = fields.BooleanField(default=False)
    metadata = fields.JSONField(null=True)


class Score(BaseScore):
    class Meta:
        table = "scores"
        indexes = (
            ("benchmark_id", "accuracy"),
            ("benchmark_id", "spec_id", "submitted_at"),
        )

    benchmark = fields.ForeignKeyField(
        "models.Benchmark",
        related_name="scores",
        on_delete=fields.OnDelete.RESTRICT,
    )
