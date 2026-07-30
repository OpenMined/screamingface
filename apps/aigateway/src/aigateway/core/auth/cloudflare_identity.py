"""Resolving the caller from the identity header the mesh gateway injects.

https://pulse.dev.openmined.org/docs/products/gateway-identity-flow/ — Cloudflare Access
authenticates the caller at the edge and issues a signed assertion; the request reaches the cluster
through a `cloudflared` tunnel, where Envoy **re-verifies that assertion against Cloudflare's JWKS**
and translates the verified claims into plain HTTP headers. Envoy also clears any client-supplied
copy of those headers first, so a caller cannot forge one.

The gateway therefore does no token work of its own: identity arrives as `X-User-Email`, already
verified. (An earlier design had aigateway verify the Cloudflare JWT itself, JWKS fetching and all —
that moved to Envoy, which is why none of it lives here.)

INVARIANT: the trust is a property of the NETWORK, not of this module. It holds only while
aigateway is unreachable except through that chain. Expose this port directly and anyone can claim
any identity with one header. Nothing here can detect that, so the mode is opt-in, not default.

The account this produces is an ordinary `Account` row, so everything downstream — profiles,
`credential_blobs`, the request cache — keeps working unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Account, BaseAccount

HEADER_USER_EMAIL = "X-User-Email"
"""The one identity header this gateway reads.

Deliberately the only one. The flow also carries a tenant and, for automation, a Cloudflare service
token's `common_name` — both dropped here: the email is globally unique, so a tenant adds nothing to
a key built from it, and service-token callers are out of scope until the gateway issues its own API
keys for them. A caller presenting no email is rejected rather than guessed at.
"""


@dataclass(frozen=True, slots=True)
class CloudflareIdentity:
    """One caller, as Cloudflare verified them: a single verified email address."""

    email: str

    @property
    def username(self) -> str:
        """The account's unique key.

        `Account.username` is unique, so it IS the identity key — no separate derivation, and no
        second source of truth to keep in step. Lowercased because mail domains are
        case-insensitive: letting `A@x.test` and `a@x.test` become two accounts would split one
        person's stored credentials in two.
        """
        return self.email.strip().lower()

    @property
    def display_name(self) -> str:
        """What an operator reads in the accounts table — the address as it actually arrived."""
        return self.email.strip()


def identity_from_headers(headers) -> CloudflareIdentity | None:  # noqa: ANN001 - any case-insensitive mapping
    """Build the caller's identity, or ``None`` when the header carries none.

    ``headers`` must look up case-insensitively (Starlette's ``Headers`` does); header names are
    case-insensitive on the wire.

    ``None`` means "no identity present", NOT "anonymous" — the caller decides what to do with that,
    and in `cloudflare_headers` mode the only safe answer is 401. A present-but-blank header counts
    as absent: it carries no identity, and treating it as one would let a reader conclude a caller
    was authenticated when nothing said so.
    """
    email = (headers.get(HEADER_USER_EMAIL) or "").strip()
    return CloudflareIdentity(email=email) if email else None


async def account_for_identity(identity: CloudflareIdentity) -> BaseAccount | None:
    """Get-or-create the account for ``identity``; ``None`` if it exists but is deactivated.

    `Account.get_or_create` is the framework's own primitive and already handles the race this path
    actually sees — two concurrent first requests from one caller, which is the NORMAL case for an
    SDK with a connection pool, not an edge case. Tortoise creates inside a transaction and
    re-fetches on `IntegrityError`, so the loser of the race gets the winner's row rather than a
    failed request.

    Deactivation is honored rather than overwritten: an operator disabling an account must lock the
    caller out, so this never reactivates one. It returns ``None`` instead of raising so the HTTP
    concern stays in the middleware.
    """
    account, _created = await Account.get_or_create(
        username=identity.username,
        defaults={
            # No password login: this account is only ever reachable by presenting the verified
            # header. An empty hash cannot match any candidate password.
            "password_hash": "",
            "display_name": identity.display_name,
            "is_active": True,
        },
    )
    return account if account.is_active else None
