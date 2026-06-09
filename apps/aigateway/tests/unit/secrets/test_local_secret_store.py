from __future__ import annotations

import os

import pytest

from aigateway.core.secrets.local import LocalSecretStore
from aigateway.core.secrets.mixin import SecretDecryptionError

_KEY = bytes(range(32))
_OTHER_KEY = bytes(range(32, 64))


@pytest.fixture
def store() -> LocalSecretStore:
    return LocalSecretStore(_KEY)


def test_rejects_non_32_byte_key() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        LocalSecretStore(b"too-short")


def test_version_is_v1(store: LocalSecretStore) -> None:
    assert store.version == "v1"


@pytest.mark.asyncio
async def test_round_trip(store: LocalSecretStore) -> None:
    plaintext = '{"access_token":"abc","refresh_token":"def"}'
    ciphertext = await store.encrypt(plaintext)
    assert ciphertext.startswith("v1:")
    assert plaintext not in ciphertext
    assert await store.decrypt(ciphertext) == plaintext


@pytest.mark.asyncio
async def test_round_trip_unicode(store: LocalSecretStore) -> None:
    plaintext = "héllo-世界-🔐"
    assert await store.decrypt(await store.encrypt(plaintext)) == plaintext


@pytest.mark.asyncio
async def test_ciphertext_format_three_parts(store: LocalSecretStore) -> None:
    parts = (await store.encrypt("x")).split(":")
    assert len(parts) == 3
    assert parts[0] == "v1"


@pytest.mark.asyncio
async def test_fresh_nonce_per_call(store: LocalSecretStore) -> None:
    # Same plaintext + key must produce different ciphertext (unique nonce).
    a = await store.encrypt("same")
    b = await store.encrypt("same")
    assert a != b
    assert await store.decrypt(a) == await store.decrypt(b) == "same"


@pytest.mark.asyncio
async def test_legacy_plaintext_passthrough(store: LocalSecretStore) -> None:
    # Pre-encryption rows hold plaintext JSON; decrypt returns them unchanged.
    legacy = '{"plain":"json","not":"encrypted"}'
    assert await store.decrypt(legacy) == legacy


@pytest.mark.asyncio
async def test_tamper_detected(store: LocalSecretStore) -> None:
    ciphertext = await store.encrypt("secret")
    version, nonce_b64, payload_b64 = ciphertext.split(":")
    # Flip the last base64 char of the payload.
    flipped = payload_b64[:-1] + ("A" if payload_b64[-1] != "A" else "B")
    tampered = f"{version}:{nonce_b64}:{flipped}"
    with pytest.raises(SecretDecryptionError):
        await store.decrypt(tampered)


@pytest.mark.asyncio
async def test_wrong_key_rejected(store: LocalSecretStore) -> None:
    ciphertext = await store.encrypt("secret")
    other = LocalSecretStore(_OTHER_KEY)
    with pytest.raises(SecretDecryptionError):
        await other.decrypt(ciphertext)


@pytest.mark.asyncio
async def test_malformed_v1_envelope_rejected(store: LocalSecretStore) -> None:
    # Has the v1: prefix but is not a valid envelope.
    with pytest.raises(SecretDecryptionError):
        await store.decrypt("v1:not-base64:also-not")


@pytest.mark.asyncio
async def test_random_key_round_trip() -> None:
    store = LocalSecretStore(os.urandom(32))
    assert await store.decrypt(await store.encrypt("payload")) == "payload"


@pytest.mark.asyncio
async def test_foreign_versioned_envelope_rejected(store: LocalSecretStore) -> None:
    # A versioned envelope from another provider/version (e.g. a future kms-v1:)
    # must fail loudly, not be returned verbatim as plaintext (SF-221 review #6).
    for foreign in ("kms-v1:opaque", "v2:future-format", "vault-v1:blob"):
        with pytest.raises(SecretDecryptionError):
            await store.decrypt(foreign)


@pytest.mark.asyncio
async def test_non_envelope_legacy_values_passthrough(store: LocalSecretStore) -> None:
    # Genuine legacy plaintext that is not an SF versioned envelope still passes
    # through unchanged — including colon-bearing values like URLs.
    for legacy in ("https://example.test/callback", "bearer-token-abc", '{"k": 1}'):
        assert await store.decrypt(legacy) == legacy
