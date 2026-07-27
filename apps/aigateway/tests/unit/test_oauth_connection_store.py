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
        await store.mark_revoked(connection)
        assert await store.list(alice.id, provider="codex") == []
        assert [
            item.id for item in await store.list(alice.id, provider="codex", status="revoked")
        ] == [connection_id]
        assert await store.get(bob.id, connection_id) is None
        assert await store.list(bob.id) == []


@pytest.mark.asyncio
async def test_complete_active_republishes_metadata_for_an_active_connection() -> None:
    """OME-307 H-1 — complete_active republishes metadata while the connection is active."""
    async with tortoise_test_context(["aigateway.core.auth.models", "aigateway.core.oauth.models"]):
        alice = await Account.create(username="alice", password_hash="hash")
        store = OAuthConnectionStore()
        connection_id = uuid4()
        connection = await store.create_pending(
            account_id=alice.id,
            provider="codex",
            label="pending",
            connection_id=connection_id,
        )
        active = await store.complete(connection, label="old-label", identity=None)

        result = await store.complete_active(active, label="new-label", identity=None)

        assert result is not None
        assert result.status == "active"
        assert result.label == "new-label"
        reread = await store.get(alice.id, connection_id)
        assert reread is not None
        assert reread.label == "new-label"
        assert reread.last_refreshed_at is not None


@pytest.mark.asyncio
async def test_complete_active_does_not_reactivate_a_revoked_connection() -> None:
    """OME-307 H-1 — a refresh republish must not resurrect a revoked connection.

    INVARIANT (OME-307 H-1): complete_active republishes only while the row is still 'active'. A
    concurrent revoke/delete during the refresh network window moves the row out of 'active', so
    the status-fenced CAS updates zero rows and returns None — the refresh surfaces a conflict
    instead of flipping a revoked connection back to active (mirrors complete_pending's fence).
    """
    async with tortoise_test_context(["aigateway.core.auth.models", "aigateway.core.oauth.models"]):
        alice = await Account.create(username="alice", password_hash="hash")
        store = OAuthConnectionStore()
        connection_id = uuid4()
        connection = await store.create_pending(
            account_id=alice.id,
            provider="codex",
            label="pending",
            connection_id=connection_id,
        )
        active = await store.complete(connection, label="codex@example.com", identity=None)

        # A concurrent revoke commits during the refresh network window.
        await store.mark_revoked(active)

        result = await store.complete_active(active, label="codex@example.com", identity=None)

        assert result is None
        reread = await store.get(alice.id, connection_id)
        assert reread is not None
        assert reread.status == "revoked"
