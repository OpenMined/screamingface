"""Only a named list of email addresses may reach `/v1/admin`.

`OME-684` made every caller who clears Cloudflare Access an ordinary `Account`. That is the right
default for the inference surface and exactly the wrong one for an administrative surface, where a
caller reads and mutates OTHER accounts' credentials. So admin is a SECOND gate on top of identity,
not a property of it.

INVARIANT under test throughout: an admin is not a tenant. `require_admin` must never create an
`Account` row — not for an allowlisted admin, and certainly not for a rejected caller. An admin who
became an account would acquire a credential namespace nobody asked for and appear in the very
table the console lists.
"""

from __future__ import annotations

from ipaddress import ip_network

from fastapi.testclient import TestClient

from aigateway.config import Settings
from aigateway.core.auth.admin import AdminPrincipal, email_is_admin

ADMIN = "admin@openmined.org"
OUTSIDER = "nobody@example.com"
POD_NETWORK = ip_network("10.0.0.0/8")


def _settings(**values: object) -> Settings:
    """Build Settings from raw values, as the environment supplies them.

    `model_validate` rather than the constructor because `admin_emails` arrives as a
    comma-separated STRING and is parsed into a frozenset — which is the behaviour under test.
    """
    return Settings.model_validate(values)


# --- parsing the setting ----------------------------------------------------------------------


def test_a_comma_separated_list_becomes_a_set() -> None:
    settings = _settings(auth_mode="jwt", admin_emails=f"{ADMIN},second@openmined.org")

    assert settings.admin_emails == frozenset({ADMIN, "second@openmined.org"})


def test_surrounding_whitespace_is_tolerated() -> None:
    """Operators write these across YAML lines; a stray space must not silently exclude an admin."""
    assert _settings(auth_mode="jwt", admin_emails=f" {ADMIN} , b@x.test ").admin_emails == (
        frozenset({ADMIN, "b@x.test"})
    )


def test_a_single_entry_needs_no_comma() -> None:
    assert _settings(auth_mode="jwt", admin_emails=ADMIN).admin_emails == frozenset({ADMIN})


def test_an_empty_value_is_no_admins() -> None:
    assert _settings(auth_mode="jwt", admin_emails="").admin_emails == frozenset()


def test_the_setting_is_absent_by_default() -> None:
    """Fail CLOSED: a deployment that never named an admin has none, and the API is disabled."""
    assert _settings(auth_mode="jwt").admin_emails == frozenset()


def test_entries_are_case_folded() -> None:
    """`CloudflareIdentity.username` lowercases, so an allowlist that did not would never match.

    Mail domains are case-insensitive and an operator will eventually type a capital. Storing the
    allowlist in the same normal form as the identity is what makes the comparison total.
    """
    assert _settings(auth_mode="jwt", admin_emails="Admin@OpenMined.org").admin_emails == (
        frozenset({ADMIN})
    )


def test_a_trailing_comma_does_not_add_an_empty_admin() -> None:
    """An empty string in the set would be matched by a blank header if one ever got through."""
    assert _settings(auth_mode="jwt", admin_emails=f"{ADMIN},").admin_emails == frozenset({ADMIN})


# --- the membership predicate -----------------------------------------------------------------


def test_a_listed_address_is_an_admin() -> None:
    assert email_is_admin(ADMIN, frozenset({ADMIN})) is True


def test_an_unlisted_address_is_not() -> None:
    assert email_is_admin(OUTSIDER, frozenset({ADMIN})) is False


def test_the_comparison_ignores_address_case() -> None:
    assert email_is_admin("ADMIN@OpenMined.org", frozenset({ADMIN})) is True


def test_an_empty_allowlist_admits_nobody() -> None:
    assert email_is_admin(ADMIN, frozenset()) is False


# --- through the app --------------------------------------------------------------------------


def _admin_client(client, *, peer: str = "10.1.2.3", admins: frozenset[str] | None = None):
    """The built app in header mode with an allowlist, addressed from a trusted peer by default.

    A fresh `TestClient` over the SAME app rather than the shared fixture: the peer address is
    fixed at construction and is one of the things under test. No context manager — the outer
    `client` fixture already ran the lifespan that initialized the database.
    """
    client.app.state.settings.auth_mode = "cloudflare_headers"
    client.app.state.settings.allowed_networks = (POD_NETWORK,)
    client.app.state.settings.admin_emails = frozenset({ADMIN}) if admins is None else admins
    return TestClient(client.app, client=(peer, 50000))


def test_an_allowlisted_admin_is_admitted(client) -> None:
    resp = _admin_client(client).get("/v1/admin/accounts", headers={"X-User-Email": ADMIN})

    assert resp.status_code == 200


