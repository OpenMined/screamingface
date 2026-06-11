"""PrivateEntity — one editable markdown entity, keyed by its uuid7 (the `id`)."""

from __future__ import annotations

from tortoise import fields

from screamingface.plugins.state.base import BaseModel


class PrivateEntity(BaseModel):
    class Meta:
        table = "private_entity"
        table_description = "Editable markdown entities for /private/{uuid7} (demo)"
        ordering = ["-updated_at"]

    # `id` (UUID pk = the uuid7), `created_at`, `updated_at` come from BaseModel.
    label = fields.CharField(max_length=200, null=True)
    content = fields.TextField(default="")

    def __str__(self) -> str:
        return f"{self.label or self.id}"
