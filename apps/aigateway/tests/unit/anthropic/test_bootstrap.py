import json
import time

import pytest
from fastapi.testclient import TestClient

from aigateway.core.profile_index import INDEX_KEYCHAIN_SERVICE, ProfileIndexStore
from aigateway.core.profile_models import Profile, profile_id_for
from aigateway.plugins.anthropic_provider.auth import keychain_service_for
from aigateway.plugins.anthropic_provider.bootstrap import bootstrap_from_claude_code
from tests.conftest import _prepare_sqlite_db

CC_SERVICE = "Claude Code-credentials"
ACCOUNT_ID = "account-1"


def _configure_app_db(monkeypatch, tmp_path) -> None:
    database_url = f"sqlite://{tmp_path / 'aigateway.sqlite3'}"
    monkeypatch.setenv("AIGATEWAY_DATABASE_URL", database_url)
    monkeypatch.setenv("AIGATEWAY_ADMIN_PASSWORD", "test-admin-password")
    monkeypatch.setenv("AIGATEWAY_JWT_SECRET", "x" * 32)
    monkeypatch.setenv("AIGATEWAY_PROVISIONING_TOKEN", "p" * 32)
    _prepare_sqlite_db(database_url)


def _auth_header(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/v1/auth/login",
        json={"username": "admin", "password": "test-admin-password"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.mark.asyncio
async def test_bootstrap_imports_cc_default_when_index_empty(fake_keychain) -> None:
    cc_payload = json.dumps(
        {
            "claudeAiOauth": {
                "accessToken": "cc-tok",
                "refreshToken": "cc-rt",
                "expiresAt": int(time.time() * 1000) + 3_600_000,
                "scopes": ["user:inference"],
            }
        }
    )
    fake_keychain.write(CC_SERVICE, "alice", cc_payload)

    await bootstrap_from_claude_code(
        account_id=ACCOUNT_ID,
        credential_store=fake_keychain,
        index_store=ProfileIndexStore(credential_store=fake_keychain),
        cc_account="alice",
    )

    aigw_payload = fake_keychain.read(keychain_service_for(f"{ACCOUNT_ID}:default"), "default")
    assert aigw_payload is not None
    converted = json.loads(aigw_payload)
    assert converted["access_token"] == "cc-tok"
    assert converted["refresh_token"] == "cc-rt"
    assert "expires_at_ms" in converted

    idx_raw = fake_keychain.read(INDEX_KEYCHAIN_SERVICE, "default")
    assert idx_raw is not None
    assert profile_id_for(ACCOUNT_ID, "anthropic", "default") in idx_raw

    # CC entry untouched
    assert fake_keychain.read(CC_SERVICE, "alice") == cc_payload


@pytest.mark.asyncio
async def test_bootstrap_noop_when_index_already_exists(fake_keychain) -> None:
    await ProfileIndexStore(credential_store=fake_keychain).upsert(
        Profile(
            id=profile_id_for(ACCOUNT_ID, "x", "y"),
            account_id=ACCOUNT_ID,
            provider="x",
            name="y",
        )
    )
    fake_keychain.write(
        CC_SERVICE,
        "alice",
        json.dumps({"claudeAiOauth": {"accessToken": "x", "refreshToken": "y", "expiresAt": 1}}),
    )
    await bootstrap_from_claude_code(
        account_id=ACCOUNT_ID,
        credential_store=fake_keychain,
        index_store=ProfileIndexStore(credential_store=fake_keychain),
        cc_account="alice",
    )
    assert fake_keychain.read(keychain_service_for(f"{ACCOUNT_ID}:default"), "default") is None


@pytest.mark.asyncio
async def test_bootstrap_noop_when_cc_entry_missing(fake_keychain) -> None:
    await bootstrap_from_claude_code(
        account_id=ACCOUNT_ID,
        credential_store=fake_keychain,
        index_store=ProfileIndexStore(credential_store=fake_keychain),
        cc_account="alice",
    )
    assert fake_keychain.read(INDEX_KEYCHAIN_SERVICE, "default") is None


def test_app_lifespan_runs_anthropic_bootstrap(fake_keychain, monkeypatch, tmp_path) -> None:
    _configure_app_db(monkeypatch, tmp_path)
    fake_keychain.write(
        CC_SERVICE,
        "alice",
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": "boot-tok",
                    "refreshToken": "boot-rt",
                    "expiresAt": int(time.time() * 1000) + 3_600_000,
                    "scopes": ["user:inference"],
                }
            }
        ),
    )
    monkeypatch.setenv("USER", "alice")
    monkeypatch.setenv("AIGATEWAY_BOOTSTRAP_FROM_CLAUDE_CODE", "1")

    from aigateway import main as main_module
    from aigateway.core import credential_store as cs_module
    from aigateway.core import profile_index as pi_module
    from aigateway.plugins.anthropic_provider import auth as auth_module

    monkeypatch.setattr(cs_module, "get_credential_store", lambda: fake_keychain)
    monkeypatch.setattr(pi_module, "get_credential_store", lambda: fake_keychain)
    monkeypatch.setattr(auth_module, "get_credential_store", lambda: fake_keychain)
    monkeypatch.setattr(main_module, "get_credential_store", lambda: fake_keychain)

    from aigateway.main import create_app

    app = create_app()
    with TestClient(app) as client:  # `with` triggers the lifespan
        resp = client.get("/v1/auth/profiles", headers=_auth_header(client))
        assert resp.status_code == 200
        profiles = resp.json()["profiles"]
        assert len(profiles) == 1
        assert profiles[0]["provider"] == "anthropic"
        assert profiles[0]["name"] == "default"
        assert profiles[0]["account_id"]
