from __future__ import annotations

import uuid

from tortoise import fields
from tortoise.models import Model


class BaseAccount(Model):
    class Meta:
        abstract = True

    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    username = fields.CharField(max_length=64, unique=True, index=True)
    password_hash = fields.CharField(max_length=255)
    display_name = fields.CharField(max_length=255, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    last_login_at = fields.DatetimeField(null=True)
    is_active = fields.BooleanField(default=True)
    is_admin = fields.BooleanField(default=False, db_default="false")


class Account(BaseAccount):
    class Meta:
        table = "accounts"
