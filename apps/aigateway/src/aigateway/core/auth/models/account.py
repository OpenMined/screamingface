from __future__ import annotations

import uuid

from tortoise import fields
from tortoise.models import Model


class BaseAccount(Model):
    class Meta:
        abstract = True

    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    # 255, not 64: a Cloudflare-identified account is keyed on its username, and that username is
    # the verified email address, which RFC 5321 allows up to 254 characters. See migration 0008.
    username = fields.CharField(max_length=255, unique=True, index=True)
    password_hash = fields.CharField(max_length=255)
    display_name = fields.CharField(max_length=255, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    last_login_at = fields.DatetimeField(null=True)
    is_active = fields.BooleanField(default=True)


class Account(BaseAccount):
    class Meta:
        table = "accounts"
