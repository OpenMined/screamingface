from __future__ import annotations

import asyncio
from statistics import median

import pytest

from aigateway.core.auth import passwords
from aigateway.core.auth.models import Account
from aigateway.core.auth.passwords import hash_password


def test_login_and_me(authenticated_client) -> None:
    response = authenticated_client.get("/v1/auth/me")
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "admin"
    assert "password" not in body
    assert "password_hash" not in body


def test_wrong_password_and_unknown_user_match(client) -> None:
    wrong = client.post(
        "/v1/auth/login",
        json={"username": "admin", "password": "wrong-pass"},
    )
    missing = client.post(
        "/v1/auth/login",
        json={"username": "missing", "password": "wrong-pass"},
    )
    assert wrong.status_code == 401
    assert missing.status_code == 401
    assert wrong.content == missing.content


def test_login_rejects_overlong_password(client) -> None:
    response = client.post(
        "/v1/auth/login",
        json={"username": "admin", "password": "a" * 73},
    )
    assert response.status_code == 422


def test_inactive_account_returns_locked(client) -> None:
    async def _deactivate() -> None:
        admin = await Account.get(username="admin")
        admin.is_active = False
        await admin.save(update_fields=["is_active"])

    client.portal.call(_deactivate)
    response = client.post(
        "/v1/auth/login",
        json={"username": "admin", "password": "test-admin-password"},
    )
    assert response.status_code == 423


@pytest.mark.asyncio
async def test_unknown_user_timing_close_to_wrong_password(client, monkeypatch) -> None:
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(passwords, "_BCRYPT_ROUNDS", 12)
    monkeypatch.setattr(passwords, "_dummy_hash", None)

    async def _strengthen_admin_hash() -> None:
        admin = await Account.get(username="admin")
        admin.password_hash = await hash_password("test-admin-password")
        await admin.save(update_fields=["password_hash"])

    client.portal.call(_strengthen_admin_hash)

    async def _post(username: str) -> float:
        start = loop.time()
        await asyncio.to_thread(
            client.post,
            "/v1/auth/login",
            json={"username": username, "password": "wrong-pass"},
        )
        return loop.time() - start

    await _post("admin")
    await _post("missing")

    wrong = median([await _post("admin") for _ in range(20)])
    missing = median([await _post("missing") for _ in range(20)])
    assert abs(missing - wrong) / wrong < 0.10


def test_login_delegates_to_password_verification_helper(client, monkeypatch) -> None:
    from aigateway.routes import auth_session

    calls: list[tuple[str, str | bytes | None]] = []

    async def fake_verify_password_or_dummy(password, password_hash) -> bool:
        calls.append((password.get_secret_value(), password_hash))
        return True

    monkeypatch.setattr(auth_session, "verify_password_or_dummy", fake_verify_password_or_dummy)

    response = client.post(
        "/v1/auth/login",
        json={"username": "admin", "password": "test-admin-password"},
    )

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0][0] == "test-admin-password"
    assert isinstance(calls[0][1], str)
