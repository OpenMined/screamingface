"""Cloudflare Access federated authentication (OME-591).

Adapter package: implements the `IdentityResolver` port for identities asserted
by Cloudflare Access. Core imports the port, never this package — `main.py`
registers the resolver when the feature is configured.
"""

from __future__ import annotations

from .identity import (
    CF_ACCESS_IDP,
    CfAccessIdentity,
    CfAccessVerificationError,
    CfAccessVerifier,
)
from .jwks import CloudflareAccessJwks, JwksUnavailableError
from .provisioning import get_or_create_cf_access_account
from .resolver import ASSERTION_COOKIE, ASSERTION_HEADER, CfAccessResolver

__all__ = [
    "ASSERTION_COOKIE",
    "ASSERTION_HEADER",
    "CF_ACCESS_IDP",
    "CfAccessIdentity",
    "CfAccessResolver",
    "CfAccessVerificationError",
    "CfAccessVerifier",
    "CloudflareAccessJwks",
    "JwksUnavailableError",
    "build_cf_access_resolver",
    "get_or_create_cf_access_account",
]


def build_cf_access_resolver(
    *,
    team_domain: str,
    audience: str,
    admin_emails: frozenset[str] = frozenset(),
    http_client_factory=None,
) -> CfAccessResolver:
    """Assemble the resolver from settings."""
    jwks = CloudflareAccessJwks(team_domain, http_client_factory=http_client_factory)
    verifier = CfAccessVerifier(jwks, audience=audience, team_domain=team_domain)
    return CfAccessResolver(verifier, admin_emails=admin_emails)
