from __future__ import annotations

import uuid

from tortoise import fields
from tortoise.models import Model


class BaseSecretMasterKey(Model):
    class Meta:
        abstract = True

    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    provider = fields.CharField(max_length=32)
    # base64 of 32 raw bytes. LOCAL-dev convenience only; hosted/prod supplies the
    # key via AIGATEWAY_SECRET_KEY and never writes this table.
    key_material = fields.TextField()
    version = fields.CharField(max_length=16, default="v1")
    created_at = fields.DatetimeField(auto_now_add=True)


class SecretMasterKey(BaseSecretMasterKey):
    class Meta:
        table = "secret_master_keys"
        unique_together = (("provider", "version"),)
