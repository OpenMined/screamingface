"""In `cloudflare_headers` mode, only declared networks may present an identity header.

WHY this exists as a second boundary: the mode trusts `X-User-Email` because the mesh guarantees a
client cannot set it, and that guarantee is enforced by deployment configuration — no Ingress, plus
a NetworkPolicy. A NetworkPolicy only restricts traffic if the cluster's CNI enforces it; where it
does not, the object is decoration and the mode becomes an open impersonation endpoint. This check
holds regardless, because it runs in the process.

INVARIANT: the peer address is the TCP peer, never `X-Forwarded-For`. Trusting a forgeable header to
decide whether to trust a forgeable header is circular.
"""

from __future__ import annotations

from ipaddress import ip_network

import pytest
from fastapi.testclient import TestClient

from aigateway.config import Settings
from aigateway.core.auth.cloudflare_identity import peer_in_networks
from aigateway.main import create_app

EMAIL = "someone@openmined.org"
POD_NETWORK = ip_network("10.0.0.0/8")


def _settings(**values: object) -> Settings:
    """Build Settings from raw values, as the environment supplies them.

    `model_validate` rather than the constructor because `allowed_networks` arrives as a
    comma-separated STRING and is parsed into networks — which is the behaviour under test.
    """
    return Settings.model_validate(values)


# --- parsing the setting ---------------------------------------------------------------------


def test_a_comma_separated_list_becomes_networks() -> None:
    settings = _settings(auth_mode="jwt", allowed_networks="10.0.0.0/8,192.168.0.0/16")

    assert settings.allowed_networks == (ip_network("10.0.0.0/8"), ip_network("192.168.0.0/16"))


def test_surrounding_whitespace_is_tolerated() -> None:
    """Operators write these across YAML lines; a stray space must not become a parse error."""
    settings = _settings(auth_mode="jwt", allowed_networks=" 10.0.0.0/8 , 172.16.0.0/12 ")

    assert settings.allowed_networks == (ip_network("10.0.0.0/8"), ip_network("172.16.0.0/12"))


def test_a_single_entry_needs_no_comma() -> None:
    assert _settings(auth_mode="jwt", allowed_networks="10.0.0.0/8").allowed_networks == (
        POD_NETWORK,
    )


def test_an_ipv6_network_is_accepted() -> None:
    settings = _settings(auth_mode="jwt", allowed_networks="fd00::/8")

    assert settings.allowed_networks == (ip_network("fd00::/8"),)


def test_an_empty_value_is_no_networks() -> None:
    assert _settings(auth_mode="jwt", allowed_networks="").allowed_networks == ()


def test_a_network_with_host_bits_set_is_refused() -> None:
    """`192.168.0.0/8` is not a network — and it is exactly the value the PR review proposed.

    Refused rather than silently coerced: `strict=False` would widen it to `192.0.0.0/8`, which
    admits 16 million addresses the operator never meant to trust.
    """
    with pytest.raises(ValueError, match="host bits"):
        _settings(auth_mode="jwt", allowed_networks="192.168.0.0/8")


# --- the setting is mandatory in header mode -------------------------------------------------


def test_header_mode_without_networks_refuses_to_start() -> None:
    """The gateway cannot trust the header without knowing who is allowed to present it.

    Enforced at app construction rather than on `Settings`, so that building settings stays a
    pure parse — `main.py` binds `app = create_app()` at import, so a deployment missing this
    still fails at startup rather than serving every reachable caller.
    """
    with pytest.raises(ValueError, match="AIGW_ALLOWED_NETWORKS"):
        create_app(_settings(auth_mode="cloudflare_headers"))


def test_header_mode_with_networks_starts() -> None:
    settings = _settings(auth_mode="cloudflare_headers", allowed_networks="10.0.0.0/8")

    assert settings.allowed_networks == (POD_NETWORK,)
    assert create_app(settings).state.settings.auth_mode == "cloudflare_headers"


def test_jwt_mode_starts_without_networks() -> None:
    """`jwt` authenticates the caller itself, so it stays reachable from anywhere."""
    assert create_app(_settings(auth_mode="jwt")).state.settings.allowed_networks == ()


def test_disabled_mode_starts_without_networks() -> None:
    assert create_app(_settings(auth_mode="disabled")).state.settings.allowed_networks == ()


