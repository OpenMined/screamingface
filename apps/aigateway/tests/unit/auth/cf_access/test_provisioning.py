"""Just-in-time provisioning — the product goal: no registration, no /login."""

from __future__ import annotations

import asyncio

import pytest

from aigateway.core.auth.cf_access import CF_ACCESS_IDP, CfAccessIdentity
from aigateway.core.auth.cf_access.provisioning import get_or_create_cf_access_account
from aigateway.core.auth.models import Account

pytestmark = pytest.mark.asyncio

IDENTITY = CfAccessIdentity(
    subject="cf-user-uuid-1",
    email="user@example.com",
    is_service_token=False,
)


async def test_first_request_creates_the_account(db) -> None:
    account = await get_or_create_cf_access_account(IDENTITY)

    assert account is not None
    assert account.external_idp == CF_ACCESS_IDP
    assert account.external_subject == "cf-user-uuid-1"
    assert account.email == "user@example.com"
    assert account.password_hash is None
    assert account.is_admin is False
    assert await Account.all().count() == 1


async def test_second_request_reuses_the_same_account(db) -> None:
    first = await get_or_create_cf_access_account(IDENTITY)
    second = await get_or_create_cf_access_account(IDENTITY)

    assert first is not None and second is not None
    assert first.id == second.id
    assert await Account.all().count() == 1


async def test_concurrent_first_requests_create_exactly_one_account(db) -> None:
    # WHY this is the NORMAL case: an SDK with a connection pool issues several
    # first requests at once. Without the (idp, subject) unique constraint from
    # OME-590 this silently produces two accounts for one person.
    results = await asyncio.gather(*(get_or_create_cf_access_account(IDENTITY) for _ in range(6)))

    assert await Account.all().count() == 1
    assert len({account.id for account in results if account is not None}) == 1


async def test_email_change_follows_the_subject(db) -> None:
    # INVARIANT: the subject is the identity; email is a mutable label. A user
    # who renames at the IdP keeps their account and history.
    created = await get_or_create_cf_access_account(IDENTITY)
    renamed = await get_or_create_cf_access_account(
        CfAccessIdentity(subject="cf-user-uuid-1", email="new@example.com", is_service_token=False)
    )

    assert created is not None and renamed is not None
    assert renamed.id == created.id
    assert renamed.email == "new@example.com"
    assert await Account.all().count() == 1


async def test_a_different_subject_with_the_same_email_is_a_different_account(db) -> None:
    # INVARIANT: keying on email would hand a reassigned corporate address the
    # previous holder's account and credentials.
    first = await get_or_create_cf_access_account(IDENTITY)
    second = await get_or_create_cf_access_account(
        CfAccessIdentity(
            subject="cf-user-uuid-2",
            email="user@example.com",
            is_service_token=False,
        )
    )

    assert first is not None and second is not None
    assert first.id != second.id


async def test_service_token_identity_provisions_without_an_email(db) -> None:
    account = await get_or_create_cf_access_account(
        CfAccessIdentity(subject="client-id-abc", email=None, is_service_token=True)
    )

    assert account is not None
    assert account.external_subject == "client-id-abc"
    assert account.email is None
    assert account.is_admin is False


async def test_admin_allowlist_grants_admin_at_creation(db) -> None:
    account = await get_or_create_cf_access_account(
        IDENTITY, admin_emails=frozenset({"user@example.com"})
    )

    assert account is not None
    assert account.is_admin is True


async def test_admin_allowlist_is_case_insensitive(db) -> None:
    account = await get_or_create_cf_access_account(
        CfAccessIdentity(
            subject="cf-user-uuid-9",
            email="User@Example.COM",
            is_service_token=False,
        ),
        admin_emails=frozenset({"user@example.com"}),
    )

    assert account is not None
    assert account.is_admin is True


async def test_a_service_token_can_never_match_the_admin_allowlist(db) -> None:
    # INVARIANT: admin is granted from a verified email. A service token has
    # none, so it must never satisfy the allowlist by any path.
    account = await get_or_create_cf_access_account(
        CfAccessIdentity(subject="client-id-abc", email=None, is_service_token=True),
        admin_emails=frozenset({"user@example.com", ""}),
    )

    assert account is not None
    assert account.is_admin is False


async def test_deactivated_account_is_refused(db) -> None:
    # INVARIANT: a gateway admin's deactivation outranks Cloudflare still
    # admitting the user at the edge.
    created = await get_or_create_cf_access_account(IDENTITY)
    assert created is not None
    created.is_active = False
    await created.save(update_fields=["is_active"])

    assert await get_or_create_cf_access_account(IDENTITY) is None


async def test_username_collision_with_a_local_account_surfaces(db) -> None:
    # A pre-existing local account already holding the derived username must not
    # be silently adopted as this federated identity.
    await Account.create(
        username=IDENTITY.username,
        password_hash="hashed",
    )

    with pytest.raises(Exception):
        await get_or_create_cf_access_account(IDENTITY)


async def test_username_is_derived_from_the_subject_not_the_email(db) -> None:
    # INVARIANT (regression): `username` is UNIQUE. Deriving it from the mutable
    # email made two distinct subjects sharing an address collide, so the second
    # user could not be provisioned at all.
    assert IDENTITY.username == f"{CF_ACCESS_IDP}:cf-user-uuid-1"


async def test_an_overlong_subject_is_hashed_not_truncated(db) -> None:
    long_a = CfAccessIdentity(subject="s" * 200 + "a", email=None, is_service_token=True)
    long_b = CfAccessIdentity(subject="s" * 200 + "b", email=None, is_service_token=True)

    assert len(long_a.username) <= 64
    assert long_a.username != long_b.username, "truncation would collide distinct subjects"
