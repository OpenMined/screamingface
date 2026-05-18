from __future__ import annotations

from uuid import uuid4

import pytest
from tortoise.contrib.test import tortoise_test_context

from aigateway.core.auth.models import Account
from aigateway.core.oauth.identity import AccountIdentity
from aigateway.core.oauth.store import OAuthConnectionStore


@pytest.mark.asyncio
async def test_store_creates_lists_and_scopes_connections() -> None:
    async with tortoise_test_context(["aigateway.core.auth.models", "aigateway.core.oauth.models"]):
        alice = await Account.create(username="alice", password_hash="hash")
        bob = await Account.create(username="bob", password_hash="hash")
        store = OAuthConnectionStore()
        connection_id = uuid4()

        connection = await store.create_pending(
            account_id=alice.id,
            provider="codex",
            label="pending-codex",
            connection_id=connection_id,
        )
        await store.complete(
            connection,
            label="codex@example.com",
            identity=AccountIdentity(
                sub="sub-1",
                email="codex@example.com",
                name="Codex User",
                raw={"sub": "sub-1"},
            ),
        )

        assert await store.get(alice.id, connection_id) is not None
        assert await store.find_by_identity(alice.id, "codex", "sub-1") is not None
        assert await store.find_by_label(alice.id, "codex", "codex@example.com") is not None
        assert [
            item.id for item in await store.list(alice.id, provider="codex", status="active")
        ] == [connection_id]
        assert await store.get(bob.id, connection_id) is None
        assert await store.list(bob.id) == []
