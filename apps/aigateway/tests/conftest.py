from __future__ import annotations

import asyncio
import sqlite3
import uuid
from collections.abc import Callable, Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tortoise import Tortoise

from aigateway.db import build_tortoise_config


class _AsyncCredentialBlobProbe:
    def __init__(self, probe: CredentialBlobProbe) -> None:
        self._probe = probe

    async def read(self, service: str, account: str) -> str | None:
        return self._probe.read(service, account)

    async def write(self, service: str, account: str, value: str) -> None:
        self._probe.write(service, account, value)

    async def delete(self, service: str, account: str) -> None:
        self._probe.delete(service, account)


class CredentialBlobProbe:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self.store = _AsyncCredentialBlobProbe(self)

    @property
    def db_path(self) -> Path:
        return self._db_path

    def read(self, service: str, account: str) -> str | None:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "select value from credential_blobs where service = ? and account = ?",
                (service, account),
            ).fetchone()
        return row[0] if row is not None else None

    def write(self, service: str, account: str, value: str) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """
                insert into credential_blobs (id, service, account, value, created_at, updated_at)
                values (?, ?, ?, ?, datetime('now'), datetime('now'))
                on conflict(service, account) do update set
                    value = excluded.value,
                    updated_at = datetime('now')
                """,
                (str(uuid.uuid4()), service, account, value),
            )

    def delete(self, service: str, account: str) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "delete from credential_blobs where service = ? and account = ?",
                (service, account),
            )


@pytest.fixture
def credential_blobs(tmp_path: Path, monkeypatch) -> CredentialBlobProbe:
    db_path = tmp_path / "aigateway.sqlite3"
    database_url = f"sqlite://{db_path}"
    monkeypatch.setenv("AIGATEWAY_DATABASE_URL", database_url)
    _prepare_sqlite_db(database_url)
    return CredentialBlobProbe(db_path)


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
def client(
    monkeypatch,
    credential_blobs,
) -> Generator[TestClient, None, None]:
    database_url = f"sqlite://{credential_blobs.db_path}"
    monkeypatch.setenv("AIGATEWAY_DATABASE_URL", database_url)
    monkeypatch.setenv("AIGATEWAY_ADMIN_PASSWORD", "test-admin-password")
    monkeypatch.setenv("AIGATEWAY_JWT_SECRET", "x" * 32)
    monkeypatch.setenv("AIGATEWAY_PROVISIONING_TOKEN", "p" * 32)
    _prepare_sqlite_db(database_url)

    from aigateway.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
    asyncio.run(Tortoise.close_connections())


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
