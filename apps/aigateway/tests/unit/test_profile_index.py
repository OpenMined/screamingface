from __future__ import annotations

import pytest

from aigateway.core.profile_index import INDEX_CREDENTIAL_SERVICE, ProfileIndexStore
from aigateway.core.profile_models import (
    Profile,
    ProfileDefaults,
    ProfileIndex,
    ProfileState,
    profile_id_for,
)

ACCOUNT_ID = "account-1"
OTHER_ACCOUNT_ID = "account-2"


def test_profile_round_trips_through_json() -> None:
    p = Profile(
        id=profile_id_for(ACCOUNT_ID, "anthropic", "default"),
        account_id=ACCOUNT_ID,
        provider="anthropic",
        name="default",
        account_label="user@example.com",
        scopes=["user:inference"],
        last_refreshed_at=None,
        state=ProfileState.AUTHENTICATED,
        defaults=ProfileDefaults(model="anthropic/claude-sonnet-4-5", max_tokens=4096),
    )
    raw = p.model_dump_json()
    restored = Profile.model_validate_json(raw)
    assert restored == p


def test_profile_index_serializes_with_version() -> None:
    idx = ProfileIndex(version=1, profiles=[])
    data = idx.model_dump()
    assert data == {"version": 1, "profiles": []}


@pytest.mark.asyncio
async def test_index_store_returns_empty_index_when_store_empty(credential_blobs) -> None:
    store = ProfileIndexStore(credential_store=credential_blobs.store)
    idx = await store.read()
    assert idx.version == 1
    assert idx.profiles == []


@pytest.mark.asyncio
async def test_index_store_round_trip(credential_blobs) -> None:
    store = ProfileIndexStore(credential_store=credential_blobs.store)
    p = Profile(
        id=profile_id_for(ACCOUNT_ID, "anthropic", "default"),
        account_id=ACCOUNT_ID,
        provider="anthropic",
        name="default",
        defaults=ProfileDefaults(model="anthropic/claude-sonnet-4-5"),
    )
    await store.upsert(p)
    idx = await store.read()
    assert len(idx.profiles) == 1
    assert idx.profiles[0].id == profile_id_for(ACCOUNT_ID, "anthropic", "default")
    assert idx.profiles[0].account_id == ACCOUNT_ID
    raw = credential_blobs.read(INDEX_CREDENTIAL_SERVICE, "default")
    assert profile_id_for(ACCOUNT_ID, "anthropic", "default") in raw


@pytest.mark.asyncio
async def test_index_store_upsert_replaces_by_id(credential_blobs) -> None:
    store = ProfileIndexStore(credential_store=credential_blobs.store)
    await store.upsert(
        Profile(
            id=profile_id_for(ACCOUNT_ID, "anthropic", "default"),
            account_id=ACCOUNT_ID,
            provider="anthropic",
            name="default",
        )
    )
    await store.upsert(
        Profile(
            id=profile_id_for(ACCOUNT_ID, "anthropic", "default"),
            account_id=ACCOUNT_ID,
            provider="anthropic",
            name="default",
            account_label="updated@example.com",
        )
    )
    idx = await store.read()
    assert len(idx.profiles) == 1
    assert idx.profiles[0].account_label == "updated@example.com"


@pytest.mark.asyncio
async def test_index_store_remove(credential_blobs) -> None:
    store = ProfileIndexStore(credential_store=credential_blobs.store)
    await store.upsert(
        Profile(
            id=profile_id_for(ACCOUNT_ID, "anthropic", "default"),
            account_id=ACCOUNT_ID,
            provider="anthropic",
            name="default",
        )
    )
    await store.remove(profile_id_for(ACCOUNT_ID, "anthropic", "default"))
    idx = await store.read()
    assert idx.profiles == []


@pytest.mark.asyncio
async def test_index_store_filters_by_account(credential_blobs) -> None:
    store = ProfileIndexStore(credential_store=credential_blobs.store)
    await store.upsert(
        Profile(
            id=profile_id_for(ACCOUNT_ID, "anthropic", "default"),
            account_id=ACCOUNT_ID,
            provider="anthropic",
            name="default",
        )
    )
    await store.upsert(
        Profile(
            id=profile_id_for(OTHER_ACCOUNT_ID, "anthropic", "default"),
            account_id=OTHER_ACCOUNT_ID,
            provider="anthropic",
            name="default",
        )
    )

    profiles = await store.list(ACCOUNT_ID)
    assert len(profiles) == 1
    assert profiles[0].account_id == ACCOUNT_ID
    assert await store.get(OTHER_ACCOUNT_ID, "anthropic", "default") is not None
    assert await store.get(ACCOUNT_ID, "anthropic", "missing") is None


@pytest.mark.asyncio
async def test_concurrent_upserts_preserve_both_profiles() -> None:
    """The per-store asyncio.Lock must serialize read-modify-write cycles so
    concurrent writers (e.g. chat error-marking racing a PUT api-key) cannot
    drop each other's profiles (SF-244 audit F25)."""
    import asyncio

    class _YieldingStore:
        def __init__(self) -> None:
            self.data: dict[tuple[str, str], str] = {}

        async def read(self, service: str, account: str) -> str | None:
            await asyncio.sleep(0)  # force interleaving between read and write
            return self.data.get((service, account))

        async def write(self, service: str, account: str, value: str) -> None:
            await asyncio.sleep(0)
            self.data[(service, account)] = value

        async def delete(self, service: str, account: str) -> None:
            self.data.pop((service, account), None)

    store = ProfileIndexStore(credential_store=_YieldingStore())
    first = Profile(
        id=profile_id_for(ACCOUNT_ID, "anthropic", "one"),
        account_id=ACCOUNT_ID,
        provider="anthropic",
        name="one",
    )
    second = Profile(
        id=profile_id_for(ACCOUNT_ID, "anthropic", "two"),
        account_id=ACCOUNT_ID,
        provider="anthropic",
        name="two",
        auth_type="api_key",
    )

    await asyncio.gather(store.upsert(first), store.upsert(second))

    profiles = await store.list(ACCOUNT_ID)
    assert {p.name for p in profiles} == {"one", "two"}
    assert {p.auth_type for p in profiles} == {"oauth", "api_key"}
