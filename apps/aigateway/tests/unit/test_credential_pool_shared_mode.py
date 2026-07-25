"""Global (shared) credential pools — admin CRUD + shared-mode chat resolution.

Covers docs/spec/2026-07-24-aigateway-shared-credential-pools-spec.md: admin-only
pool management, the AIGATEWAY_CREDENTIAL_MODE=shared branch in
chat_credentials.py, the 404 when no pool is configured, and that per-account
usage attribution (account_id) is unaffected by which credential backs the call.
"""

from __future__ import annotations

import asyncio
import base64
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from tortoise import Tortoise

from aigateway.db import build_tortoise_config
from aigateway.main import create_app
from tests.conftest import TEST_SECRET_KEY

_HF_KEY = "hf_shared_pool_key_1234567890"
_HF_MODEL = "huggingface/deepseek-ai/DeepSeek-R1:novita"


def _account_id(client) -> str:
    return client.get("/v1/auth/me").json()["id"]


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
def shared_mode_client(monkeypatch, credential_blobs):
    """Same wiring as the ``client``/``authenticated_client`` fixtures, but with
    AIGATEWAY_CREDENTIAL_MODE=shared — the gateway-wide mode switch is read once
    at Settings() construction inside create_app(), so it must be set before the
    app is built."""
    database_url = f"sqlite://{credential_blobs.db_path}"
    monkeypatch.setenv("AIGATEWAY_DATABASE_URL", database_url)
    monkeypatch.setenv("AIGATEWAY_ADMIN_PASSWORD", "test-admin-password")
    monkeypatch.setenv("AIGATEWAY_JWT_SECRET", "x" * 32)
    monkeypatch.setenv("AIGATEWAY_PROVISIONING_TOKEN", "p" * 32)
    monkeypatch.setenv("AIGATEWAY_SECRET_KEY", base64.b64encode(TEST_SECRET_KEY).decode())
    monkeypatch.setenv("AIGATEWAY_CREDENTIAL_MODE", "shared")
    _prepare_sqlite_db(database_url)

    with TestClient(create_app()) as test_client:
        yield test_client
    asyncio.run(Tortoise.close_connections())


@pytest.fixture
def shared_admin_client(shared_mode_client: TestClient) -> TestClient:
    response = shared_mode_client.post(
        "/v1/auth/login",
        json={"username": "admin", "password": "test-admin-password"},
    )
    assert response.status_code == 200, response.text
    shared_mode_client.headers.update({"Authorization": f"Bearer {response.json()['token']}"})
    return shared_mode_client


