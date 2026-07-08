from __future__ import annotations

from abc import ABC, abstractmethod


class SecretStoreError(Exception):
    """Base class for secret-store failures."""


class SecretDecryptionError(SecretStoreError):
    """Raised when ciphertext fails authentication (tamper / wrong key / corrupt)."""


class SecretStoreMixin(ABC):
    """Port: encode/decode secret values for at-rest storage.

    Despite the ``Mixin`` suffix (kept to match the SF-221 ticket name), this is
    an abstract base class / port — it provides no concrete behavior and is meant
    to be subclassed directly by a provider, not mixed alongside another base.

    Async so network-backed providers (KMS / Vault / HSM) plug in without
    changing call sites. ``encrypt(plaintext)`` must round-trip through the SAME
    provider's ``decrypt``. Cross-provider rotation is bookkept at the storage
    layer via the ``ciphertext_version`` column, never here.

    The default :class:`~aigateway.core.secrets.local.LocalSecretStore` is
    CPU-bound and simply does not ``await`` inside its async methods — that is
    intentional. We deliberately avoid ``asyncio.to_thread`` for local AES-GCM:
    it is microsecond-scale, so offloading would only add overhead.
    """

    @property
    @abstractmethod
    def version(self) -> str:
        """The version tag this provider stamps (e.g. ``"v1"``, ``"kms-v1"``)."""

    @abstractmethod
    async def encrypt(self, plaintext: str) -> str:
        """Return a versioned, self-describing ciphertext string.

        The payload format is owned by the provider; the local provider uses
        ``"v1:<nonce-b64>:<ciphertext-b64>"``. Every provider must prefix its
        payload with ``f"{version}:"`` so the storage layer can validate the
        persisted ``ciphertext_version`` before provider-specific decrypt logic.
        """

    @abstractmethod
    async def decrypt(self, ciphertext: str) -> str:
        """Reverse :meth:`encrypt`.

        Raise :class:`SecretDecryptionError` on tamper / wrong key — never return
        partial or garbage plaintext.
        """
