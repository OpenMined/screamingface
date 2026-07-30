"""Who may reach ``/v1/admin`` — a second gate on top of Cloudflare Access identity.

`OME-684` made every caller who clears Cloudflare Access an ordinary `Account`. That is the right
default for the inference surface and exactly the wrong one for an administrative surface, where a
caller reads and mutates OTHER accounts' credentials. So administration is a SEPARATE authorization
decision layered on the same verified identity, keyed on :attr:`Settings.admin_emails`.

INVARIANT — an admin is not a tenant. Nothing here calls
:func:`aigateway.core.auth.cloudflare_identity.account_for_identity`, and nothing here writes to the
database at all. Resolving an admin through the account path would mean every probe of this endpoint
silently provisioned a tenant: the accounts table would fill with strangers, each owning a
credential namespace, and the admin's own address would appear in the very list the console renders.

INVARIANT — the peer network is checked BEFORE the identity header is read, exactly as
`_account_from_cloudflare_headers` does. The header is meaningful only from a caller the deployment
vouches for, so an untrusted peer is refused without its claim ever being consulted.

The trust model is inherited wholesale from `cloudflare_identity` and is a property of the NETWORK,
not of this module: it holds only while the port is unreachable except through Envoy. Nothing here
can detect otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from .cloudflare_identity import HEADER_USER_EMAIL, identity_from_headers, peer_in_networks

_API_DISABLED = (
    "The admin API is disabled: no administrator addresses are configured. Set "
    "AIGATEWAY_ADMIN_EMAILS to enable it."
)

_WRONG_MODE = (
    "The admin API requires AIGW_AUTH_MODE=cloudflare_headers: administrators are identified by "
    "the address Cloudflare Access verified, which no other mode supplies."
)

_UNTRUSTED_PEER = (
    "This gateway accepts header identity only from the networks it was configured to trust."
)

_NOT_AN_ADMIN = "This account is not an administrator of this gateway."


def email_is_admin(email: str, admin_emails: frozenset[str]) -> bool:
    """Whether ``email`` is on the allowlist.

    Case-folded on both sides — `Settings._parse_admin_emails` lowercases the allowlist and this
    lowercases the candidate — because mail domains are case-insensitive and an operator will
    eventually type a capital on one side but not the other.

    An empty allowlist admits nobody. That is a real state (the setting is unset by default), and
    the callers above turn it into a 503 rather than reaching here, but failing closed is the only
    safe answer if it is ever reached directly.
    """
    return email.strip().lower() in admin_emails


@dataclass(frozen=True, slots=True)
class AdminPrincipal:
    """One administrator, as Cloudflare verified them.

    Deliberately NOT an `Account`: it has no id, no credential namespace and no database row. It
    exists to name the actor in the audit log and to be a type the routes can require.
    """

    email: str

    @property
    def username(self) -> str:
        """The normalised address — what the allowlist and the audit log agree on."""
        return self.email.strip().lower()


async def require_admin(request: Request) -> AdminPrincipal:
    """Resolve the calling administrator, or refuse.

    The order of the checks is load-bearing, and each failure carries a DIFFERENT status because
    they mean different things to whoever is looking at the response:

    - **503** — the deployment has not enabled this API (no allowlist), or cannot support it (a
      mode that carries no address). Nothing about the caller is wrong. Mirrors
      `require_provisioning_token`, which answers 503 when no provisioning token is set.
    - **403 (peer)** — the caller is not entitled to be believed, and no credential they could
      present would change that. Checked first, so an untrusted peer never has its identity read.
    - **401** — no identity was presented.
    - **403 (allowlist)** — identified, and not an administrator.

    The messages name neither the peer, the trusted ranges, nor whether the address exists as an
    account, so a probe learns nothing about the topology or the tenant list.
    """
    settings = request.app.state.settings

    if not settings.admin_emails:
        raise HTTPException(status_code=503, detail=_API_DISABLED)

    # `disabled` mode is deliberately permitted: it is loopback-only, enforced by
    # AuthDisabledLocalOnlyMiddleware, and it is how the console is developed against a local
    # gateway. `jwt` mode is refused because a bearer token carries no address to match.
    if settings.auth_mode == "jwt":
        raise HTTPException(status_code=503, detail=_WRONG_MODE)
    if settings.auth_mode == "disabled":
        return AdminPrincipal(email=next(iter(sorted(settings.admin_emails))))

    if not peer_in_networks(
        request.client.host if request.client is not None else None,
        settings.allowed_networks,
    ):
        raise HTTPException(status_code=403, detail=_UNTRUSTED_PEER)

    identity = identity_from_headers(request.headers)
    if identity is None:
        raise HTTPException(
            status_code=401,
            detail=(
                f"Missing {HEADER_USER_EMAIL} — this gateway resolves the caller from the identity "
                "header the mesh gateway injects after verifying Cloudflare Access."
            ),
        )

    if not email_is_admin(identity.email, settings.admin_emails):
        raise HTTPException(status_code=403, detail=_NOT_AN_ADMIN)

    # NOTE the absence: no `account_for_identity`. See the module docstring.
    return AdminPrincipal(email=identity.email)


CurrentAdmin = Annotated[AdminPrincipal, Depends(require_admin)]
