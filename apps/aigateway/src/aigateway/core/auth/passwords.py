from __future__ import annotations

import threading

import bcrypt
from fastapi.concurrency import run_in_threadpool
from pydantic import SecretStr

_BCRYPT_ROUNDS = 12
_DUMMY_PASSWORD = b"screamingface-dummy-password"
_dummy_hash: bytes | None = None
_dummy_lock = threading.Lock()


def _password_bytes(password: SecretStr | str) -> bytes:
    raw = password.get_secret_value() if isinstance(password, SecretStr) else password
    encoded = raw.encode("utf-8")
    if not 8 <= len(encoded) <= 72:
        raise ValueError("password must be 8-72 UTF-8 bytes")
    return encoded


def _hash_password_sync(password: SecretStr | str) -> str:
    hashed = bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS))
    return hashed.decode("ascii")


def _verify_password_sync(password: SecretStr | str, password_hash: str | bytes) -> bool:
    stored = password_hash.encode("ascii") if isinstance(password_hash, str) else password_hash
    try:
        return bcrypt.checkpw(_password_bytes(password), stored)
    except ValueError:
        return False


def _get_dummy_hash() -> bytes:
    global _dummy_hash
    if _dummy_hash is None:
        with _dummy_lock:
            if _dummy_hash is None:
                _dummy_hash = bcrypt.hashpw(
                    _DUMMY_PASSWORD,
                    bcrypt.gensalt(rounds=_BCRYPT_ROUNDS),
                )
    return _dummy_hash


async def hash_password(password: SecretStr | str) -> str:
    return await run_in_threadpool(_hash_password_sync, password)


async def verify_password(password: SecretStr | str, password_hash: str | bytes) -> bool:
    return await run_in_threadpool(_verify_password_sync, password, password_hash)


async def verify_password_or_dummy(
    password: SecretStr | str, password_hash: str | bytes | None
) -> bool:
    if password_hash is None:
        password_hash = await run_in_threadpool(_get_dummy_hash)
    return await verify_password(password, password_hash)
