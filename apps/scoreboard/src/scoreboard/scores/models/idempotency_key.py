from __future__ import annotations

from tortoise import fields

from .base import BaseScoreboardModel


class BaseIdempotencyKey(BaseScoreboardModel):
    class Meta:
        abstract = True

    key = fields.CharField(max_length=255, primary_key=True)
    expires_at = fields.DatetimeField(db_index=True)


class IdempotencyKey(BaseIdempotencyKey):
    class Meta:
        table = "idempotency_keys"

    score = fields.ForeignKeyField(
        "models.Score",
        related_name="idempotency_keys",
        on_delete=fields.OnDelete.CASCADE,
    )
