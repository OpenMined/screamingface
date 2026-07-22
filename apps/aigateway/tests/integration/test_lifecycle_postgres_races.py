from __future__ import annotations

import asyncio
import base64
import os
import subprocess
import sys
import threading
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]

from aigateway.config import Settings
from aigateway.core.api_key_validation import (
    ApiKeyValidationResult,
    ApiKeyValidationStage,
    ApiKeyValidationState,
)
from aigateway.core.oauth.store import (
    OAuthConnectionStore,
    credential_locator_for,
)
from aigateway.core.profile_models import credential_name_for
from aigateway.main import create_app
from aigateway.plugins.anthropic_provider.auth import credential_service_for

pytestmark = pytest.mark.needs_postgres

_APP_DIR = Path(__file__).resolve().parents[2]
_API_KEY = "sk-ant-api03-postgres-race-key-1234"


class _ValidValidationService:
    async def validate(self, _plugin, _provider: str, _api_key: str) -> ApiKeyValidationResult:
        return ApiKeyValidationResult(
            ApiKeyValidationState.VALID,
            stage=ApiKeyValidationStage.READINESS,
        )


@pytest.fixture(scope="module")
def postgres_database_url() -> Generator[str, None, None]:
    if os.environ.get("AIGW_TEST_PG") != "1":
        pytest.skip("AIGW_TEST_PG=1 not set")
    with PostgresContainer("postgres:16-alpine", driver=None) as postgres:
        database_url = (
            f"postgres://{postgres.username}:{quote(postgres.password, safe='')}"
            f"@{postgres.get_container_host_ip()}:{postgres.get_exposed_port(5432)}"
            f"/{postgres.dbname}"
        )
        subprocess.run(
            [
                sys.executable,
                "-m",
                "tortoise",
                "-c",
                "aigateway.db.TORTOISE_CONFIG",
                "migrate",
            ],
            cwd=_APP_DIR,
            env={**os.environ, "AIGATEWAY_DATABASE_URL": database_url},
            check=True,
            capture_output=True,
            text=True,
        )
        yield database_url


@pytest.fixture
def pg_client(postgres_database_url: str) -> Generator[TestClient, None, None]:
    settings = Settings(
        database_url=SecretStr(postgres_database_url),
        admin_password=SecretStr("test-admin-password"),
        jwt_secret=SecretStr("x" * 32),
        provisioning_token=SecretStr("p" * 32),
        secret_key=SecretStr(base64.b64encode(b"k" * 32).decode()),
    )
    app = create_app(settings)
    with TestClient(app) as client:
        login = client.post(
            "/v1/auth/login",
            json={"username": "admin", "password": "test-admin-password"},
        )
        assert login.status_code == 200, login.text
        client.headers.update({"Authorization": f"Bearer {login.json()['token']}"})
        app.state.api_key_validation_service = _ValidValidationService()
        yield client


def _token_factory(token: str):
    async def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": token,
                "refresh_token": f"refresh-{token}",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

    return lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(_handler),
        timeout=httpx.Timeout(5.0),
    )


def _app(client: TestClient) -> FastAPI:
    app = client.app
    if not isinstance(app, FastAPI):
        raise AssertionError("TestClient is not running the expected FastAPI app")
    return app


def _read_credential(client: TestClient, service: str, account: str) -> str | None:
    portal = client.portal
    if portal is None:
        raise AssertionError("TestClient portal is not active")
    value = portal.call(_app(client).state.credential_store.read, service, account)
    if value is not None and not isinstance(value, str):
        raise AssertionError("credential store returned a non-string value")
    return value


def _failing_token_factory():
    async def _handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    return lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(_handler),
        timeout=httpx.Timeout(5.0),
    )


def _profile_credential(client: TestClient, account_id: str, name: str) -> str | None:
    service = credential_service_for(credential_name_for(account_id, name))
    return _read_credential(client, service, "default")


