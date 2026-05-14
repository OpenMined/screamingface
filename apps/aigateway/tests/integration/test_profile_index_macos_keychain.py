from __future__ import annotations

import os
import shutil
import sys
import uuid

import pytest

from aigateway.core.credential_store import MacOSKeychainStore
from aigateway.core.profile_index import ProfileIndexStore
from aigateway.core.profile_models import Profile, ProfileState, profile_id_for


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform != "darwin", reason="macOS Keychain smoke is macOS-only")
@pytest.mark.skipif(
    os.environ.get("AIGW_MAC_KEYCHAIN_SMOKE") != "1",
    reason="set AIGW_MAC_KEYCHAIN_SMOKE=1 to touch the local macOS Keychain",
)
async def test_profile_index_persists_across_macos_keychain_store_instances() -> None:
    if shutil.which("security") is None:
        pytest.skip("macOS security command is unavailable")

    account_id = f"account-{uuid.uuid4()}"
    service = f"aigateway:index:test:{uuid.uuid4()}"
    credential_store = MacOSKeychainStore()
    profile = Profile(
        id=profile_id_for(account_id, "codex", "default"),
        account_id=account_id,
        provider="codex",
        name="default",
        state=ProfileState.AUTHENTICATED,
    )

    try:
        await ProfileIndexStore(credential_store=credential_store, service=service).upsert(profile)
        restarted_store = ProfileIndexStore(credential_store=credential_store, service=service)

        profiles = await restarted_store.list(account_id, provider="codex")
        assert [p.id for p in profiles] == [profile.id]
    finally:
        credential_store.delete(service, "default")
