from __future__ import annotations

from typing import Protocol

from tortoise.exceptions import DoesNotExist, IntegrityError

from ..secrets.factory import get_active_secret_store
from ..secrets.mixin import SecretStoreMixin
from .model import CredentialBlob


class CredentialBlobStore(Protocol):
    async def read(self, service: str, account: str) -> str | None: ...

    async def write(self, service: str, account: str, value: str) -> None: ...

    async def delete(self, service: str, account: str) -> None: ...


class ORMStore:
    """Tortoise-backed credential storage with encryption-at-rest (SF-221).

    The row value is encrypted via a :class:`SecretStoreMixin` before write and
    decrypted on read. ``secret_store`` is an optional injected dependency (a
    unit-test seam); when ``None`` the process-wide active store is resolved
    lazily at call time — never in ``__init__`` — so the import-time ``ORMStore()``
    in ``create_app`` is safe before the DB and secret store are initialized.
    """

    def __init__(self, secret_store: SecretStoreMixin | None = None) -> None:
        self._secret_store = secret_store

    def _secrets(self) -> SecretStoreMixin:
        return self._secret_store or get_active_secret_store()

    async def read(self, service: str, account: str) -> str | None:
        blob = await CredentialBlob.filter(service=service, account=account).first()
        if blob is None:
            return None
        return await self._secrets().decrypt(blob.value)

    async def write(self, service: str, account: str, value: str) -> None:
        store = self._secrets()
        ciphertext = await store.encrypt(value)
        version = store.version
        try:
            blob = await CredentialBlob.get(service=service, account=account)
        except DoesNotExist:
            try:
                await CredentialBlob.create(
                    service=service,
                    account=account,
                    value=ciphertext,
                    ciphertext_version=version,
                )
                return
            except IntegrityError:
                blob = await CredentialBlob.get(service=service, account=account)
        blob.value = ciphertext
        blob.ciphertext_version = version
        await blob.save(update_fields=["value", "ciphertext_version", "updated_at"])

    async def delete(self, service: str, account: str) -> None:
        await CredentialBlob.filter(service=service, account=account).delete()
