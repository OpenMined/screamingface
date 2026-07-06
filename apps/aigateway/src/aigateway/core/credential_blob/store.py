from __future__ import annotations

from typing import Protocol

from tortoise.exceptions import DoesNotExist, IntegrityError

from ..secrets.factory import get_active_secret_store
from ..secrets.mixin import SecretDecryptionError, SecretStoreMixin
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
        store = self._secrets()
        try:
            _validate_ciphertext_version(blob.value, blob.ciphertext_version, store.version)
            return await store.decrypt(blob.value)
        except SecretDecryptionError as exc:
            raise _credential_decryption_error(service, account, blob.ciphertext_version) from exc

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


def _validate_ciphertext_version(
    value: str, ciphertext_version: str | None, active_version: str
) -> None:
    if ciphertext_version is None:
        return
    if ciphertext_version != active_version:
        raise SecretDecryptionError(
            "credential blob was encrypted with a different secret provider version"
        )
    if not value.startswith(f"{ciphertext_version}:"):
        raise SecretDecryptionError("versioned credential blob is missing its ciphertext prefix")


def _credential_decryption_error(
    service: str,
    account: str,
    ciphertext_version: str | None,
) -> SecretDecryptionError:
    version = ciphertext_version or "legacy/plaintext"
    return SecretDecryptionError(
        "failed to decrypt credential blob "
        f"service={service!r} account={account!r} ciphertext_version={version!r}; "
        "verify AIGATEWAY_SECRET_KEY and AIGATEWAY_SECRET_PROVIDER, then restore "
        "the matching secret key or re-authenticate this connection"
    )
