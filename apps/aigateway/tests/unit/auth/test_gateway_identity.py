"""aigateway resolves the caller from the identity headers Envoy injects.

The trust model is the deployment's, not this module's: Envoy clears and re-injects these headers
from verified claims, so in `gateway_headers` mode the gateway reads them directly. What these tests
pin is everything that must hold GIVEN that trust — above all that the derived account id is stable,
because `credential_blobs` and `oauth_connections` are keyed on it and an unstable id orphans every
credential the caller has stored.
"""

from __future__ import annotations

import pytest

from aigateway.config import Settings
from aigateway.core.auth.gateway_identity import (
    GatewayIdentity,
    identity_from_headers,
)
from aigateway.core.auth.models import Account

TENANT = "openmined"
EMAIL = "someone@openmined.org"
USER_ID = "sub-123"
SERVICE_ID = "svc-abc"


def _headers(**overrides: str) -> dict[str, str]:
    return {"X-Tenant": TENANT, **overrides}


# --- parsing the headers ---------------------------------------------------------------------


def test_a_human_caller_is_identified_by_their_user_id() -> None:
    """`X-User-Id` is the token's `sub` and outlives an address change, so it beats the email."""
    identity = identity_from_headers(_headers(**{"X-User-Id": USER_ID, "X-User-Email": EMAIL}))

    assert identity == GatewayIdentity(tenant=TENANT, kind="user", subject=USER_ID, email=EMAIL)


def test_an_email_only_caller_falls_back_to_the_email_as_subject() -> None:
    identity = identity_from_headers(_headers(**{"X-User-Email": EMAIL}))

    assert identity is not None
    assert identity.kind == "user"
    assert identity.subject == EMAIL


def test_a_service_caller_is_identified_by_its_service_id() -> None:
    identity = identity_from_headers(_headers(**{"X-Service-Id": SERVICE_ID}))

    assert identity == GatewayIdentity(tenant=TENANT, kind="service", subject=SERVICE_ID)


def test_no_identity_headers_is_no_identity() -> None:
    assert identity_from_headers(_headers()) is None


def test_a_missing_tenant_is_no_identity() -> None:
    """The tenant is the namespace every subject is scoped under — without it, two tenants'
    callers sharing a subject would share an account, so it fails closed."""
    assert identity_from_headers({"X-User-Email": EMAIL}) is None


def test_blank_headers_are_treated_as_absent() -> None:
    assert identity_from_headers({"X-Tenant": "  ", "X-User-Email": EMAIL}) is None
    assert identity_from_headers(_headers(**{"X-User-Email": "   "})) is None


def test_a_blank_user_id_falls_through_to_the_email() -> None:
    identity = identity_from_headers(_headers(**{"X-User-Id": "  ", "X-User-Email": EMAIL}))

    assert identity is not None
    assert identity.subject == EMAIL


# --- deriving the account -------------------------------------------------------------------


def test_the_same_identity_always_derives_the_same_account_id() -> None:
    """The property the stored credentials depend on. Derived, never allocated."""
    first = GatewayIdentity(tenant=TENANT, kind="user", subject=USER_ID)
    second = GatewayIdentity(tenant=TENANT, kind="user", subject=USER_ID, email=EMAIL)

    # The email is descriptive only — it must not participate in the key, or a caller whose address
    # changes would lose access to their own credentials.
    assert first.account_id == second.account_id
    assert first.username == second.username


def test_different_tenants_are_different_accounts() -> None:
    a = GatewayIdentity(tenant="tenant-a", kind="user", subject=USER_ID)
    b = GatewayIdentity(tenant="tenant-b", kind="user", subject=USER_ID)

    assert a.account_id != b.account_id


def test_a_user_and_a_service_sharing_a_subject_are_different_accounts() -> None:
    user = GatewayIdentity(tenant=TENANT, kind="user", subject="shared")
    service = GatewayIdentity(tenant=TENANT, kind="service", subject="shared")

    assert user.account_id != service.account_id


def test_the_key_cannot_be_confused_across_field_boundaries() -> None:
    """A separator-collision would hand one tenant's caller another tenant's account."""
    a = GatewayIdentity(tenant="a:user", kind="user", subject="b")
    b = GatewayIdentity(tenant="a", kind="user", subject="user:b")

    assert a.account_id != b.account_id


def test_a_long_identity_still_fits_the_username_column() -> None:
    """`Account.username` is `max_length=64`; an email plus a tenant can exceed that."""
    identity = GatewayIdentity(
        tenant="a-very-long-tenant-name-for-some-organization",
        kind="user",
        subject="a.person.with.a.very.long.email.address@an-extremely-long-domain.example.org",
    )

    assert len(identity.username) <= 64
    assert identity.username.startswith("gw:")


