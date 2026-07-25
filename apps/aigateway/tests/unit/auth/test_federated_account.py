from __future__ import annotations

import logging

import pytest
from tortoise.exceptions import IntegrityError

from aigateway.core.auth.models import Account

CF_IDP = "cf_access"


async def _create_federated(
    *,
    username: str = "cf-user",
    subject: str = "cf-sub-1",
    email: str | None = "cf-user@example.com",
) -> Account:
    return await Account.create(
        username=username,
        password_hash=None,
        external_idp=CF_IDP,
        external_subject=subject,
        email=email,
    )


@pytest.mark.asyncio
async def test_account_can_be_created_without_a_password_hash(db) -> None:
    # FEATURE: JIT provisioning — a Cloudflare-authenticated user has no password.
    account = await _create_federated()

    assert account.password_hash is None
    assert account.external_idp == CF_IDP
    assert account.external_subject == "cf-sub-1"
    assert account.email == "cf-user@example.com"


@pytest.mark.asyncio
async def test_duplicate_external_identity_is_rejected(db) -> None:
    # INVARIANT: (external_idp, external_subject) is THE federated identity key —
    # it is what makes concurrent first-request provisioning safe (OME-591).
    await _create_federated(username="first", subject="same-sub")

    with pytest.raises(IntegrityError):
        await _create_federated(username="second", subject="same-sub")


@pytest.mark.asyncio
async def test_same_subject_under_a_different_idp_is_allowed(db) -> None:
    await _create_federated(username="first", subject="shared")
    other = await Account.create(
        username="second",
        password_hash=None,
        external_idp="some_other_idp",
        external_subject="shared",
    )

    assert other.id is not None


@pytest.mark.asyncio
async def test_many_local_accounts_coexist_with_null_external_identity(db) -> None:
    # WHY: SQL treats NULLs as distinct under a unique constraint, so the federated
    # key must not collide local accounts with each other. Asserted, not assumed —
    # a naive constraint would make the second local account unwritable.
    for name in ("local-a", "local-b", "local-c"):
        await Account.create(username=name, password_hash="hashed")

    assert await Account.filter(external_idp=None).count() == 3


def test_federated_account_cannot_log_in_with_a_password(client, caplog) -> None:
    # INVARIANT: a null password_hash is not a password — it is the absence of one.
    # Login must refuse, and refuse INDISTINGUISHABLY from bad credentials so no
    # federation-status enumeration oracle exists (same rule as SF-335).
    async def _seed() -> None:
        await _create_federated(username="cf-user")

    client.portal.call(_seed)

    with caplog.at_level(logging.INFO):
        refused = client.post(
            "/v1/auth/login",
            json={"username": "cf-user", "password": "any-password-at-all"},
        )
    unknown = client.post(
        "/v1/auth/login",
        json={"username": "no-such-user", "password": "any-password-at-all"},
    )

    assert refused.status_code == 401
    assert refused.json()["detail"]["code"] == "invalid_credentials"
    assert (refused.status_code, refused.content) == (unknown.status_code, unknown.content)
    assert any("cf-user" in record.getMessage() for record in caplog.records)


def test_federated_account_rejects_the_public_dummy_password(client) -> None:
    # INVARIANT: `verify_password_or_dummy` falls back to the hash of the PUBLIC
    # constant `passwords._DUMMY_PASSWORD` when the stored hash is NULL. Submitting
    # that constant verbatim therefore makes bcrypt return True. Login must refuse
    # on the NULL itself, never on the verification result alone.
    from aigateway.core.auth.passwords import _DUMMY_PASSWORD

    async def _seed() -> None:
        await _create_federated(username="cf-user")

    client.portal.call(_seed)

    response = client.post(
        "/v1/auth/login",
        json={"username": "cf-user", "password": _DUMMY_PASSWORD.decode()},
    )

    assert response.status_code == 401


def test_local_accounts_still_log_in(client) -> None:
    response = client.post(
        "/v1/auth/login",
        json={"username": "admin", "password": "test-admin-password"},
    )

    assert response.status_code == 200


def test_account_out_exposes_email_and_never_the_hash(authenticated_client) -> None:
    body = authenticated_client.get("/v1/auth/me").json()

    assert "email" in body
    assert "password_hash" not in body
