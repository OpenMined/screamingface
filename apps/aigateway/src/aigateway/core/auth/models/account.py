from __future__ import annotations

import uuid

from tortoise import fields
from tortoise.models import Model


class BaseAccount(Model):
    class Meta:
        abstract = True

    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    username = fields.CharField(max_length=64, unique=True, index=True)
    # INVARIANT: NULL means "this account has no password and never had one" — a
    # federated (Cloudflare Access) identity. `login()` refuses NULL explicitly;
    # it is never a hash that merely fails to verify. See OME-590.
    password_hash = fields.CharField(max_length=255, null=True)
    display_name = fields.CharField(max_length=255, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    last_login_at = fields.DatetimeField(null=True)
    is_active = fields.BooleanField(default=True)
    is_admin = fields.BooleanField(default=False, db_default="false")

    # FEATURE: federated authentication. The identity key is (external_idp,
    # external_subject) — NEVER email, which is mutable at the IdP and can be
    # reassigned to a different human. NULL for local password accounts; SQL
    # treats NULLs as distinct, so local accounts do not collide under the
    # unique constraint.
    external_idp = fields.CharField(max_length=64, null=True)
    external_subject = fields.CharField(max_length=255, null=True)
    email = fields.CharField(max_length=320, null=True, index=True)


class Account(BaseAccount):
    class Meta:
        table = "accounts"
        unique_together = (("external_idp", "external_subject"),)
