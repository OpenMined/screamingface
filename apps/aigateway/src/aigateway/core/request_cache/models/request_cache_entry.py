from __future__ import annotations

import uuid

from tortoise import fields
from tortoise.models import Model


class BaseRequestCacheEntry(Model):
    class Meta:
        abstract = True

    id = fields.UUIDField(pk=True, default=uuid.uuid4)
    key_hash = fields.CharField(max_length=64, unique=True, index=True)
    key_version = fields.CharField(max_length=32)
    account_id = fields.CharField(max_length=64, index=True)
    profile_name = fields.CharField(max_length=128, index=True)
    prompt_hash = fields.CharField(max_length=64, index=True)
    provider = fields.CharField(max_length=64, index=True)
    model = fields.CharField(max_length=255, index=True)
    response_ciphertext = fields.TextField()
    response_size_bytes = fields.IntField()
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)
    # INVARIANT (OME-305 plan §4.2): NULL means "never expires" and every global v2 row writes NULL.
    # Nullable rather than a far-future sentinel so "indefinite" is a distinct state a reader cannot
    # mistake for a TTL, and so a later configurable-TTL feature can adopt the column unchanged.
    # v1 rows keep the non-NULL expiry they were written with; `get()` treats NULL as unexpired.
    expires_at = fields.DatetimeField(index=True, null=True)
    last_hit_at = fields.DatetimeField(null=True)
    hit_count = fields.IntField(default=0)


class RequestCacheEntry(BaseRequestCacheEntry):
    class Meta:
        table = "request_cache_entries"
        indexes = (("account_id", "profile_name", "provider", "expires_at"),)
