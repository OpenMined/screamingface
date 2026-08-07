"""Resolving the submitter from the identity header the mesh gateway injects.

https://pulse.dev.openmined.org/docs/products/gateway-identity-flow/ — Cloudflare Access
authenticates the caller at the edge and issues a signed assertion; the request reaches the
cluster through a `cloudflared` tunnel, where Envoy **re-verifies that assertion against
Cloudflare's JWKS** and translates the verified claims into plain HTTP headers. Envoy also clears
any client-supplied copy of those headers first, so a caller cannot forge one.

This service therefore does no token work of its own: identity arrives as `X-User-Email`, already
verified. Mirrors `apps/aigateway/src/aigateway/core/auth/cloudflare_identity.py`, simplified —
scoreboard has no accounts table, so the submitter is stored as a plain string, not looked up
against an `Account` model.

INVARIANT: the trust is a property of the NETWORK, not of this module. It holds only while this
service is unreachable except through that chain. Expose this port directly and anyone can claim
any identity with one header — see `peer_in_networks`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from ipaddress import IPv4Network, IPv6Address, IPv6Network, ip_address

HEADER_USER_EMAIL = "X-User-Email"
"""The one identity header this service reads.

A caller presenting no email is rejected rather than guessed at — see `identity_from_headers`.
"""


def peer_in_networks(host: str | None, networks: Sequence[IPv4Network | IPv6Network]) -> bool:
    """Whether the connecting peer falls inside one of ``networks``.

    ``host`` is the TCP peer (`request.client.host`).

    INVARIANT: never `X-Forwarded-For`, and never any other header. This check exists because
    `X-User-Email` is forgeable by anyone who can reach the port; deciding whether to trust it
    from a second header that is forgeable in exactly the same way would be circular. A
    deployment behind a proxy must declare the PROXY's address here.

    Fails closed on every uncertainty: no peer, an unparseable peer, or no declared networks all
    return False.
    """
    if host is None or not networks:
        return False
    try:
        peer = ip_address(host)
    except ValueError:
        return False
    # A dual-stack cluster reports an IPv4 peer as `::ffff:10.1.2.3`. Comparing that against an
    # IPv4 network returns False (`__contains__` short-circuits on version), so without this the
    # service would refuse every legitimate caller on such a cluster.
    if isinstance(peer, IPv6Address) and peer.ipv4_mapped is not None:
        peer = peer.ipv4_mapped
    return any(peer in network for network in networks)


def identity_from_headers(headers: Mapping[str, str]) -> str | None:
    """The caller's verified email, or ``None`` when the header carries none.

    ``headers`` must look up case-insensitively (Starlette's ``Headers`` does); header names are
    case-insensitive on the wire.

    ``None`` means "no identity present", NOT "anonymous" — the caller decides what to do with
    that. A present-but-blank header counts as absent: it carries no identity, and treating it as
    one would let a reader conclude a caller was authenticated when nothing said so.
    """
    email = (headers.get(HEADER_USER_EMAIL) or "").strip()
    return email or None
