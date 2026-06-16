"""Persistence for cache entries: encrypted-at-rest, account/profile scoped.

Mirrors ``ORMStore``: the active secret store is resolved lazily at call time
(the app lifespan installs it before any request runs), and writes use the
safe get / create / catch-``IntegrityError`` upsert pattern.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from tortoise.exceptions import IntegrityError

from ..secrets import get_active_secret_store
from ..secrets.mixin import SecretStoreMixin
from .models import RequestCacheEntry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RequestCacheWrite:
    key_hash: str
    key_version: str
    account_id: str
    profile_name: str
    prompt_hash: str
    provider: str
    model: str
    response: dict[str, Any]
    response_size_bytes: int
    expires_at: datetime


class RequestCacheStore(Protocol):
    async def get(
        self, key_hash: str, *, max_age_seconds: int | None = None
    ) -> dict[str, Any] | None: ...

    async def set(self, entry: RequestCacheWrite) -> None: ...

    async def delete_expired(self) -> int: ...


class TortoiseRequestCacheStore:
    """Tortoise-backed implementation of :class:`RequestCacheStore`."""

    def __init__(self, secret_store: SecretStoreMixin | None = None) -> None:
        # Lazy by default: the process-wide active store is installed by the
        # app lifespan. Tests may inject one directly.
        self._secret_store = secret_store

    def _secrets(self) -> SecretStoreMixin:
        return self._secret_store if self._secret_store is not None else get_active_secret_store()

    async def get(
        self, key_hash: str, *, max_age_seconds: int | None = None
    ) -> dict[str, Any] | None:
        row = await RequestCacheEntry.get_or_none(key_hash=key_hash)
        if row is None:
            return None

        now = datetime.now(UTC)
        if row.expires_at <= now:
            return None
        if max_age_seconds is not None and row.created_at < now - timedelta(
            seconds=max_age_seconds
        ):
            return None

        try:
            plaintext = await self._secrets().decrypt(row.response_ciphertext)
            response = json.loads(plaintext)
            if not isinstance(response, dict):
                raise ValueError("cached payload is not a JSON object")
        except Exception:
            # Corrupt or undecryptable entry: drop it so it cannot keep
            # short-circuiting dispatch. Log by hash prefix only.
            logger.warning("request cache entry %s… is corrupt; deleting", key_hash[:12])
            await row.delete()
            return None

        row.hit_count += 1
        row.last_hit_at = now
        await row.save(update_fields=["hit_count", "last_hit_at"])
        return response

    async def set(self, entry: RequestCacheWrite) -> None:
        payload = json.dumps(entry.response, separators=(",", ":"), ensure_ascii=False)
        ciphertext = await self._secrets().encrypt(payload)
        values = {
            "key_version": entry.key_version,
            "account_id": entry.account_id,
            "profile_name": entry.profile_name,
            "prompt_hash": entry.prompt_hash,
            "provider": entry.provider,
            "model": entry.model,
            "response_ciphertext": ciphertext,
            "response_size_bytes": entry.response_size_bytes,
            "expires_at": entry.expires_at,
        }

        row = await RequestCacheEntry.get_or_none(key_hash=entry.key_hash)
        if row is None:
            try:
                await RequestCacheEntry.create(key_hash=entry.key_hash, **values)
                await self.delete_expired()
                return
            except IntegrityError:
                # Lost a concurrent-create race: fall through to update.
                row = await RequestCacheEntry.get(key_hash=entry.key_hash)

        for field, value in values.items():
            setattr(row, field, value)
        await row.save(update_fields=list(values.keys()))
        await self.delete_expired()

    async def delete_expired(self) -> int:
        return await RequestCacheEntry.filter(expires_at__lte=datetime.now(UTC)).delete()