def test_the_legacy_flag_alone_still_starts_without_networks() -> None:
    """INVARIANT: the mode may be DERIVED from `AIGATEWAY_AUTH_ENABLED`.

    A deployment that sets only the legacy flag never asked for header mode, so it must not be
    made to declare networks. This pins that the requirement is read from the RECONCILED mode.
    """
    app = create_app(_settings(auth_enabled=False))

    assert app.state.settings.auth_mode == "disabled"


# --- matching a peer against them -------------------------------------------------------------


def test_a_peer_inside_a_declared_network_is_trusted() -> None:
    assert peer_in_networks("10.1.2.3", (POD_NETWORK,)) is True


def test_a_peer_outside_every_declared_network_is_not() -> None:
    assert peer_in_networks("203.0.113.7", (POD_NETWORK,)) is False


def test_no_peer_at_all_is_not_trusted() -> None:
    """`request.client` is None for some transports; absent evidence is not evidence."""
    assert peer_in_networks(None, (POD_NETWORK,)) is False


def test_a_peer_that_is_not_an_address_is_not_trusted() -> None:
    assert peer_in_networks("testclient", (POD_NETWORK,)) is False


def test_no_declared_networks_trusts_nobody() -> None:
    """Fail CLOSED. Reachable only if the startup check is bypassed, and then it must deny."""
    assert peer_in_networks("10.1.2.3", ()) is False


def test_an_ipv4_mapped_ipv6_peer_matches_its_ipv4_network() -> None:
    """A dual-stack cluster reports `::ffff:10.1.2.3`; failing closed there would be an outage."""
    assert peer_in_networks("::ffff:10.1.2.3", (POD_NETWORK,)) is True


def test_an_ipv6_peer_does_not_match_an_ipv4_network() -> None:
    assert peer_in_networks("fd00::1", (POD_NETWORK,)) is False


# --- through the app --------------------------------------------------------------------------


def _header_mode_client(client, peer: str) -> TestClient:
    """The built app in header mode, addressed from `peer`.

    A fresh `TestClient` over the SAME app rather than the shared fixture: the peer address is fixed
    at construction, and it is the subject here. No context manager — the outer `client` fixture
    already ran the lifespan that initialized the database.
    """
    client.app.state.settings.auth_mode = "cloudflare_headers"
    client.app.state.settings.allowed_networks = (POD_NETWORK,)
    return TestClient(client.app, client=(peer, 50000))


def test_a_caller_from_a_declared_network_is_resolved(client) -> None:
    resp = _header_mode_client(client, "10.1.2.3").get(
        "/v1/auth/me", headers={"X-User-Email": EMAIL}
    )

    assert resp.status_code == 200
    assert resp.json()["username"] == EMAIL


def test_a_caller_from_outside_is_refused(client) -> None:
    resp = _header_mode_client(client, "203.0.113.7").get(
        "/v1/auth/me", headers={"X-User-Email": EMAIL}
    )

    assert resp.status_code == 403


def test_the_refusal_does_not_name_the_networks_it_checked(client) -> None:
    """A rejected caller learns that they are not trusted, not the shape of the trusted range."""
    resp = _header_mode_client(client, "203.0.113.7").get(
        "/v1/auth/me", headers={"X-User-Email": EMAIL}
    )

    assert "10.0.0.0/8" not in resp.text


def test_a_forwarded_for_header_cannot_buy_trust(client) -> None:
    """THE invariant. `X-Forwarded-For` is as forgeable as `X-User-Email`, so it is never read.

    This test is what stops a later "fix" for a proxied deployment from reopening the hole: any
    such deployment must declare the proxy's own address instead.
    """
    resp = _header_mode_client(client, "203.0.113.7").get(
        "/v1/auth/me",
        headers={"X-User-Email": EMAIL, "X-Forwarded-For": "10.1.2.3"},
    )

    assert resp.status_code == 403


def test_the_network_is_checked_before_the_identity_header_is_read(client) -> None:
    """An untrusted caller gets 403, not the 401 that would tell them which header to forge."""
    resp = _header_mode_client(client, "203.0.113.7").get("/v1/auth/me")

    assert resp.status_code == 403


def test_jwt_mode_is_not_restricted_by_the_networks(client) -> None:
    """Confirms the guard is scoped to the mode that needs it, not applied gateway-wide."""
    client.app.state.settings.allowed_networks = (POD_NETWORK,)
    resp = TestClient(client.app, client=("203.0.113.7", 50000)).get("/v1/models")

    # 401 (no token) rather than 403 (wrong network) — jwt mode never consults the networks.
    assert resp.status_code == 401
