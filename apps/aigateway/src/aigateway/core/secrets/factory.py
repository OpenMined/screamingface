from __future__ import annotations

from pydantic import SecretStr

from .local import LocalSecretStore
from .master_key import get_or_create_master_key
from .mixin import SecretStoreMixin

_active: SecretStoreMixin | None = None


async def build_secret_store(provider: str, env_key: SecretStr | None = None) -> SecretStoreMixin:
    """Dispatch on the configured provider and resolve its key material.

    Async because the ``local`` provider may touch the DB (auto-generate +
    persist the master key). Run once during the app lifespan, then install the
    result via :func:`set_active_secret_store`.
    """
    normalized = provider.lower()
    if normalized == "local":
        key = await get_or_create_master_key(env_key)
        return LocalSecretStore(key)
    if normalized == "kms":
        from .kms import KMSSecretStore

        # Constructs fine; encrypt/decrypt raise NotImplementedError. This proves
        # the dispatch wiring without a real KMS backend.
        return KMSSecretStore()
    raise RuntimeError(f"Unknown AIGATEWAY_SECRET_PROVIDER={provider!r}")


def set_active_secret_store(store: SecretStoreMixin | None) -> None:
    """Install (or clear, with ``None``) the process-wide active secret store."""
    global _active
    _active = store


def get_active_secret_store() -> SecretStoreMixin:
    """Return the active secret store installed during the app lifespan.

    Raises if called before :func:`build_secret_store` + :func:`set_active_secret_store`
    have run (e.g. a credential read/write before the lifespan initialized it).
    """
    if _active is None:
        raise RuntimeError(
            "secret store not initialized — build_secret_store() must run in the app "
            "lifespan before any credential read/write"
        )
    return _active
