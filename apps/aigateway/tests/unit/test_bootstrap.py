import json
import time

import pytest
from fastapi.testclient import TestClient

from aigateway.core.bootstrap import bootstrap_from_claude_code
from aigateway.core.profile_index import INDEX_KEYCHAIN_SERVICE, ProfileIndexStore
from aigateway.plugins.anthropic_provider.auth import keychain_service_for

CC_SERVICE = "Claude Code-credentials"


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
        credential_store=fake_keychain,
        index_store=ProfileIndexStore(credential_store=fake_keychain),
        cc_account="alice",
    )

    aigw_payload = fake_keychain.read(keychain_service_for("default"), "default")
    assert aigw_payload is not None
    converted = json.loads(aigw_payload)
    assert converted["access_token"] == "cc-tok"
    assert converted["refresh_token"] == "cc-rt"
    assert "expires_at_ms" in converted

    idx_raw = fake_keychain.read(INDEX_KEYCHAIN_SERVICE, "default")
    assert idx_raw is not None
    assert "anthropic:default" in idx_raw

    # CC entry untouched
    assert fake_keychain.read(CC_SERVICE, "alice") == cc_payload


@pytest.mark.asyncio
async def test_bootstrap_noop_when_index_already_exists(fake_keychain) -> None:
    fake_keychain.write(
        INDEX_KEYCHAIN_SERVICE,
        "default",
        '{"version":1,"profiles":[{"id":"x:y","provider":"x","name":"y"}]}',
    )
    fake_keychain.write(
        CC_SERVICE,
        "alice",
        json.dumps({"claudeAiOauth": {"accessToken": "x", "refreshToken": "y", "expiresAt": 1}}),
    )
    await bootstrap_from_claude_code(
        credential_store=fake_keychain,
        index_store=ProfileIndexStore(credential_store=fake_keychain),
        cc_account="alice",
    )
    assert fake_keychain.read(keychain_service_for("default"), "default") is None


@pytest.mark.asyncio
async def test_bootstrap_noop_when_cc_entry_missing(fake_keychain) -> None:
    await bootstrap_from_claude_code(
        credential_store=fake_keychain,
        index_store=ProfileIndexStore(credential_store=fake_keychain),
        cc_account="alice",
    )
    assert fake_keychain.read(INDEX_KEYCHAIN_SERVICE, "default") is None


def test_app_lifespan_runs_bootstrap(fake_keychain, monkeypatch) -> None:
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

    from aigateway.core import bootstrap as bs_module
    from aigateway.core import credential_store as cs_module
    from aigateway.core import profile_index as pi_module
    from aigateway.plugins.anthropic_provider import auth as auth_module

    monkeypatch.setattr(cs_module, "get_credential_store", lambda: fake_keychain)
    monkeypatch.setattr(pi_module, "get_credential_store", lambda: fake_keychain)
    monkeypatch.setattr(bs_module, "get_credential_store", lambda: fake_keychain)
    monkeypatch.setattr(auth_module, "get_credential_store", lambda: fake_keychain)

    from aigateway.main import create_app

    app = create_app()
    with TestClient(app) as client:  # `with` triggers the lifespan
        resp = client.get("/v1/auth/profiles")
        assert resp.status_code == 200
        ids = [p["id"] for p in resp.json()["profiles"]]
        assert "anthropic:default" in ids
