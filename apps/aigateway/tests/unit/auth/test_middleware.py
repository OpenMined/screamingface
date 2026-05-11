from __future__ import annotations

from aigateway.core.auth import middleware
from aigateway.core.auth.jwt import encode_token
from aigateway.core.auth.middleware import ANONYMOUS_ACCOUNT_ID, anonymous_account
from aigateway.core.auth.models import Account, BaseAccount


def test_missing_authorization_rejected(client) -> None:
    response = client.get("/v1/models")
    assert response.status_code == 401


def test_auth_disabled_returns_anonymous_account_without_token(client, monkeypatch) -> None:
    client.app.state.settings.auth_enabled = False

    async def fail_lookup(*_args, **_kwargs):
        raise AssertionError("disabled auth should not look up accounts")

    monkeypatch.setattr(middleware.Account, "get_or_none", staticmethod(fail_lookup))
    response = client.get("/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["id"] == str(ANONYMOUS_ACCOUNT_ID)
    assert response.json()["username"] == "anonymous"
    assert response.json()["display_name"] == "Anonymous"


def test_anonymous_account_uses_base_account_interface() -> None:
    account = anonymous_account()
    assert isinstance(account, BaseAccount)
    assert isinstance(account, Account)
    assert account.id == ANONYMOUS_ACCOUNT_ID
    assert account.username == "anonymous"


def test_malformed_token_rejected(client) -> None:
    response = client.get("/v1/models", headers={"Authorization": "Bearer not-a-token"})
    assert response.status_code == 401


def test_expired_token_rejected(client) -> None:
    token, _ = encode_token(
        account_id="missing",
        username="missing",
        secret="x" * 32,
        ttl_seconds=-1,
    )
    response = client.get("/v1/models", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert "expired" in response.text.lower()


def test_token_for_nonexistent_account_rejected(client) -> None:
    token, _ = encode_token(
        account_id="00000000-0000-0000-0000-000000000000",
        username="ghost",
        secret="x" * 32,
        ttl_seconds=60,
    )
    response = client.get("/v1/models", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_token_with_malformed_subject_rejected_before_db_lookup(client, monkeypatch) -> None:
    token, _ = encode_token(
        account_id="not-a-uuid",
        username="ghost",
        secret="x" * 32,
        ttl_seconds=60,
    )

    async def fail_lookup(*_args, **_kwargs):
        raise AssertionError("malformed subject should be rejected before DB lookup")

    monkeypatch.setattr(middleware.Account, "get_or_none", staticmethod(fail_lookup))
    response = client.get("/v1/models", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert "malformed subject" in response.text


def test_token_for_inactive_account_rejected(client) -> None:
    async def _deactivate() -> None:
        admin = await Account.get(username="admin")
        admin.is_active = False
        await admin.save(update_fields=["is_active"])

    token = client.post(
        "/v1/auth/login",
        json={"username": "admin", "password": "test-admin-password"},
    ).json()["token"]
    client.portal.call(_deactivate)
    response = client.get("/v1/models", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_valid_token_allowed(authenticated_client) -> None:
    response = authenticated_client.get("/v1/models")
    assert response.status_code == 200


def test_healthz_stays_open(client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
