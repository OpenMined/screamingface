from __future__ import annotations

import asyncio
import logging

from .credential_store import CredentialStore, get_credential_store
from .profile_models import Profile, ProfileIndex

logger = logging.getLogger(__name__)

INDEX_KEYCHAIN_SERVICE = "aigateway:index"
_INDEX_ACCOUNT = "default"  # one keychain entry holds account-scoped profile metadata


class ProfileIndexStore:
    """Read/write the `aigateway:index` keychain entry under an asyncio.Lock."""

    def __init__(
        self,
        credential_store: CredentialStore | None = None,
        *,
        service: str = INDEX_KEYCHAIN_SERVICE,
    ) -> None:
        self._store = credential_store or get_credential_store()
        self._service = service
        self._lock = asyncio.Lock()

    async def read(self) -> ProfileIndex:
        raw = await asyncio.to_thread(self._store.read, self._service, _INDEX_ACCOUNT)
        if raw is None:
            return ProfileIndex()
        return ProfileIndex.model_validate_json(raw)

    async def upsert(self, profile: Profile) -> None:
        if not profile.account_id:
            raise ValueError("profile.account_id is required")
        async with self._lock:
            idx = await self.read()
            idx.profiles = [p for p in idx.profiles if p.id != profile.id] + [profile]
            await asyncio.to_thread(
                self._store.write,
                self._service,
                _INDEX_ACCOUNT,
                idx.model_dump_json(),
            )

    async def remove(self, profile_id: str) -> None:
        async with self._lock:
            idx = await self.read()
            idx.profiles = [p for p in idx.profiles if p.id != profile_id]
            await asyncio.to_thread(
                self._store.write,
                self._service,
                _INDEX_ACCOUNT,
                idx.model_dump_json(),
            )

    async def list(self, account_id: str, provider: str | None = None) -> list[Profile]:
        idx = await self.read()
        return [
            p
            for p in idx.profiles
            if p.account_id == account_id and (provider is None or p.provider == provider)
        ]

    async def get(self, account_id: str, provider: str, name: str) -> Profile | None:
        idx = await self.read()
        for p in idx.profiles:
            if p.account_id == account_id and p.provider == provider and p.name == name:
                return p
        return None
