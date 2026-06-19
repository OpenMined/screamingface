from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from tortoise.exceptions import DoesNotExist

from aigateway.core.auth.middleware import ANONYMOUS_ACCOUNT_ID
from aigateway.core.auth.models import Account

from .identity import AccountIdentity
from .models import OAuthConnection
from .schemas import OAuthConnectionResponse

DEFAULT_CREDENTIAL_ACCOUNT = "default"


def credential_key_for(account_id: str | UUID, connection_id: str | UUID) -> str:
    return f"{account_id}:{connection_id}"


def credential_locator_for(
    provider: str,
    account_id: str | UUID,
    connection_id: str | UUID,
) -> dict[str, str]:
    return {
        "service": f"aigateway:{provider}:{credential_key_for(account_id, connection_id)}",
        "account": DEFAULT_CREDENTIAL_ACCOUNT,
    }


class OAuthConnectionStore:
    async def list(
        self,
        account_id: str | UUID,
        *,
        provider: str | None = None,
        status: str | None = None,
    ) -> list[OAuthConnection]:
        query = OAuthConnection.filter(account_id=account_id)
        if provider is not None:
            query = query.filter(provider=provider)
        if status is not None:
            query = query.filter(status=status)
        else:
            query = query.exclude(status="revoked")
        return await query.order_by("provider", "label", "created_at")

    async def get(
        self, account_id: str | UUID, connection_id: str | UUID
    ) -> OAuthConnection | None:
        try:
            return await OAuthConnection.get(id=connection_id, account_id=account_id)
        except DoesNotExist:
            return None

    async def create_pending(
        self,
        *,
        account_id: str | UUID,
        provider: str,
        label: str,
        connection_id: UUID,
        credential_provider: str | None = None,
    ) -> OAuthConnection:
        await _ensure_anonymous_account(account_id)
        return await OAuthConnection.create(
            id=connection_id,
            account_id=account_id,
            provider=provider,
            label=label,
            status="pending",
            credential_locator=credential_locator_for(
                credential_provider or provider,
                account_id,
                connection_id,
            ),
        )

    async def create_api_key(
        self,
        *,
        account_id: str | UUID,
        provider: str,
        label: str,
        connection_id: UUID,
        credential_provider: str | None = None,
    ) -> OAuthConnection:
        """Create an api-key connection in the active state directly.

        Unlike create_pending (OAuth: pending -> active on callback), an
        api-key connection has no browser round-trip, so it is authenticated
        the moment its key is stored. status has no DB default, so it is set
        explicitly here; auth_type is set to "api_key" (the column defaults to
        "oauth"). The credential_locator points at the same blob slot the chat
        path reads via credential_key_for(account_id, connection_id)."""
        await _ensure_anonymous_account(account_id)
        return await OAuthConnection.create(
            id=connection_id,
            account_id=account_id,
            provider=provider,
            label=label,
            status="active",
            auth_type="api_key",
            credential_locator=credential_locator_for(
                credential_provider or provider,
                account_id,
                connection_id,
            ),
        )

    async def find_by_identity(
        self,
        account_id: str | UUID,
        provider: str,
        identity_sub: str | None,
    ) -> OAuthConnection | None:
        if not identity_sub:
            return None
        return await OAuthConnection.filter(
            account_id=account_id,
            provider=provider,
            identity_sub=identity_sub,
            status="active",
        ).first()

    async def find_by_label(
        self,
        account_id: str | UUID,
        provider: str,
        label: str,
    ) -> OAuthConnection | None:
        return await OAuthConnection.filter(
            account_id=account_id,
            provider=provider,
            label=label,
            status="active",
        ).first()

    async def complete(
        self,
        connection: OAuthConnection,
        *,
        label: str,
        identity: AccountIdentity | None,
    ) -> OAuthConnection:
        connection.label = label
        connection.status = "active"
        connection.error_message = None
        connection.last_refreshed_at = datetime.now(UTC)
        if identity is not None:
            connection.identity_sub = identity.sub
            connection.identity_email = identity.email
            connection.identity_name = identity.name
            connection.identity_raw = identity.raw
        await connection.save()
        return connection

    async def mark_error(self, connection: OAuthConnection, message: str) -> OAuthConnection:
        connection.status = "error"
        connection.error_message = message
        fields = ["status", "error_message"]
        # OAuth connections are superseded by a fresh re-auth, so the old row's
        # label/identity are cleared. An api-key connection is re-keyed IN PLACE
        # (Replace key), so its label and identity must survive the error state
        # to stay recoverable (SF-291 review RF2-1).
        if connection.auth_type != "api_key":
            connection.label = f"error:{connection.id}"
            connection.identity_sub = None
            fields += ["label", "identity_sub"]
        await connection.save(update_fields=fields)
        return connection

    async def reactivate(self, connection: OAuthConnection) -> OAuthConnection:
        """Return an errored connection to active after its credential is
        replaced (SF-291 review RF2-1)."""
        connection.status = "active"
        connection.error_message = None
        connection.last_refreshed_at = datetime.now(UTC)
        await connection.save(update_fields=["status", "error_message", "last_refreshed_at"])
        return connection

    async def mark_revoked(
        self,
        connection: OAuthConnection,
        message: str | None = None,
    ) -> OAuthConnection:
        connection.label = f"revoked:{connection.id}"
        connection.identity_sub = None
        connection.status = "revoked"
        connection.error_message = message
        await connection.save(update_fields=["label", "identity_sub", "status", "error_message"])
        return connection

    async def delete_or_supersede_pending(
        self,
        connection: OAuthConnection,
        duplicate: OAuthConnection,
    ) -> OAuthConnection:
        return await self.mark_revoked(connection, f"duplicate:{duplicate.id}")

    async def touch_last_used(self, connection: OAuthConnection) -> OAuthConnection:
        connection.last_used_at = datetime.now(UTC)
        await connection.save(update_fields=["last_used_at"])
        return connection

    async def touch_last_refreshed(self, connection: OAuthConnection) -> OAuthConnection:
        connection.last_refreshed_at = datetime.now(UTC)
        await connection.save(update_fields=["last_refreshed_at"])
        return connection


def response_from_connection(
    connection: OAuthConnection,
    *,
    is_duplicate: bool = False,
) -> OAuthConnectionResponse:
    account = None
    if connection.identity_sub or connection.identity_email or connection.identity_name:
        account = AccountIdentity(
            sub=connection.identity_sub,
            email=connection.identity_email,
            name=connection.identity_name,
            raw=connection.identity_raw or {},
        )
    return OAuthConnectionResponse(
        id=connection.id,
        account_id=connection.account_id,
        provider=connection.provider,
        label=connection.label,
        status=connection.status,
        auth_type=connection.auth_type,
        account=account,
        credential_locator=connection.credential_locator,
        created_at=connection.created_at,
        last_used_at=connection.last_used_at,
        last_refreshed_at=connection.last_refreshed_at,
        error_message=connection.error_message,
        is_duplicate=is_duplicate,
    )


async def _ensure_anonymous_account(account_id: str | UUID) -> None:
    if str(account_id) != str(ANONYMOUS_ACCOUNT_ID):
        return
    await Account.get_or_create(
        id=ANONYMOUS_ACCOUNT_ID,
        defaults={
            "username": "anonymous",
            "password_hash": "",
            "display_name": "Anonymous",
            "is_active": True,
        },
    )
