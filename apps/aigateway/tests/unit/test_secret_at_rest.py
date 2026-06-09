from __future__ import annotations

import asyncio
import base64

import pytest
from fastapi.testclient import TestClient
from tortoise import Tortoise

from aigateway.config import Settings
from aigateway.core.auth.jwt_secret import JWT_SECRET_ACCOUNT, JWT_SECRET_SERVICE
from tests.conftest import TEST_SECRET_KEY


@pytest.fixture
def client_without_jwt_env(monkeypatch, credential_blobs):
    # Like the conftest `client` fixture but deliberately WITHOUT a JWT secret, so
    # the lifespan auto-generates it and persists it through the real,
    # lifespan-installed encrypting ORMStore. We build Settings with
    # _env_file=None so the app ignores the repo .env (which sets
    # AIGATEWAY_JWT_SECRET) — this test must exercise the generate-and-encrypt path.
    monkeypatch.delenv("AIGATEWAY_JWT_SECRET", raising=False)
    # Dict-spread so static checkers don't flag the dotenv/alias kwargs (read at
    # runtime by pydantic-settings via **values). _env_file=None bypasses the repo
    # .env so jwt_secret is truly absent.
    settings = Settings(
        **{
            "_env_file": None,
            "AIGATEWAY_DATABASE_URL": f"sqlite://{credential_blobs.db_path}",
            "AIGATEWAY_ADMIN_PASSWORD": "test-admin-password",
            # Match the probe key so credential_blobs.read() can decrypt what the app wrote.
            "AIGATEWAY_SECRET_KEY": base64.b64encode(TEST_SECRET_KEY).decode(),
            # Pin the provider so an ambient AIGATEWAY_SECRET_PROVIDER=kms in CI cannot
            # divert this test into the KMS stub (which would raise mid-lifespan).
            "AIGATEWAY_SECRET_PROVIDER": "local",
        }
    )
    assert settings.jwt_secret is None  # guard: the generate path must be reachable

    from aigateway.main import create_app

    with TestClient(create_app(settings=settings)) as test_client:
        yield test_client
    asyncio.run(Tortoise.close_connections())


def test_generated_jwt_secret_is_encrypted_at_rest(
    client_without_jwt_env: TestClient, credential_blobs
) -> None:
    # Login proves the real app (create_app -> lifespan -> build_secret_store ->
    # set_active_secret_store -> ORMStore via get_active_secret_store) is wired and
    # that the auto-generated JWT secret round-trips.
    resp = client_without_jwt_env.post(
        "/v1/auth/login", json={"username": "admin", "password": "test-admin-password"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json().get("token")

    # The lifespan-installed store wrote the JWT secret ENCRYPTED, not plaintext.
    raw = credential_blobs.read_raw(JWT_SECRET_SERVICE, JWT_SECRET_ACCOUNT)
    assert raw is not None
    assert raw.startswith("v1:")

    # And it decrypts back to the persisted >= 32-char secret.
    decrypted = credential_blobs.read(JWT_SECRET_SERVICE, JWT_SECRET_ACCOUNT)
    assert decrypted is not None
    assert len(decrypted) >= 32
    assert not decrypted.startswith("v1:")
