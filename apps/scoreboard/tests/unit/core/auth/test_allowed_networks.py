"""In `cloudflare_headers` mode, only declared networks may present an identity header.

WHY this exists as a second boundary: the mode trusts `X-User-Email` because the mesh guarantees
a client cannot set it, and that guarantee is enforced by deployment configuration — no direct
Ingress, plus a NetworkPolicy. This check holds regardless, because it runs in the process.
Mirrors apps/aigateway/tests/unit/auth/test_allowed_networks.py's parsing/peer-matching sections;
the HTTP-level "through the app" cases live in test_scores_routes.py instead.

INVARIANT: the peer address is the TCP peer, never `X-Forwarded-For`. Trusting a forgeable header
to decide whether to trust a forgeable header is circular.
"""

from __future__ import annotations

from ipaddress import ip_address, ip_network

import pytest

from scoreboard.config import Settings
from scoreboard.core.auth.cloudflare_identity import peer_in_networks
from scoreboard.main import create_app

POD_NETWORK = ip_network("10.0.0.0/8")


def _settings(**values: object) -> Settings:
    """Build Settings from raw values, as the environment supplies them.

    `model_validate` rather than the constructor because `allowed_networks` arrives as a
    comma-separated STRING and is parsed into networks — which is the behaviour under test.
    """
    return Settings.model_validate(values)


# --- parsing the setting ---------------------------------------------------------------------


def test_a_comma_separated_list_becomes_networks() -> None:
    settings = _settings(allowed_networks="10.0.0.0/8,192.168.0.0/16")

    assert settings.allowed_networks == (ip_network("10.0.0.0/8"), ip_network("192.168.0.0/16"))


def test_surrounding_whitespace_is_tolerated() -> None:
    settings = _settings(allowed_networks=" 10.0.0.0/8 , 172.16.0.0/12 ")

    assert settings.allowed_networks == (ip_network("10.0.0.0/8"), ip_network("172.16.0.0/12"))


def test_an_empty_value_is_no_networks() -> None:
    assert _settings(allowed_networks="").allowed_networks == ()


def test_a_network_with_host_bits_set_is_refused() -> None:
    """Refused rather than silently widened: `strict=False` would let in far more than declared."""
    with pytest.raises(ValueError, match="host bits"):
        _settings(allowed_networks="192.168.0.0/8")


# --- the setting is mandatory in header mode -------------------------------------------------


def test_header_mode_without_networks_refuses_to_start() -> None:
    with pytest.raises(ValueError, match="SCOREBOARD_ALLOWED_NETWORKS"):
        create_app(_settings(auth_mode="cloudflare_headers"))


def test_header_mode_with_networks_starts() -> None:
    settings = _settings(auth_mode="cloudflare_headers", allowed_networks="10.0.0.0/8")

    assert create_app(settings).state.settings.auth_mode == "cloudflare_headers"


# --- FORWARDED_ALLOW_IPS="*" defeats the peer check, so header mode refuses it too -----------


def test_header_mode_refuses_to_start_with_wildcard_forwarded_allow_ips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """uvicorn's ProxyHeadersMiddleware trusts a client-supplied X-Forwarded-For from ANY
    peer when FORWARDED_ALLOW_IPS="*", overwriting request.client.host before
    peer_in_networks() ever sees it — the exact value apps/scoreboard's chart sets by
    default for its (unrelated) Traefik-fronted deployment. Combined with cloudflare_headers
    mode, that's a full identity-spoofing bypass; confirmed by live reproduction against the
    actual entrypoint during self-review.
    """
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "*")

    with pytest.raises(ValueError, match="FORWARDED_ALLOW_IPS"):
        create_app(_settings(auth_mode="cloudflare_headers", allowed_networks="10.0.0.0/8"))


def test_header_mode_starts_with_scoped_forwarded_allow_ips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # WHY 203.0.113.5, not 10.0.0.5: it must be genuinely disjoint from allowed_networks
    # below, or this "scoped/safe" case is actually the overlap bug the next section covers.
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "203.0.113.5")
    settings = _settings(auth_mode="cloudflare_headers", allowed_networks="10.0.0.0/8")

    assert create_app(settings).state.settings.auth_mode == "cloudflare_headers"


def test_header_mode_starts_with_unset_forwarded_allow_ips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """uvicorn's own default (127.0.0.1, not "*") is safe, so an unset env var must not
    trip the guard — only an explicit wildcard should."""
    monkeypatch.delenv("FORWARDED_ALLOW_IPS", raising=False)
    settings = _settings(auth_mode="cloudflare_headers", allowed_networks="10.0.0.0/8")

    assert create_app(settings).state.settings.auth_mode == "cloudflare_headers"


# --- FORWARDED_ALLOW_IPS overlapping allowed_networks defeats the peer check too -------------
#
# WHY this is a separate guard from the "*" check above: scoping FORWARDED_ALLOW_IPS away from
# "*" is not enough on its own. uvicorn's ProxyHeadersMiddleware still overwrites
# request.client.host from a client-supplied X-Forwarded-For whenever the real peer falls
# inside FORWARDED_ALLOW_IPS — even a single, deliberately narrow address. If that address also
# falls inside allowed_networks, the exact peers the check exists to authenticate are the ones
# it can no longer see correctly (found in external review of this PR).


def test_header_mode_refuses_to_start_with_bare_ip_forwarded_allow_ips_inside_allowed_networks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "10.0.0.5")

    with pytest.raises(ValueError, match="overlaps"):
        create_app(_settings(auth_mode="cloudflare_headers", allowed_networks="10.0.0.0/8"))


