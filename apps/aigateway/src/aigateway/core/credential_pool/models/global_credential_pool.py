from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from tortoise import fields
from tortoise.models import Model

if TYPE_CHECKING:
    from aigateway.core.auth.models import Account


class GlobalCredentialPool(Model):
    """An admin-provisioned credential shared by every account for one provider.

    Used only when the gateway runs with AIGATEWAY_CREDENTIAL_MODE=shared; the
    secret itself lives in credential_blobs like any other credential (see
    core/credential_pool/store.py), this row is metadata only.
    """

    class Meta:
        table = "global_credential_pools"
        unique_together = (("provider", "label"),)

    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    provider = fields.CharField(max_length=64, index=True)
    label = fields.CharField(max_length=255, default="default", db_default="default")
    auth_type = fields.CharField(max_length=16, default="api_key", db_default="api_key")
    is_active = fields.BooleanField(default=True, db_default="true")
    created_by: fields.ForeignKeyRelation[Account] = fields.ForeignKeyField(
        "models.Account",
        related_name="created_credential_pools",
        on_delete=fields.OnDelete.RESTRICT,
    )
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    if TYPE_CHECKING:
        created_by_id: uuid.UUID