def test_the_readable_identity_lives_in_the_display_name() -> None:
    identity = GatewayIdentity(tenant=TENANT, kind="user", subject=USER_ID, email=EMAIL)

    assert EMAIL in identity.display_name
    assert TENANT in identity.display_name


def test_email_case_does_not_split_one_person_into_two_accounts() -> None:
    lower = identity_from_headers(_headers(**{"X-User-Email": "Someone@OpenMined.org"}))
    upper = identity_from_headers(_headers(**{"X-User-Email": "someone@openmined.org"}))

    assert lower is not None and upper is not None
    assert lower.account_id == upper.account_id


# --- through the app ------------------------------------------------------------------------


@pytest.fixture
def header_client(client):
    """The app switched into `gateway_headers` mode.

    `current_account` reads the mode per request, so flipping it on a built app exercises the same
    branch a header-mode deployment takes.
    """
    client.app.state.settings.auth_mode = "gateway_headers"
    return client


def test_a_human_caller_is_resolved_to_a_real_account(header_client) -> None:
    resp = header_client.get(
        "/v1/auth/me", headers=_headers(**{"X-User-Id": USER_ID, "X-User-Email": EMAIL})
    )

    assert resp.status_code == 200
    body = resp.json()
    expected = GatewayIdentity(tenant=TENANT, kind="user", subject=USER_ID, email=EMAIL)
    assert body["id"] == str(expected.account_id)
    assert EMAIL in body["display_name"]


def test_a_repeat_caller_reuses_one_account_rather_than_accumulating_rows(header_client) -> None:
    headers = _headers(**{"X-User-Id": USER_ID, "X-User-Email": EMAIL})

    first = header_client.get("/v1/auth/me", headers=headers)
    second = header_client.get("/v1/auth/me", headers=headers)

    assert first.json()["id"] == second.json()["id"]
    derived = GatewayIdentity(tenant=TENANT, kind="user", subject=USER_ID).account_id
    assert header_client.portal.call(_count_accounts, derived) == 1


async def _count_accounts(account_id) -> int:
    return await Account.filter(id=account_id).count()


def test_a_service_caller_gets_its_own_account(header_client) -> None:
    user = header_client.get("/v1/auth/me", headers=_headers(**{"X-User-Id": SERVICE_ID}))
    service = header_client.get("/v1/auth/me", headers=_headers(**{"X-Service-Id": SERVICE_ID}))

    assert user.status_code == 200
    assert service.status_code == 200
    assert user.json()["id"] != service.json()["id"]


def test_a_caller_with_no_identity_headers_is_rejected_not_made_anonymous(header_client) -> None:
    """The invariant that keeps a misconfigured mesh from becoming a shared-principal gateway."""
    resp = header_client.get("/v1/auth/me")

    assert resp.status_code == 401
    assert "X-Tenant" in resp.json()["detail"]


def test_a_bearer_token_alone_does_not_authenticate_in_header_mode(header_client) -> None:
    resp = header_client.get("/v1/auth/me", headers={"Authorization": "Bearer whatever"})

    assert resp.status_code == 401


def test_a_deactivated_derived_account_is_rejected_not_recreated(header_client) -> None:
    identity = GatewayIdentity(tenant=TENANT, kind="user", subject=USER_ID)
    header_client.portal.call(_seed_inactive_account, identity)

    resp = header_client.get("/v1/auth/me", headers=_headers(**{"X-User-Id": USER_ID}))

    assert resp.status_code == 401
    assert header_client.portal.call(_is_active, identity.account_id) is False


async def _seed_inactive_account(identity: GatewayIdentity) -> None:
    await Account.create(
        id=identity.account_id,
        username=identity.username,
        password_hash="",
        display_name=identity.display_name,
        is_active=False,
    )


async def _is_active(account_id) -> bool:
    account = await Account.get_or_none(id=account_id)
    assert account is not None
    return account.is_active


# --- the mode setting ----------------------------------------------------------------------


def test_the_legacy_flag_alone_still_disables_auth() -> None:
    """An existing deployment sets only `AIGATEWAY_AUTH_ENABLED` and must be unaffected."""
    assert Settings(auth_enabled=False).auth_mode == "disabled"
    assert Settings(auth_enabled=True).auth_mode == "jwt"


def test_the_default_mode_is_jwt() -> None:
    assert Settings().auth_mode == "jwt"


def test_an_explicit_mode_wins_over_the_legacy_default() -> None:
    assert Settings(auth_mode="gateway_headers").auth_mode == "gateway_headers"


def test_a_contradictory_auth_configuration_is_refused() -> None:
    """Silently preferring either setting would misrepresent the deployment's auth posture."""
    with pytest.raises(ValueError, match="conflicts with"):
        Settings(auth_enabled=False, auth_mode="gateway_headers")


def test_disabling_via_both_settings_is_consistent_and_allowed() -> None:
    assert Settings(auth_enabled=False, auth_mode="disabled").auth_mode == "disabled"
