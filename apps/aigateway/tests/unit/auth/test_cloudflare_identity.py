"""aigateway resolves the caller from the identity header the mesh gateway injects.

The trust model is the deployment's, not this module's: Cloudflare Access authenticates at the edge
and Envoy re-verifies that assertion before injecting `X-User-Email`, so in `cloudflare_headers`
mode the gateway reads the header directly. What these tests pin is everything that must hold GIVEN
that trust — above all that one caller maps to exactly one account, since `credential_blobs` hang
off that account's id and a caller resolving to a second account loses their stored credentials.
"""

from __future__ import annotations

import pytest
from starlette.datastructures import Headers
from tortoise.fields import CharField

from aigateway.config import Settings
from aigateway.core.auth.cloudflare_identity import CloudflareIdentity, identity_from_headers
from aigateway.core.auth.models import Account

EMAIL = "someone@openmined.org"


# --- parsing the header ----------------------------------------------------------------------


def test_a_caller_is_identified_by_their_verified_email() -> None:
    assert identity_from_headers({"X-User-Email": EMAIL}) == CloudflareIdentity(email=EMAIL)


def test_no_identity_header_is_no_identity() -> None:
    """`None` means "nothing presented", which the middleware turns into a 401 — never anonymous."""
    assert identity_from_headers({}) is None


def test_a_blank_header_is_treated_as_absent() -> None:
    """Blank carries no identity; treating it as one would let a reader think a caller was known."""
    assert identity_from_headers({"X-User-Email": "   "}) is None


def test_the_header_is_read_case_insensitively() -> None:
    """Header names are case-insensitive on the wire, whatever casing the gateway emits.

    Exercised through Starlette's `Headers`, not a plain dict: the case-insensitivity is the
    mapping's, which is exactly the contract `identity_from_headers` documents for its argument.
    """
    identity = identity_from_headers(Headers({"x-user-email": EMAIL}))

    assert identity == CloudflareIdentity(email=EMAIL)


def test_the_dropped_headers_no_longer_identify_anyone() -> None:
    """Tenant and service-token callers are deliberately out of scope.

    A Cloudflare service token carries `common_name` and no email, so automation gets a 401 in this
    mode rather than silently resolving to some account. Pinned so re-adding support is a visible
    decision rather than an accident.
    """
    assert identity_from_headers({"X-Tenant": "openmined", "X-Service-Id": "svc-abc"}) is None


# --- the account key ------------------------------------------------------------------------


def test_the_username_is_the_email() -> None:
    """`Account.username` is unique, so it IS the key — no second derivation to keep in step."""
    assert CloudflareIdentity(email=EMAIL).username == EMAIL


def test_address_case_does_not_split_one_person_into_two_accounts() -> None:
    upper = CloudflareIdentity(email="Someone@OpenMined.org")
    lower = CloudflareIdentity(email="someone@openmined.org")

    assert upper.username == lower.username


def test_the_display_name_keeps_the_address_as_it_arrived() -> None:
    assert CloudflareIdentity(email="Someone@OpenMined.org").display_name == "Someone@OpenMined.org"


def test_a_maximum_length_address_fits_the_username_column() -> None:
    """RFC 5321 allows 254 characters; the column was widened to 255 in migration 0008.

    Read off the model rather than hard-coded, so narrowing the column moves this test with it.
    """
    domain = "@openmined.org"
    longest = "a" * (254 - len(domain)) + domain
    column = Account._meta.fields_map["username"]  # noqa: SLF001 - the schema is the subject
    assert isinstance(column, CharField)

    assert len(longest) == 254
    assert len(CloudflareIdentity(email=longest).username) <= column.max_length


# --- through the app ------------------------------------------------------------------------


@pytest.fixture
def header_client(client):
    """The app switched into `cloudflare_headers` mode.

    `current_account` reads the mode per request, so flipping it on a built app exercises the same
    branch a header-mode deployment takes.
    """
    client.app.state.settings.auth_mode = "cloudflare_headers"
    return client


def test_a_caller_is_resolved_to_a_real_account(header_client) -> None:
    resp = header_client.get("/v1/auth/me", headers={"X-User-Email": EMAIL})

    assert resp.status_code == 200
    body = resp.json()
    assert body["username"] == EMAIL
    assert body["display_name"] == EMAIL


def test_a_repeat_caller_reuses_one_account_rather_than_accumulating_rows(header_client) -> None:
    """The property the stored credentials depend on: one caller, one account, one id."""
    first = header_client.get("/v1/auth/me", headers={"X-User-Email": EMAIL})
    second = header_client.get("/v1/auth/me", headers={"X-User-Email": EMAIL})

    assert first.json()["id"] == second.json()["id"]
    assert header_client.portal.call(_count_accounts, EMAIL) == 1


async def _count_accounts(username: str) -> int:
    return await Account.filter(username=username).count()


def test_a_differently_cased_address_resolves_to_the_same_account(header_client) -> None:
    first = header_client.get("/v1/auth/me", headers={"X-User-Email": EMAIL})
    second = header_client.get("/v1/auth/me", headers={"X-User-Email": EMAIL.upper()})

    assert first.json()["id"] == second.json()["id"]
    assert header_client.portal.call(_count_accounts, EMAIL) == 1


def test_two_callers_get_two_accounts(header_client) -> None:
    a = header_client.get("/v1/auth/me", headers={"X-User-Email": "a@openmined.org"})
    b = header_client.get("/v1/auth/me", headers={"X-User-Email": "b@openmined.org"})

    assert a.json()["id"] != b.json()["id"]


def test_a_caller_with_no_identity_header_is_rejected_not_made_anonymous(header_client) -> None:
    """The invariant that keeps a misconfigured mesh from becoming a shared-principal gateway."""
    resp = header_client.get("/v1/auth/me")

    assert resp.status_code == 401
    assert "X-User-Email" in resp.json()["detail"]


def test_a_bearer_token_alone_does_not_authenticate_in_header_mode(header_client) -> None:
    resp = header_client.get("/v1/auth/me", headers={"Authorization": "Bearer whatever"})

    assert resp.status_code == 401


def test_a_deactivated_account_is_rejected_not_reactivated(header_client) -> None:
    header_client.portal.call(_seed_inactive_account, EMAIL)

    resp = header_client.get("/v1/auth/me", headers={"X-User-Email": EMAIL})

    assert resp.status_code == 401
    assert header_client.portal.call(_is_active, EMAIL) is False


async def _seed_inactive_account(username: str) -> None:
    await Account.create(
        username=username, password_hash="", display_name=username, is_active=False
    )


async def _is_active(username: str) -> bool:
    account = await Account.get_or_none(username=username)
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
    assert Settings(auth_mode="cloudflare_headers").auth_mode == "cloudflare_headers"


def test_a_contradictory_auth_configuration_is_refused() -> None:
    """Silently preferring either setting would misrepresent the deployment's auth posture."""
    with pytest.raises(ValueError, match="conflicts with"):
        Settings(auth_enabled=False, auth_mode="cloudflare_headers")


def test_disabling_via_both_settings_is_consistent_and_allowed() -> None:
    assert Settings(auth_enabled=False, auth_mode="disabled").auth_mode == "disabled"