def _connection_credential(client: TestClient, account_id: str, connection_id: UUID) -> str | None:
    locator = credential_locator_for("anthropic", account_id, connection_id)
    return _read_credential(client, locator["service"], locator["account"])


def test_postcondition_owner_check_and_cas_are_atomic_on_postgres(
    pg_client: TestClient,
    monkeypatch,
) -> None:
    name = f"ownership-{uuid4()}"
    account_id = pg_client.get("/v1/auth/me").json()["id"]
    _app(pg_client).state.anthropic_http_factory = _token_factory("oauth-A-token")
    start_a = pg_client.post("/v1/auth/anthropic/profiles", json={"name": name})
    index = _app(pg_client).state.profile_index
    authenticate_pending = index.authenticate_pending
    cas_reached = threading.Event()
    release_cas = threading.Event()

    async def _pause_before_cas(profile, **kwargs) -> None:
        cas_reached.set()
        if not await asyncio.to_thread(release_cas.wait, 10):
            raise TimeoutError("profile CAS was not released")
        await authenticate_pending(profile, **kwargs)

    monkeypatch.setattr(index, "authenticate_pending", _pause_before_cas)
    with ThreadPoolExecutor(max_workers=1) as executor:
        callback_a = executor.submit(
            pg_client.get,
            "/v1/auth/anthropic/callback",
            params={"code": "code-A", "state": start_a.json()["state"]},
            follow_redirects=False,
        )
        assert cas_reached.wait(10), "A never reached its production durable-CAS boundary"
        start_b = pg_client.post("/v1/auth/anthropic/profiles", json={"name": name})
        release_cas.set()
        response_a = callback_a.result(timeout=10)

    assert start_b.status_code == 201
    assert response_a.status_code == 409
    assert response_a.json()["detail"]["code"] == "profile_auth_conflict"
    assert _profile_credential(pg_client, account_id, name) is None
    assert pg_client.get(f"/v1/auth/anthropic/profiles/{name}").json()["state"] == "pending"

    _app(pg_client).state.anthropic_http_factory = _token_factory("oauth-B-token")
    response_b = pg_client.get(
        "/v1/auth/anthropic/callback",
        params={"code": "code-B", "state": start_b.json()["state"]},
        follow_redirects=False,
    )
    assert response_b.status_code == 200


def test_stale_error_read_before_delete_cannot_resurrect_profile_on_postgres(
    pg_client: TestClient,
    monkeypatch,
) -> None:
    name = f"error-delete-{uuid4()}"
    account_id = pg_client.get("/v1/auth/me").json()["id"]
    _app(pg_client).state.anthropic_http_factory = _failing_token_factory()
    started = pg_client.post("/v1/auth/anthropic/profiles", json={"name": name})
    index = _app(pg_client).state.profile_index
    mark_pending_error = index.mark_pending_error
    error_precondition_read = threading.Event()
    release_error_cas = threading.Event()

    async def _pause_after_error_precondition(profile_id: str, **kwargs) -> None:
        observed = await index.get(account_id, "anthropic", name)
        assert observed is not None and observed.state.value == "pending"
        error_precondition_read.set()
        if not await asyncio.to_thread(release_error_cas.wait, 10):
            raise TimeoutError("error CAS was not released")
        await mark_pending_error(profile_id, **kwargs)

    monkeypatch.setattr(index, "mark_pending_error", _pause_after_error_precondition)
    with ThreadPoolExecutor(max_workers=1) as executor:
        callback = executor.submit(
            pg_client.get,
            "/callback",
            params={"code": "bad-code", "state": started.json()["state"]},
            follow_redirects=False,
        )
        assert error_precondition_read.wait(10), "failure path never read its pending profile"
        deleted = pg_client.delete(f"/v1/auth/anthropic/profiles/{name}")
        release_error_cas.set()
        failed = callback.result(timeout=10)

    assert deleted.status_code == 204
    assert failed.status_code == 500
    assert pg_client.get(f"/v1/auth/anthropic/profiles/{name}").status_code == 404
    assert _profile_credential(pg_client, account_id, name) is None


