from __future__ import annotations

from pydantic import SecretStr
from tortoise.exceptions import IntegrityError

from .models import Account
from .passwords import hash_password

_MISSING_ADMIN_PASSWORD_MESSAGE = (
    "AIGATEWAY_ADMIN_PASSWORD must be set before creating the initial admin account; "
    "no bootstrap password was generated or logged. Set AIGATEWAY_ADMIN_PASSWORD and "
    "restart before first boot, or reset the admin account in the database."
)


async def ensure_admin_account(env_password: SecretStr | None) -> Account:
    existing = await Account.get_or_none(username="admin")
    if existing is not None:
        return existing
    if env_password is None:
        raise RuntimeError(_MISSING_ADMIN_PASSWORD_MESSAGE)

    password_hash = await hash_password(env_password)
    try:
        admin = await Account.create(username="admin", password_hash=password_hash)
    except IntegrityError:
        return await Account.get(username="admin")
    return admin
