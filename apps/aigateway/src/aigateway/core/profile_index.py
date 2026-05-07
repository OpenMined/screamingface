from __future__ import annotations

import asyncio
import logging

from .credential_store import CredentialStore, get_credential_store
from .profile_models import Profile, ProfileIndex

logger = logging.getLogger(__name__)

INDEX_KEYCHAIN_SERVICE = "aigateway:index"
_INDEX_ACCOUNT = "default"  # single-tenant; every install has one index


class ProfileIndexStore:
    """Read/write the `aigateway:index` keychain entry under an asyncio.Lock."""

    def __init__(self, credential_store: CredentialStore | None = None) -> None:
        self._store = credential_store or get_credential_store()
        self._lock = asyncio.Lock()

    async def read(self) -> ProfileIndex:
        raw = await asyncio.to_thread(self._store.read, INDEX_KEYCHAIN_SERVICE, _INDEX_ACCOUNT)
        if raw is None:
            return ProfileIndex()
        return ProfileIndex.model_validate_json(raw)

    async def upsert(self, profile: Profile) -> None:
        async with self._lock:
            idx = await self.read()
            idx.profiles = [p for p in idx.profiles if p.id != profile.id] + [profile]
            await asyncio.to_thread(
                self._store.write,
                INDEX_KEYCHAIN_SERVICE,
                _INDEX_ACCOUNT,
                idx.model_dump_json(),
            )

    async def remove(self, profile_id: str) -> None:
        async with self._lock:
            idx = await self.read()
            idx.profiles = [p for p in idx.profiles if p.id != profile_id]
            await asyncio.to_thread(
                self._store.write,
                INDEX_KEYCHAIN_SERVICE,
                _INDEX_ACCOUNT,
                idx.model_dump_json(),
            )

    async def get(self, provider: str, name: str) -> Profile | None:
        idx = await self.read()
        for p in idx.profiles:
            if p.provider == provider and p.name == name:
                return p
        return None