def test_profile_absent_credential_delete_set_commit_orders_on_postgres(
    pg_client: TestClient,
    monkeypatch,
) -> None:
    account_id = pg_client.get("/v1/auth/me").json()["id"]
    index = _app(pg_client).state.profile_index

    delete_first = f"profile-delete-first-{uuid4()}"
    assert (
        pg_client.post("/v1/auth/anthropic/profiles", json={"name": delete_first}).status_code
        == 201
    )
    remove = index.remove
    upsert = index.upsert
    delete_holds_index = threading.Event()
    set_attempted_index = threading.Event()
    release_delete = threading.Event()

    async def _holding_remove(profile_id: str) -> None:
        await remove(profile_id)
        delete_holds_index.set()
        if not await asyncio.to_thread(release_delete.wait, 10):
            raise TimeoutError("profile delete was not released")

    async def _attempting_upsert(*args, **kwargs) -> None:
        set_attempted_index.set()
        await upsert(*args, **kwargs)

    monkeypatch.setattr(index, "remove", _holding_remove)
    monkeypatch.setattr(index, "upsert", _attempting_upsert)
    with ThreadPoolExecutor(max_workers=2) as executor:
        deleting = executor.submit(
            pg_client.delete,
            f"/v1/auth/anthropic/profiles/{delete_first}",
        )
        assert delete_holds_index.wait(10)
        setting = executor.submit(
            pg_client.put,
            f"/v1/auth/anthropic/profiles/{delete_first}/api-key",
            json={"api_key": _API_KEY},
        )
        assert set_attempted_index.wait(10)
        release_delete.set()
        deleted = deleting.result(timeout=10)
        set_result = setting.result(timeout=10)

    assert deleted.status_code == 204
    assert set_result.status_code == 409
    assert pg_client.get(f"/v1/auth/anthropic/profiles/{delete_first}").status_code == 404
    assert _profile_credential(pg_client, account_id, delete_first) is None

    monkeypatch.setattr(index, "remove", remove)
    monkeypatch.setattr(index, "upsert", upsert)
    set_first = f"profile-set-first-{uuid4()}"
    assert (
        pg_client.post("/v1/auth/anthropic/profiles", json={"name": set_first}).status_code == 201
    )
    set_holds_index = threading.Event()
    delete_attempted_index = threading.Event()
    release_set = threading.Event()

    async def _holding_upsert(*args, **kwargs) -> None:
        await upsert(*args, **kwargs)
        set_holds_index.set()
        if not await asyncio.to_thread(release_set.wait, 10):
            raise TimeoutError("profile set was not released")

    async def _attempting_remove(profile_id: str) -> None:
        delete_attempted_index.set()
        await remove(profile_id)

    monkeypatch.setattr(index, "upsert", _holding_upsert)
    monkeypatch.setattr(index, "remove", _attempting_remove)
    with ThreadPoolExecutor(max_workers=2) as executor:
        setting = executor.submit(
            pg_client.put,
            f"/v1/auth/anthropic/profiles/{set_first}/api-key",
            json={"api_key": _API_KEY},
        )
        assert set_holds_index.wait(10)
        deleting = executor.submit(
            pg_client.delete,
            f"/v1/auth/anthropic/profiles/{set_first}",
        )
        assert delete_attempted_index.wait(10)
        release_set.set()
        set_result = setting.result(timeout=10)
        deleted = deleting.result(timeout=10)

    assert set_result.status_code == 200
    assert deleted.status_code == 204
    assert pg_client.get(f"/v1/auth/anthropic/profiles/{set_first}").status_code == 404
    assert _profile_credential(pg_client, account_id, set_first) is None