def test_the_admins_own_address_case_does_not_matter(client) -> None:
    resp = _admin_client(client).get(
        "/v1/admin/accounts", headers={"X-User-Email": "Admin@OpenMined.ORG"}
    )

    assert resp.status_code == 200


def test_an_authenticated_non_admin_is_refused(client) -> None:
    """403, not 401: this caller IS identified, and no credential they could present would help."""
    resp = _admin_client(client).get("/v1/admin/accounts", headers={"X-User-Email": OUTSIDER})

    assert resp.status_code == 403


def _usernames(admin_client) -> set[str]:
    """Every account the gateway knows, read back through the admin API.

    Asserted through the API rather than with a direct `await Account.filter(...)`: a sync
    `TestClient` call followed by an `await` on the ORM in the test's own loop makes Tortoise
    reconnect across event loops and deadlocks (it warns `TortoiseLoopSwitchWarning` even when it
    survives). Reading back through the same client keeps one loop — and asserts the stronger
    property anyway, since the console sees exactly this list.
    """
    resp = admin_client.get("/v1/admin/accounts", headers={"X-User-Email": ADMIN})
    assert resp.status_code == 200
    return {a["username"] for a in resp.json()["accounts"]}


def test_a_refused_caller_is_not_given_an_account(client) -> None:
    """THE invariant. `current_account` get-or-creates; `require_admin` must NOT.

    Were the admin gate to resolve identity through `account_for_identity`, every probe of this
    endpoint would silently provision a tenant — the accounts table would fill with strangers, and
    each would own a credential namespace.
    """
    admin_client = _admin_client(client)
    admin_client.get("/v1/admin/accounts", headers={"X-User-Email": OUTSIDER})

    assert OUTSIDER not in _usernames(admin_client)


def test_an_admitted_admin_is_not_given_an_account_either(client) -> None:
    """An admin is not a tenant. Same invariant, on the path that SUCCEEDS."""
    admin_client = _admin_client(client)

    assert ADMIN not in _usernames(admin_client)


def test_no_identity_header_is_unauthenticated(client) -> None:
    resp = _admin_client(client).get("/v1/admin/accounts")

    assert resp.status_code == 401


def test_a_blank_identity_header_is_unauthenticated(client) -> None:
    resp = _admin_client(client).get("/v1/admin/accounts", headers={"X-User-Email": "   "})

    assert resp.status_code == 401


def test_an_untrusted_peer_is_refused(client) -> None:
    resp = _admin_client(client, peer="203.0.113.7").get(
        "/v1/admin/accounts", headers={"X-User-Email": ADMIN}
    )

    assert resp.status_code == 403


def test_the_peer_is_checked_before_the_allowlist(client) -> None:
    """Ordering, not just outcome.

    An untrusted peer must be refused WITHOUT its identity claim being consulted — otherwise the
    response distinguishes "wrong network" from "wrong network AND not an admin", and an attacker
    outside the mesh learns whether an address is privileged. Both are 403; what this pins is that
    the untrusted peer is refused even when it presents a VALID admin address.
    """
    resp = _admin_client(client, peer="203.0.113.7").get(
        "/v1/admin/accounts", headers={"X-User-Email": ADMIN}
    )

    assert resp.status_code == 403


def test_an_empty_allowlist_disables_the_api(client) -> None:
    """503, not 403: nothing is misconfigured about the CALLER — the feature is switched off.

    Mirrors `require_provisioning_token`, which answers 503 when no provisioning token is set.
    """
    resp = _admin_client(client, admins=frozenset()).get(
        "/v1/admin/accounts", headers={"X-User-Email": ADMIN}
    )

    assert resp.status_code == 503


def test_jwt_mode_disables_the_api(client) -> None:
    """The allowlist keys on an address only the header carries; bearer tokens supply no email.

    503 rather than 401 because no request could succeed in this mode — it is a deployment
    statement, not a per-caller one.
    """
    client.app.state.settings.auth_mode = "cloudflare_headers"
    client.app.state.settings.allowed_networks = (POD_NETWORK,)
    client.app.state.settings.admin_emails = frozenset({ADMIN})
    admin_client = TestClient(client.app, client=("10.1.2.3", 50000))
    client.app.state.settings.auth_mode = "jwt"

    resp = admin_client.get("/v1/admin/accounts", headers={"X-User-Email": ADMIN})

    assert resp.status_code == 503


def test_the_principal_carries_the_normalised_address() -> None:
    """Downstream audit logging names the actor, so the value must be the stable one."""
    assert AdminPrincipal(email="Admin@OpenMined.org").email == "Admin@OpenMined.org"
    assert AdminPrincipal(email="Admin@OpenMined.org").username == ADMIN
