from __future__ import annotations

import pytest

from aigateway.core.secrets.local import LocalSecretStore
from aigateway.core.secrets.mixin import SecretDecryptionError
from tests.conftest import TEST_SECRET_KEY, _test_decrypt, _test_encrypt


@pytest.mark.asyncio
async def test_probe_double_is_format_compatible_with_local_secret_store() -> None:
    # The CredentialBlobProbe hand-implements the v1 envelope as a test double.
    # Pin it to the real LocalSecretStore so a future format change to either side
    # cannot silently diverge (which would let the "no plaintext leak" assertions
    # pass against a stale format).
    store = LocalSecretStore(TEST_SECRET_KEY)

    # Real store decrypts the probe's ciphertext.
    assert await store.decrypt(_test_encrypt("payload-A")) == "payload-A"
    # Probe decrypts the real store's ciphertext.
    assert _test_decrypt(await store.encrypt("payload-B")) == "payload-B"


@pytest.mark.asyncio
async def test_probe_double_matches_decrypt_reject_and_passthrough_branches() -> None:
    # Pin the double to the real store on the NON-happy-path branches too, so the
    # foreign-envelope reject semantics (SF-221 review #6) cannot silently diverge.
    store = LocalSecretStore(TEST_SECRET_KEY)

    for foreign in ("kms-v1:opaque", "aws-kms-v1:opaque", "v2:future"):
        with pytest.raises(SecretDecryptionError):
            await store.decrypt(foreign)
        with pytest.raises(SecretDecryptionError):
            _test_decrypt(foreign)

    for legacy in ('{"legacy": true}', "https://example.test/callback"):
        assert await store.decrypt(legacy) == legacy
        assert _test_decrypt(legacy) == legacy