def test_connection_absent_credential_delete_set_commit_orders_on_postgres(
    pg_client: TestClient,
    monkeypatch,
) -> None:
    account_id = pg_client.get("/v1/auth/me").json()["id"]

    async def _seed_errored_connection(label: str) -> UUID:
        store = OAuthConnectionStore()
        connection_id = uuid4()
        connection = await store.create_api_key(
            account_id=account_id,
            provider="anthropic",
            label=label,
            connection_id=connection_id,
        )
        await store.mark_error(connection, "credential absent")
        return connection_id

    portal = pg_client.portal
    if portal is None:
        raise AssertionError("TestClient portal is not active")
    delete_first: UUID = portal.call(_seed_errored_connection, f"conn-delete-first-{uuid4()}")
    mark_revoked = OAuthConnectionStore.mark_revoked
    reactivate = OAuthConnectionStore.reactivate
    delete_holds_connection = threading.Event()
    set_attempted_connection = threading.Event()
    release_delete = threading.Event()

    async def _holding_revoke(self, connection, *args, **kwargs):
        revoked = await mark_revoked(self, connection, *args, **kwargs)
        delete_holds_connection.set()
        if not await asyncio.to_thread(release_delete.wait, 10):
            raise TimeoutError("connection delete was not released")
        return revoked

    async def _attempting_reactivate(self, connection):
        set_attempted_connection.set()
        return await reactivate(self, connection)

    monkeypatch.setattr(OAuthConnectionStore, "mark_revoked", _holding_revoke)
    monkeypatch.setattr(OAuthConnectionStore, "reactivate", _attempting_reactivate)
    with ThreadPoolExecutor(max_workers=2) as executor:
        deleting = executor.submit(pg_client.delete, f"/v1/oauth/connections/{delete_first}")
        assert delete_holds_connection.wait(10)
        setting = executor.submit(
            pg_client.put,
            f"/v1/oauth/connections/{delete_first}/api-key",
            json={"api_key": _API_KEY},
        )
        assert set_attempted_connection.wait(10)
        release_delete.set()
        deleted = deleting.result(timeout=10)
        set_result = setting.result(timeout=10)

    assert deleted.status_code == 204
    assert set_result.status_code == 409
    assert pg_client.get(f"/v1/oauth/connections/{delete_first}").json()["status"] == "revoked"
    assert _connection_credential(pg_client, account_id, delete_first) is None

    monkeypatch.setattr(OAuthConnectionStore, "mark_revoked", mark_revoked)
    monkeypatch.setattr(OAuthConnectionStore, "reactivate", reactivate)
    set_first: UUID = portal.call(_seed_errored_connection, f"conn-set-first-{uuid4()}")
    set_holds_connection = threading.Event()
    delete_attempted_connection = threading.Event()
    release_set = threading.Event()

    async def _holding_reactivate(self, connection):
        activated = await reactivate(self, connection)
        set_holds_connection.set()
        if not await asyncio.to_thread(release_set.wait, 10):
            raise TimeoutError("connection set was not released")
        return activated

    async def _attempting_revoke(self, connection, *args, **kwargs):
        delete_attempted_connection.set()
        return await mark_revoked(self, connection, *args, **kwargs)

    monkeypatch.setattr(OAuthConnectionStore, "reactivate", _holding_reactivate)
    monkeypatch.setattr(OAuthConnectionStore, "mark_revoked", _attempting_revoke)
    with ThreadPoolExecutor(max_workers=2) as executor:
        setting = executor.submit(
            pg_client.put,
            f"/v1/oauth/connections/{set_first}/api-key",
            json={"api_key": _API_KEY},
        )
        assert set_holds_connection.wait(10)
        deleting = executor.submit(pg_client.delete, f"/v1/oauth/connections/{set_first}")
        assert delete_attempted_connection.wait(10)
        release_set.set()
        set_result = setting.result(timeout=10)
        deleted = deleting.result(timeout=10)

    assert set_result.status_code == 200
    assert deleted.status_code == 204
    assert pg_client.get(f"/v1/oauth/connections/{set_first}").json()["status"] == "revoked"
    assert _connection_credential(pg_client, account_id, set_first) is None
