from __future__ import annotations

import base64
import binascii
import logging
import os

from pydantic import SecretStr
from tortoise.exceptions import IntegrityError

from .models import SecretMasterKey

logger = logging.getLogger(__name__)

_PROVIDER = "local"
_VERSION = "v1"


def _decode_key(b64: str) -> bytes:
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RuntimeError("aigateway secret master key must be valid base64") from exc
    if len(raw) != 32:
        raise RuntimeError("aigateway secret master key must decode to exactly 32 bytes")
    return raw


async def get_or_create_master_key(env_key: SecretStr | None = None) -> bytes:
    """Resolve the 32-byte AES-256 master key for the local provider.

    Precedence: env (``AIGATEWAY_SECRET_KEY``) > persisted sibling-table row >
    auto-generate + persist.

    Auto-generation is a single-worker LOCAL convenience. Multi-worker / hosted
    deployments MUST set ``AIGATEWAY_SECRET_KEY`` so every worker shares one key
    (otherwise each worker generates its own and they cannot decrypt each other's
    rows). The key is stored in its own ``secret_master_keys`` table, never in
    ``credential_blobs`` — that table is what the key encrypts, so storing the
    key there would be circular.
    """
    if env_key is not None:
        return _decode_key(env_key.get_secret_value())

    existing = await SecretMasterKey.filter(provider=_PROVIDER, version=_VERSION).first()
    if existing is not None:
        return _decode_key(existing.key_material)

    raw = os.urandom(32)
    try:
        await SecretMasterKey.create(
            provider=_PROVIDER,
            version=_VERSION,
            key_material=base64.b64encode(raw).decode(),
        )
    except IntegrityError:
        # Concurrent first boot raced us to the single row — re-read the winner.
        existing = await SecretMasterKey.get(provider=_PROVIDER, version=_VERSION)
        return _decode_key(existing.key_material)
    logger.warning(
        "Generated and persisted aigateway secret master key (local provider). "
        "Multi-worker / hosted deployments MUST set AIGATEWAY_SECRET_KEY."
    )
    return raw
