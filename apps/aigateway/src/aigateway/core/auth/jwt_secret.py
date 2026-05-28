from __future__ import annotations

import logging
import secrets

from pydantic import SecretStr

from ..credential_blob.store import CredentialBlobStore

JWT_SECRET_SERVICE = "aigateway:jwt-secret"
JWT_SECRET_ACCOUNT = "default"

logger = logging.getLogger(__name__)


async def get_or_create_jwt_secret(
    credential_store: CredentialBlobStore,
    env_secret: SecretStr | None = None,
) -> str:
    """Return the gateway JWT secret as a plain string.

    Auto-generation is a local/single-worker convenience only. Multi-process
    deployments must set AIGATEWAY_JWT_SECRET so every worker starts with the
    same secret instead of racing through generated-secret persistence.
    """
    if env_secret is not None:
        return env_secret.get_secret_value()

    existing = await credential_store.read(JWT_SECRET_SERVICE, JWT_SECRET_ACCOUNT)
    if existing:
        if len(existing) < 32:
            raise RuntimeError(
                "Persisted aigateway JWT secret must be at least 32 characters; "
                "delete credential blob aigateway:jwt-secret/default or set AIGATEWAY_JWT_SECRET"
            )
        return existing

    generated = secrets.token_urlsafe(48)
    await credential_store.write(JWT_SECRET_SERVICE, JWT_SECRET_ACCOUNT, generated)
    logger.warning("Generated and persisted aigateway JWT secret")
    return generated