def _login_as(client: TestClient, username: str, password: str) -> None:
    response = client.post("/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    client.headers.update({"Authorization": f"Bearer {response.json()['token']}"})


@pytest.fixture
def valid_api_key_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """This module is intentionally NOT on the legacy frozen-allowlist in
    unit/conftest.py, so pool creation exercises the real ApiKeyValidationService
    unless a test installs this explicit double (matches that file's own
    convention for new API-key routes)."""
    from aigateway.core.api_key_validation import (
        ApiKeyValidationResult,
        ApiKeyValidationStage,
        ApiKeyValidationState,
    )
    from aigateway.core.api_key_validation_service import ApiKeyValidationService

    async def _valid(_self, _plugin, _provider, _api_key):
        return ApiKeyValidationResult(
            state=ApiKeyValidationState.VALID,
            stage=ApiKeyValidationStage.READINESS,
        )

    monkeypatch.setattr(ApiKeyValidationService, "validate", _valid)


# --- admin gating ---


def test_create_pool_requires_authentication(client: TestClient) -> None:
    resp = client.post(
        "/v1/admin/credential-pools",
        json={"provider": "huggingface", "api_key": _HF_KEY},
    )
    assert resp.status_code == 401


def test_create_pool_rejects_non_admin_account(
    authenticated_client: TestClient, provisioned_user_factory
) -> None:
    provisioned_user_factory("regular-user", "regular-pass1")
    _login_as(authenticated_client, "regular-user", "regular-pass1")

    resp = authenticated_client.post(
        "/v1/admin/credential-pools",
        json={"provider": "huggingface", "api_key": _HF_KEY},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "admin_required"


# --- admin CRUD (bootstrap "admin" account is is_admin=True) ---


def test_admin_can_create_list_patch_delete_pool(
    authenticated_client: TestClient, valid_api_key_validation: None
) -> None:
    create = authenticated_client.post(
        "/v1/admin/credential-pools",
        json={"provider": "huggingface", "api_key": _HF_KEY},
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["provider"] == "huggingface"
    assert body["auth_type"] == "api_key"
    assert body["is_active"] is True
    assert _HF_KEY not in create.text
    pool_id = body["id"]

    listed = authenticated_client.get("/v1/admin/credential-pools")
    assert listed.status_code == 200
    assert any(p["id"] == pool_id for p in listed.json()["pools"])

    # A second active pool for the same provider conflicts.
    conflict = authenticated_client.post(
        "/v1/admin/credential-pools",
        json={"provider": "huggingface", "api_key": _HF_KEY},
    )
    assert conflict.status_code == 409

    deactivated = authenticated_client.patch(
        f"/v1/admin/credential-pools/{pool_id}", json={"is_active": False}
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    deleted = authenticated_client.delete(f"/v1/admin/credential-pools/{pool_id}")
    assert deleted.status_code == 204
    assert authenticated_client.get(f"/v1/admin/credential-pools/{pool_id}").status_code == 404


# --- shared-mode chat resolution ---


def test_chat_shared_mode_without_pool_returns_actionable_404(
    shared_mode_client: TestClient, provisioned_user_factory
) -> None:
    provisioned_user_factory("alice", "alice-pass1")
    _login_as(shared_mode_client, "alice", "alice-pass1")

    resp = shared_mode_client.post(
        "/v1/chat/completions",
        json={"model": _HF_MODEL, "messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "credential_pool_not_configured"
    assert resp.json()["detail"]["provider"] == "huggingface"


def test_chat_shared_mode_uses_pool_credential_for_every_account(
    shared_admin_client: TestClient,
    provisioned_user_factory,
    valid_api_key_validation: None,
) -> None:
    create = shared_admin_client.post(
        "/v1/admin/credential-pools",
        json={"provider": "huggingface", "api_key": _HF_KEY},
    )
    assert create.status_code == 201, create.text

    provisioned_user_factory("alice", "alice-pass1")
    provisioned_user_factory("bob", "bob-pass1")

    captured_keys: list[str] = []
    captured_account_ids: list[str] = []

    async def fake_chat_completion(_self, body):
        captured_keys.append(body.get("api_key"))
        return SimpleNamespace(
            model_dump=lambda: {"id": "x", "choices": [{"message": {"content": "ok"}}]}
        )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "aigateway.core.plugin_base.ProviderPluginBase.chat_completion",
            fake_chat_completion,
        )
        for username, password in (("alice", "alice-pass1"), ("bob", "bob-pass1")):
            _login_as(shared_admin_client, username, password)
            captured_account_ids.append(_account_id(shared_admin_client))
            resp = shared_admin_client.post(
                "/v1/chat/completions",
                json={"model": _HF_MODEL, "messages": [{"role": "user", "content": "hi"}]},
            )
            assert resp.status_code == 200, resp.text

    # Both distinct accounts dispatched through the SAME shared key...
    assert len(captured_keys) == 2
    assert captured_keys[0] == _HF_KEY
    assert captured_keys[1] == _HF_KEY
    # ...yet each request is still attributable to its own, distinct account —
    # credential mode never touches request attribution (core/auth/middleware.py's
    # current_account() is unaffected by credential_mode).
    assert len(set(captured_account_ids)) == 2
