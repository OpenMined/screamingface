from __future__ import annotations

from uuid import uuid4

import pytest

from aigateway.core.oauth.store import OAuthConnectionStore


@pytest.mark.parametrize("status", ["pending", "active", "error"])
def test_label_exists_checks_every_non_revoked_status(authenticated_client, status: str) -> None:
    account_id = authenticated_client.get("/v1/auth/me").json()["id"]
    label = f"label-{status}"

    async def scenario() -> bool:
        store = OAuthConnectionStore()
        if status == "pending":
            await store.create_pending(
                account_id=account_id,
                provider="anthropic",
                label=label,
                connection_id=uuid4(),
            )
        else:
            connection = await store.create_api_key(
                account_id=account_id,
                provider="anthropic",
                label=label,
                connection_id=uuid4(),
            )
            if status == "error":
                await store.mark_error(connection, "synthetic")
        return await store.label_exists(account_id, "anthropic", label)

    assert authenticated_client.portal.call(scenario) is True


def test_label_exists_is_account_and_provider_scoped(authenticated_client) -> None:
    account_id = authenticated_client.get("/v1/auth/me").json()["id"]

    async def scenario() -> tuple[bool, bool]:
        store = OAuthConnectionStore()
        await store.create_pending(
            account_id=account_id,
            provider="anthropic",
            label="scoped",
            connection_id=uuid4(),
        )
        return (
            await store.label_exists(account_id, "gemini-cli", "scoped"),
            await store.label_exists(uuid4(), "anthropic", "scoped"),
        )

    assert authenticated_client.portal.call(scenario) == (False, False)


@pytest.mark.parametrize("status", ["expired", "revoked"])
def test_label_exists_includes_terminal_statuses(authenticated_client, status: str) -> None:
    account_id = authenticated_client.get("/v1/auth/me").json()["id"]

    async def scenario() -> bool:
        store = OAuthConnectionStore()
        connection = await store.create_api_key(
            account_id=account_id,
            provider="anthropic",
            label=f"terminal-{status}",
            connection_id=uuid4(),
        )
        connection.status = status
        await connection.save(update_fields=["status"])
        return await store.label_exists(account_id, "anthropic", f"terminal-{status}")

    assert authenticated_client.portal.call(scenario) is True
