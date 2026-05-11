from __future__ import annotations

import asyncio
from collections.abc import Callable, Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tortoise import Tortoise

from aigateway.core.credential_store import CredentialStore
from aigateway.db import build_tortoise_config


class FakeKeychain(CredentialStore):
    def __init__(self) -> None:
        self._data: dict[tuple[str, str], str] = {}

    def read(self, service: str, account: str) -> str | None:
        return self._data.get((service, account))

    def write(self, service: str, account: str, value: str) -> None:
        self._data[(service, account)] = value

    def delete(self, service: str, account: str) -> None:
        self._data.pop((service, account), None)


@pytest.fixture
def fake_keychain() -> FakeKeychain:
    return FakeKeychain()


@pytest.fixture(autouse=True)
def _fast_bcrypt(monkeypatch):
    from aigateway.core.auth import passwords

    monkeypatch.setattr(passwords, "_BCRYPT_ROUNDS", 4)
    passwords._dummy_hash = None
    yield
    passwords._dummy_hash = None


def _prepare_sqlite_db(database_url: str) -> None:
    async def _prepare() -> None:
        await Tortoise.close_connections()
        await Tortoise.init(
            config=build_tortoise_config(database_url), _enable_global_fallback=True
        )
        await Tortoise.generate_schemas()
        await Tortoise.close_connections()

    asyncio.run(_prepare())


@pytest.fixture
def patch_credential_factories(fake_keychain, monkeypatch) -> FakeKeychain:
    from aigateway import main as main_module
    from aigateway.core import credential_store as cs_module
    from aigateway.core import profile_index as pi_module
    from aigateway.plugins.anthropic_provider import auth as auth_module
    from aigateway.plugins.anthropic_provider import bootstrap as bs_module

    monkeypatch.setattr(cs_module, "get_credential_store", lambda: fake_keychain)
    monkeypatch.setattr(pi_module, "get_credential_store", lambda: fake_keychain)
    monkeypatch.setattr(bs_module, "get_credential_store", lambda: fake_keychain)
    monkeypatch.setattr(auth_module, "get_credential_store", lambda: fake_keychain)
    monkeypatch.setattr(main_module, "get_credential_store", lambda: fake_keychain)
    return fake_keychain


@pytest.fixture
def client(
    tmp_path: Path,
    monkeypatch,
    patch_credential_factories,
) -> Generator[TestClient, None, None]:
    db_path = tmp_path / "aigateway.sqlite3"
    database_url = f"sqlite://{db_path}"
    monkeypatch.setenv("AIGATEWAY_DATABASE_URL", database_url)
    monkeypatch.setenv("AIGATEWAY_ADMIN_PASSWORD", "test-admin-password")
    monkeypatch.setenv("AIGATEWAY_JWT_SECRET", "x" * 32)
    monkeypatch.setenv("AIGATEWAY_PROVISIONING_TOKEN", "p" * 32)
    _prepare_sqlite_db(database_url)

    from aigateway.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture
def authenticated_client(client: TestClient) -> TestClient:
    response = client.post(
        "/v1/auth/login",
        json={"username": "admin", "password": "test-admin-password"},
    )
    assert response.status_code == 200, response.text
    client.headers.update({"Authorization": f"Bearer {response.json()['token']}"})
    return client


@pytest.fixture
def provisioned_user_factory(client: TestClient) -> Callable[[str, str], dict]:
    def _create(username: str, password: str = "test-user-password") -> dict:
        response = client.post(
            "/v1/accounts",
            headers={"X-Aigw-Provisioning-Token": "p" * 32},
            json={"username": username, "password": password},
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _create
