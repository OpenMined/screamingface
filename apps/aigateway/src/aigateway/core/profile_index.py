from __future__ import annotations

import asyncio
import logging

from .credential_blob.store import CredentialBlobStore, ORMStore
from .profile_models import Profile, ProfileIndex

logger = logging.getLogger(__name__)

INDEX_CREDENTIAL_SERVICE = "aigateway:index"
_LEGACY_INDEX_ACCOUNT = "default"
_INDEX_ACCOUNT_PREFIX = "account:"


def _index_account_for(account_id: str) -> str:
    return f"{_INDEX_ACCOUNT_PREFIX}{account_id}"


def _account_id_from_profile_id(profile_id: str) -> str:
    account_id, separator, _rest = profile_id.partition(":")
    if not separator or not account_id:
        raise ValueError("profile_id must include account_id")
    return account_id


class ProfileIndexStore:
    """Read/write account-scoped `aigateway:index` credential blobs."""

    def __init__(self, credential_store: CredentialBlobStore | None = None) -> None:
        self._store = credential_store or ORMStore()
        self._lock = asyncio.Lock()

    async def read(self, account_id: str | None = None) -> ProfileIndex:
        account = _LEGACY_INDEX_ACCOUNT if account_id is None else _index_account_for(account_id)
        raw = await self._store.read(INDEX_CREDENTIAL_SERVICE, account)
        if raw is None:
            if account_id is not None:
                return await self._read_legacy_account_index(account_id)
            return ProfileIndex()
        return ProfileIndex.model_validate_json(raw)

    async def _read_legacy_account_index(self, account_id: str) -> ProfileIndex:
        raw = await self._store.read(INDEX_CREDENTIAL_SERVICE, _LEGACY_INDEX_ACCOUNT)
        if raw is None:
            return ProfileIndex()
        legacy = ProfileIndex.model_validate_json(raw)
        return ProfileIndex(profiles=[p for p in legacy.profiles if p.account_id == account_id])

    async def upsert(self, profile: Profile) -> None:
        if not profile.account_id:
            raise ValueError("profile.account_id is required")

        async with self._lock:
            legacy_seed = await self._read_legacy_account_index(profile.account_id)

            def mutate(raw: str | None) -> str:
                # WHY: legacy installs used one global row; seed the account row lazily
                # so existing profiles survive the storage-shape split.
                idx = legacy_seed if raw is None else ProfileIndex.model_validate_json(raw)
                idx.profiles = [p for p in idx.profiles if p.id != profile.id] + [profile]
                return idx.model_dump_json()

            await self._store.mutate(
                INDEX_CREDENTIAL_SERVICE,
                _index_account_for(profile.account_id),
                mutate,
            )

    async def remove(self, profile_id: str) -> None:
        account_id = _account_id_from_profile_id(profile_id)

        async with self._lock:
            legacy_seed = await self._read_legacy_account_index(account_id)

            def mutate(raw: str | None) -> str:
                idx = legacy_seed if raw is None else ProfileIndex.model_validate_json(raw)
                idx.profiles = [p for p in idx.profiles if p.id != profile_id]
                return idx.model_dump_json()

            await self._store.mutate(
                INDEX_CREDENTIAL_SERVICE,
                _index_account_for(account_id),
                mutate,
            )

    async def list(self, account_id: str, provider: str | None = None) -> list[Profile]:
        idx = await self.read(account_id)
        return [
            p
            for p in idx.profiles
            if p.account_id == account_id and (provider is None or p.provider == provider)
        ]

    async def get(self, account_id: str, provider: str, name: str) -> Profile | None:
        idx = await self.read(account_id)
        for p in idx.profiles:
            if p.account_id == account_id and p.provider == provider and p.name == name:
                return p
        return None
