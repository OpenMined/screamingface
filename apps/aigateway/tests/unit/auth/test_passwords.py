from __future__ import annotations

import asyncio
import threading
from unittest.mock import patch

import pytest

from aigateway.core.auth.passwords import hash_password, verify_password


@pytest.mark.asyncio
async def test_hash_and_verify_password() -> None:
    hashed = await hash_password("password123")
    assert hashed.startswith("$2")
    assert await verify_password("password123", hashed)
    assert not await verify_password("wrongpass", hashed)


@pytest.mark.asyncio
async def test_malformed_hash_returns_false() -> None:
    assert not await verify_password("password123", "not-a-bcrypt-hash")


@pytest.mark.asyncio
async def test_password_over_72_bytes_rejected() -> None:
    with pytest.raises(ValueError, match="8-72 UTF-8 bytes"):
        await hash_password("a" * 73)


@pytest.mark.asyncio
async def test_bcrypt_runs_in_threadpool() -> None:
    started = threading.Event()
    release = threading.Event()

    def _thread_id(password: str) -> str:
        started.set()
        release.wait(timeout=1)
        return f"hashed:{password}"

    with patch("aigateway.core.auth.passwords._hash_password_sync", _thread_id):
        task = asyncio.create_task(hash_password("password123"))
        for _ in range(100):
            if started.is_set():
                break
            await asyncio.sleep(0.01)
        assert started.is_set()
        assert not task.done()
        release.set()
        assert await task == "hashed:password123"
