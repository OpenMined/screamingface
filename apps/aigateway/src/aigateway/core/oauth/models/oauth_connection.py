from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from tortoise import fields
from tortoise.models import Model

if TYPE_CHECKING:
    from aigateway.core.auth.models import Account


class BaseOAuthConnection(Model):
    class Meta:
        abstract = True

    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    provider = fields.CharField(max_length=64, index=True)
    label = fields.CharField(max_length=255)
    status = fields.CharField(max_length=32, index=True)
    identity_sub = fields.CharField(max_length=255, null=True)
    identity_email = fields.CharField(max_length=320, null=True)
    identity_name = fields.CharField(max_length=255, null=True)
    identity_raw: Any = fields.JSONField(null=True)
    credential_locator: Any = fields.JSONField()
    created_at = fields.DatetimeField(auto_now_add=True)
    last_used_at = fields.DatetimeField(null=True)
    last_refreshed_at = fields.DatetimeField(null=True)
    error_message: Any = fields.TextField(null=True)


class OAuthConnection(BaseOAuthConnection):
    class Meta:
        table = "oauth_connections"
        unique_together = (
            ("account_id", "provider", "status", "identity_sub"),
            ("account_id", "provider", "status", "label"),
        )

    account: fields.ForeignKeyRelation[Account] = fields.ForeignKeyField(
        "models.Account",
        related_name="oauth_connections",
        on_delete=fields.OnDelete.CASCADE,
    )

    if TYPE_CHECKING:
        account_id: uuid.UUID