def test_header_mode_refuses_to_start_with_forwarded_allow_ips_cidr_overlapping_allowed_networks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "10.0.0.0/16")

    with pytest.raises(ValueError, match="overlaps"):
        create_app(_settings(auth_mode="cloudflare_headers", allowed_networks="10.0.0.0/8"))


def test_header_mode_starts_with_forwarded_allow_ips_cidr_disjoint_from_allowed_networks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard: a genuinely disjoint FORWARDED_ALLOW_IPS must not trip the overlap
    check."""
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "192.0.2.0/24")
    settings = _settings(auth_mode="cloudflare_headers", allowed_networks="10.0.0.0/8")

    assert create_app(settings).state.settings.auth_mode == "cloudflare_headers"


def test_header_mode_starts_with_ipv6_forwarded_allow_ips_against_ipv4_only_allowed_networks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An IPv6 FORWARDED_ALLOW_IPS entry must never be treated as overlapping an IPv4-only
    allowed_networks — ipaddress itself refuses cross-version containment, but the new guard's
    own comparison must not crash or false-positive on a version mismatch either."""
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "fd00::1")
    settings = _settings(auth_mode="cloudflare_headers", allowed_networks="10.0.0.0/8")

    assert create_app(settings).state.settings.auth_mode == "cloudflare_headers"


def test_header_mode_refuses_to_start_when_one_entry_in_a_mixed_forwarded_allow_ips_list_overlaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proves the guard classifies FORWARDED_ALLOW_IPS per entry, not as one opaque string — a
    non-overlapping IPv6 entry must not mask a real overlapping IPv4 entry in the same list."""
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "fd00::1,10.0.0.5")

    with pytest.raises(ValueError, match="overlaps"):
        create_app(_settings(auth_mode="cloudflare_headers", allowed_networks="10.0.0.0/8"))


def test_header_mode_refuses_to_start_with_pure_ipv6_forwarded_allow_ips_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A same-version IPv6-vs-IPv6 overlap must be caught too — the IPv4/IPv6 cross-version
    tests above only prove the guard doesn't false-positive across versions; this proves it
    doesn't false-negative within a single version either."""
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "fd00::/16")

    with pytest.raises(ValueError, match="overlaps"):
        create_app(_settings(auth_mode="cloudflare_headers", allowed_networks="fd00::/8"))


def test_header_mode_refuses_to_start_with_ipv4_mapped_ipv6_forwarded_allow_ips_overlap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An operator naming the same real peer in IPv4-mapped-IPv6 form (how a dual-stack
    cluster's own tooling may report it) must overlap allowed_networks the same way the plain
    IPv4 form would — found in follow-up review of this guard."""
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "::ffff:10.0.0.5")

    with pytest.raises(ValueError, match="overlaps"):
        create_app(_settings(auth_mode="cloudflare_headers", allowed_networks="10.0.0.0/8"))


def test_disabled_mode_starts_with_wildcard_forwarded_allow_ips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Confirms the guard is scoped to the mode that needs it — disabled mode never reads
    request.client.host for anything security-sensitive, so "*" is fine there (and is in
    fact today's default for the Traefik-fronted deployment)."""
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "*")

    assert create_app(_settings()).state.settings.auth_mode == "disabled"


def test_disabled_mode_starts_without_networks() -> None:
    assert create_app(_settings()).state.settings.auth_mode == "disabled"


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


# --- pinning the uvicorn behavior main.py's FORWARDED_ALLOW_IPS guard assumes ------------------


def test_uvicorn_treats_bare_wildcard_as_always_trust() -> None:
    """`main.py::create_app`'s `forwarded_allow_ips == "*"` check assumes uvicorn's own
    `_TrustedHosts` treats a bare "*" as "trust every peer" — an UNDOCUMENTED, private
    implementation detail (`_TrustedHosts.always_trust`), not part of uvicorn's public
    contract. Pinned directly against the installed version so a future `uv lock --upgrade`
    that changes this fails HERE, loudly, rather than silently reopening the
    FORWARDED_ALLOW_IPS bypass this guard exists to close.
    """
    from uvicorn.middleware.proxy_headers import _TrustedHosts

    assert _TrustedHosts("*").always_trust is True


def test_uvicorn_does_not_treat_a_wildcard_inside_a_list_as_always_trust() -> None:
    """Confirms main.py's exact-string check isn't too narrow: a comma-list CONTAINING "*"
    (e.g. "127.0.0.1,*") is NOT equivalent to a bare "*" in the installed uvicorn — it only
    matches a client whose address literally equals the string "*", never a real peer. If
    this ever flipped (any-entry-is-"*" trusts everyone), main.py's guard would need to
    parse the list instead of comparing the raw string.
    """
    from uvicorn.middleware.proxy_headers import _TrustedHosts

    assert _TrustedHosts(["127.0.0.1", "*"]).always_trust is False


def test_uvicorn_parses_a_cidr_forwarded_allow_ips_entry_into_trusted_networks() -> None:
    """main.py's overlap guard mirrors this classification independently — it can't import a
    private class to do its own parsing — so this pins the real behavior it assumes: a `/`
    entry becomes a real ipaddress network, not a string literal. A future `uv lock --upgrade`
    that changes this fails HERE rather than silently invalidating the overlap guard.
    """
    from uvicorn.middleware.proxy_headers import _TrustedHosts

    assert _TrustedHosts("10.0.0.0/8").trusted_networks == {ip_network("10.0.0.0/8")}


def test_uvicorn_parses_a_bare_ip_forwarded_allow_ips_entry_into_trusted_hosts() -> None:
    from uvicorn.middleware.proxy_headers import _TrustedHosts

    assert _TrustedHosts("10.0.0.5").trusted_hosts == {ip_address("10.0.0.5")}
