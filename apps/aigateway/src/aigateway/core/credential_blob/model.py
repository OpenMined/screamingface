from __future__ import annotations

import uuid

from tortoise import fields
from tortoise.models import Model


class BaseCredentialBlob(Model):
    class Meta:
        abstract = True

    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    service = fields.CharField(max_length=255, index=True)
    account = fields.CharField(max_length=255, index=True)
    value = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)


class CredentialBlob(BaseCredentialBlob):
    class Meta:
        table = "credential_blobs"
        unique_together = (("service", "account"),)
