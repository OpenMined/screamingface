from __future__ import annotations

from .mixin import SecretStoreMixin


class KMSSecretStore(SecretStoreMixin):
    """Extension shape for cloud KMS / Vault providers (NOT implemented in SF-221).

    A real implementation performs network I/O in async ``encrypt`` / ``decrypt``
    (AWS KMS ``Encrypt``/``Decrypt``, GCP KMS ``cryptoKeyVersion``, Vault Transit)
    and stamps ``"kms-v1:<provider-payload>"`` so the storage layer can route
    decryption to the right provider during rotation.

    This stub ships so the factory's provider dispatch is exercised end-to-end and
    the extension contract lives in code, not just prose. Implementation is
    deferred to a follow-up ticket.
    """

    @property
    def version(self) -> str:
        return "kms-v1"

    async def encrypt(self, plaintext: str) -> str:
        raise NotImplementedError("KMSSecretStore is a stub — see SF-221 non-goals")

    async def decrypt(self, ciphertext: str) -> str:
        raise NotImplementedError("KMSSecretStore is a stub — see SF-221 non-goals")
