from __future__ import annotations

import base64
import os

import pytest
from pydantic import SecretStr

from aigateway.core.secrets.factory import (
    build_secret_store,
    get_active_secret_store,
    set_active_secret_store,
)
from aigateway.core.secrets.kms import KMSSecretStore
from aigateway.core.secrets.local import LocalSecretStore


@pytest.fixture(autouse=True)
def _reset_active():
    set_active_secret_store(None)
    yield
    set_active_secret_store(None)


def test_get_active_before_init_raises() -> None:
    with pytest.raises(RuntimeError, match="not initialized"):
        get_active_secret_store()


def test_set_get_active_round_trip() -> None:
    store = LocalSecretStore(os.urandom(32))
    set_active_secret_store(store)
    assert get_active_secret_store() is store


@pytest.mark.asyncio
async def test_build_local_with_env_key() -> None:
    key = SecretStr(base64.b64encode(os.urandom(32)).decode())
    store = await build_secret_store("local", key)
    assert isinstance(store, LocalSecretStore)
    assert store.version == "v1"


@pytest.mark.asyncio
async def test_build_local_provider_is_case_insensitive() -> None:
    key = SecretStr(base64.b64encode(os.urandom(32)).decode())
    store = await build_secret_store("LOCAL", key)
    assert isinstance(store, LocalSecretStore)


@pytest.mark.asyncio
async def test_build_kms_returns_stub() -> None:
    store = await build_secret_store("kms")
    assert isinstance(store, KMSSecretStore)
    assert store.version == "kms-v1"
    with pytest.raises(NotImplementedError):
        await store.encrypt("x")
    with pytest.raises(NotImplementedError):
        await store.decrypt("kms-v1:x")


@pytest.mark.asyncio
async def test_build_unknown_provider_raises() -> None:
    with pytest.raises(RuntimeError, match="Unknown"):
        await build_secret_store("vault")
