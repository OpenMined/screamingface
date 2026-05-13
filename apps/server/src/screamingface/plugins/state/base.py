"""Cross-cutting abstract BaseModel for every state-plugin-managed table.

Every downstream plugin model inherits from this. Gives every record a UUID
primary key and audit timestamps (`created_at`, `updated_at`) for free.
"""

from __future__ import annotations

from tortoise import fields
from tortoise.models import Model


class BaseModel(Model):
    class Meta:
        abstract = True

    id = fields.UUIDField(primary_key=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
