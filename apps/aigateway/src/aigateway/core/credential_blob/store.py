from __future__ import annotations

import asyncio
import random
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from tortoise.exceptions import DoesNotExist, IntegrityError

from ..secrets.factory import get_active_secret_store
from ..secrets.mixin import SecretDecryptionError, SecretStoreMixin
from .model import CredentialBlob

_MUTATE_MAX_ATTEMPTS = 8
_MUTATE_BACKOFF_BASE_SECONDS = 0.001
_MUTATE_BACKOFF_MAX_SECONDS = 0.02
_MUTATE_JITTER_SECONDS = 0.002


class CredentialBlobMutationConflict(RuntimeError):
    """Raised when optimistic credential-blob mutation exhausts its retry budget."""


class CredentialBlobStore(Protocol):
    async def read(self, service: str, account: str) -> str | None: ...

    async def write(self, service: str, account: str, value: str) -> None: ...

    async def delete(self, service: str, account: str) -> None: ...

    async def mutate(
        self,
        service: str,
        account: str,
        mutator: Callable[[str | None], str | None],
    ) -> None: ...


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

    async def mutate(
        self,
        service: str,
        account: str,
        mutator: Callable[[str | None], str | None],
    ) -> None:
        store = self._secrets()
        for attempt in range(_MUTATE_MAX_ATTEMPTS):
            blob = await CredentialBlob.filter(service=service, account=account).first()
            current_ciphertext = blob.value if blob is not None else None
            if blob is None:
                current_value = None
            else:
                try:
                    _validate_ciphertext_version(blob.value, blob.ciphertext_version, store.version)
                    current_value = await store.decrypt(blob.value)
                except SecretDecryptionError as exc:
                    raise _credential_decryption_error(
                        service, account, blob.ciphertext_version
                    ) from exc
            next_value = mutator(current_value)

            if blob is None:
                if next_value is None:
                    return
                next_ciphertext = await store.encrypt(next_value)
                try:
                    await CredentialBlob.create(
                        service=service,
                        account=account,
                        value=next_ciphertext,
                        ciphertext_version=store.version,
                    )
                    return
                except IntegrityError:
                    if attempt + 1 < _MUTATE_MAX_ATTEMPTS:
                        await _sleep_before_mutation_retry(attempt)
                    continue

            # INVARIANT: compare against the ciphertext read above. Encryption uses a
            # fresh nonce, so comparing newly encrypted plaintext would always miss.
            if next_value is None:
                deleted = await CredentialBlob.filter(
                    id=blob.id,
                    service=service,
                    account=account,
                    value=current_ciphertext,
                ).delete()
                if deleted == 1:
                    return
                if attempt + 1 < _MUTATE_MAX_ATTEMPTS:
                    await _sleep_before_mutation_retry(attempt)
                continue

            next_ciphertext = await store.encrypt(next_value)
            updated = await CredentialBlob.filter(
                id=blob.id,
                service=service,
                account=account,
                value=current_ciphertext,
            ).update(
                value=next_ciphertext,
                ciphertext_version=store.version,
                updated_at=datetime.now(UTC),
            )
            if updated == 1:
                return
            if attempt + 1 < _MUTATE_MAX_ATTEMPTS:
                await _sleep_before_mutation_retry(attempt)

        raise CredentialBlobMutationConflict(
            f"Credential blob mutation conflicted after {_MUTATE_MAX_ATTEMPTS} attempts"
        )


async def _sleep_before_mutation_retry(attempt: int) -> None:
    delay = min(
        _MUTATE_BACKOFF_BASE_SECONDS * 2**attempt,
        _MUTATE_BACKOFF_MAX_SECONDS,
    )
    delay += random.uniform(0.0, _MUTATE_JITTER_SECONDS)
    await asyncio.sleep(delay)


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
        "the matching secret key. If the key is unrecoverable, delete this credential "
        "so it can be regenerated (internal secrets) or re-authenticated (user connections)"
    )
