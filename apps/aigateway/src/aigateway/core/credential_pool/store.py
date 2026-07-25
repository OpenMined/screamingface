from __future__ import annotations

from uuid import UUID

from tortoise.exceptions import DoesNotExist

from .models import GlobalCredentialPool

DEFAULT_CREDENTIAL_ACCOUNT = "default"
DEFAULT_POOL_LABEL = "default"


def global_pool_credential_key_for(pool_id: str | UUID) -> str:
    return f"pool:{pool_id}"


def global_pool_credential_locator_for(provider: str, pool_id: str | UUID) -> dict[str, str]:
    return {
        "service": f"aigateway:{provider}:{global_pool_credential_key_for(pool_id)}",
        "account": DEFAULT_CREDENTIAL_ACCOUNT,
    }


class GlobalCredentialPoolStore:
    async def list(self) -> list[GlobalCredentialPool]:
        return await GlobalCredentialPool.all().order_by("provider", "label")

    async def get(self, pool_id: str | UUID) -> GlobalCredentialPool | None:
        try:
            return await GlobalCredentialPool.get(id=pool_id)
        except DoesNotExist:
            return None

    async def get_active_for_provider(
        self, provider: str, *, label: str = DEFAULT_POOL_LABEL
    ) -> GlobalCredentialPool | None:
        return await GlobalCredentialPool.filter(
            provider=provider, label=label, is_active=True
        ).first()

    async def create(
        self,
        *,
        provider: str,
        auth_type: str,
        created_by_id: str | UUID,
        label: str = DEFAULT_POOL_LABEL,
    ) -> GlobalCredentialPool:
        return await GlobalCredentialPool.create(
            provider=provider,
            auth_type=auth_type,
            label=label,
            created_by_id=created_by_id,
        )

    async def set_active(
        self, pool: GlobalCredentialPool, *, is_active: bool
    ) -> GlobalCredentialPool:
        pool.is_active = is_active
        await pool.save(update_fields=["is_active", "updated_at"])
        return pool

    async def delete(self, pool: GlobalCredentialPool) -> None:
        await pool.delete()
