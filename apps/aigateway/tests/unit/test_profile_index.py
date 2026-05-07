from __future__ import annotations

import pytest

from aigateway.core.profile_index import INDEX_KEYCHAIN_SERVICE, ProfileIndexStore
from aigateway.core.profile_models import Profile, ProfileDefaults, ProfileIndex, ProfileState


def test_profile_round_trips_through_json() -> None:
    p = Profile(
        id="anthropic:default",
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
async def test_index_store_returns_empty_index_when_keychain_empty(fake_keychain) -> None:
    store = ProfileIndexStore(credential_store=fake_keychain)
    idx = await store.read()
    assert idx.version == 1
    assert idx.profiles == []


@pytest.mark.asyncio
async def test_index_store_round_trip(fake_keychain) -> None:
    store = ProfileIndexStore(credential_store=fake_keychain)
    p = Profile(
        id="anthropic:default",
        provider="anthropic",
        name="default",
        defaults=ProfileDefaults(model="anthropic/claude-sonnet-4-5"),
    )
    await store.upsert(p)
    idx = await store.read()
    assert len(idx.profiles) == 1
    assert idx.profiles[0].id == "anthropic:default"
    raw = fake_keychain.read(INDEX_KEYCHAIN_SERVICE, "default")
    assert "anthropic:default" in raw


@pytest.mark.asyncio
async def test_index_store_upsert_replaces_by_id(fake_keychain) -> None:
    store = ProfileIndexStore(credential_store=fake_keychain)
    await store.upsert(Profile(id="anthropic:default", provider="anthropic", name="default"))
    await store.upsert(
        Profile(
            id="anthropic:default",
            provider="anthropic",
            name="default",
            account_label="updated@example.com",
        )
    )
    idx = await store.read()
    assert len(idx.profiles) == 1
    assert idx.profiles[0].account_label == "updated@example.com"


@pytest.mark.asyncio
async def test_index_store_remove(fake_keychain) -> None:
    store = ProfileIndexStore(credential_store=fake_keychain)
    await store.upsert(Profile(id="anthropic:default", provider="anthropic", name="default"))
    await store.remove("anthropic:default")
    idx = await store.read()
    assert idx.profiles == []
