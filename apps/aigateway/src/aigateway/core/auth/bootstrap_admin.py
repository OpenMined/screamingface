from __future__ import annotations

import logging
import secrets
import string

from pydantic import SecretStr
from tortoise.exceptions import IntegrityError

from .models import Account
from .passwords import hash_password

logger = logging.getLogger(__name__)

_PASSWORD_ALPHABET = string.ascii_letters + string.digits


def _generate_password(length: int = 24) -> str:
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


async def ensure_admin_account(env_password: SecretStr | None) -> None:
    if await Account.get_or_none(username="admin") is not None:
        return

    generated_password = None if env_password is not None else _generate_password()
    password = env_password if env_password is not None else SecretStr(generated_password or "")
    password_hash = await hash_password(password)
    try:
        await Account.create(username="admin", password_hash=password_hash)
    except IntegrityError:
        return

    if generated_password is not None:
        logger.warning("Bootstrap admin password: %s", generated_password)
