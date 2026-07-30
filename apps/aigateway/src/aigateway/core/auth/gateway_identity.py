"""Resolving the caller from the gateway-identity headers Envoy injects.

https://pulse.dev.openmined.org/docs/products/gateway-identity-flow/ — Envoy verifies the caller's
token, clears every one of these headers off the inbound request, and re-injects them from the
verified claims. A client therefore cannot forge them, and the gateway needs no token parsing of
its own: who-is-calling is already plain, trustworthy HTTP.

INVARIANT: that trust is a property of the NETWORK, not of this module. It holds only while
aigateway is unreachable except through Envoy (plus the Runner Pods that carry identity forward).
Expose this port publicly in `gateway_headers` mode and anyone can claim any identity by setting a
header. Nothing here can detect that, which is why the mode is opt-in rather than the default.

The account this produces is an ordinary `Account` row, so everything downstream — profiles,
`credential_blobs`, the request cache — keeps working unchanged.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Literal

from tortoise.exceptions import IntegrityError

from .models import Account, BaseAccount

HEADER_TENANT = "X-Tenant"
HEADER_USER_ID = "X-User-Id"
HEADER_USER_EMAIL = "X-User-Email"
HEADER_SERVICE_ID = "X-Service-Id"

IDENTITY_HEADERS = (HEADER_TENANT, HEADER_USER_ID, HEADER_USER_EMAIL, HEADER_SERVICE_ID)

_ACCOUNT_NAMESPACE = uuid.UUID("6f9d9c2e-8d3a-5b47-9a1e-3c7f2b6d4a10")
"""Fixed namespace for the UUIDv5 account ids derived below. NEVER change it.

`credential_blobs` and `oauth_connections` are keyed on the account id, so a new namespace would
silently orphan every stored credential for every header-derived account — they would still exist,
just belong to an account nobody resolves to anymore.
"""

_USERNAME_PREFIX = "gw:"
"""Namespaces derived usernames away from local ones (`admin`, `anonymous`), which are chosen by a
human and must never collide with a derived one."""

_USERNAME_DIGEST_LEN = 32

SubjectKind = Literal["user", "service"]


@dataclass(frozen=True, slots=True)
class GatewayIdentity:
    """One caller, as the identity headers describe them.

    ``subject`` is whichever claim identifies them most stably; ``kind`` records which, so a user
    and a service that happened to share a subject string can never collapse into one account.
    """

    tenant: str
    kind: SubjectKind
    subject: str
    email: str | None = None

    @property
    def account_id(self) -> uuid.UUID:
        """The account's primary key — derived, not allocated.

        Deterministic so the SAME caller maps to the SAME id on every request, in every process,
        without a lookup being the source of truth. That is what keeps their stored credentials
        reachable across restarts and replicas.
        """
        return uuid.uuid5(_ACCOUNT_NAMESPACE, self._key)

    @property
    def username(self) -> str:
        """A bounded, deterministic username.

        `Account.username` is `max_length=64` and unique, and an email plus a tenant can exceed
        that, so the identity is hashed rather than spelled out. The readable form lives in
        `display_name` (max 255), which is what an operator actually reads.
        """
        digest = hashlib.sha256(self._key.encode("utf-8")).hexdigest()[:_USERNAME_DIGEST_LEN]
        return f"{_USERNAME_PREFIX}{digest}"

    @property
    def display_name(self) -> str:
        """The human-readable identity, for operators reading the accounts table."""
        return f"{self.email or self.subject} ({self.tenant})"

    @property
    def _key(self) -> str:
        # NUL-separated so no combination of values can be reinterpreted as another: with a plain
        # ":" join, tenant "a:b" + subject "c" and tenant "a" + subject "b:c" would collide, which
        # would hand one tenant's caller another tenant's account.
        return f"{self.tenant}\0{self.kind}\0{self.subject}"


def identity_from_headers(headers) -> GatewayIdentity | None:  # noqa: ANN001 - any case-insensitive mapping
    """Build the caller's identity, or ``None`` when the headers carry none.

    ``None`` means "no identity present", NOT "anonymous" — the caller decides what to do with
    that, and in `gateway_headers` mode the only safe answer is 401.

    A tenant is mandatory: it is the namespace every subject is scoped under, and the flow always
    injects it. Without one, two tenants' callers with the same subject would share an account, so
    a missing tenant fails closed rather than defaulting.
    """
    tenant = _clean(headers.get(HEADER_TENANT))
    if tenant is None:
        return None

    email = _clean(headers.get(HEADER_USER_EMAIL))
    # Precedence follows stability, not convenience. `X-User-Id` is the token's `sub` and survives
    # an address change; an email is the fallback identifier only when no id was issued. A service
    # token carries neither, which is exactly what distinguishes automation from a human.
    if (user_id := _clean(headers.get(HEADER_USER_ID))) is not None:
        return GatewayIdentity(tenant=tenant, kind="user", subject=user_id, email=email)
    if email is not None:
        # Lowercased for the KEY only: mail domains are case-insensitive, and letting `A@x.test`
        # and `a@x.test` resolve to two accounts would split one person's credentials in two.
        return GatewayIdentity(tenant=tenant, kind="user", subject=email.lower(), email=email)
    if (service_id := _clean(headers.get(HEADER_SERVICE_ID))) is not None:
        return GatewayIdentity(tenant=tenant, kind="service", subject=service_id)
    return None


def _clean(value: str | None) -> str | None:
    """A header's usable value, or ``None`` — blank is absent, never an identity of its own."""
    if value is None:
        return None
    return stripped if (stripped := value.strip()) else None


async def account_for_identity(identity: GatewayIdentity) -> BaseAccount | None:
    """Get-or-create the account for ``identity``; ``None`` if it exists but is deactivated.

    Deactivation is honored rather than overwritten: an operator disabling a derived account must
    lock the caller out, so this never reactivates or recreates one. It returns ``None`` instead of
    raising so the HTTP concern stays in the middleware.
    """
    account = await Account.get_or_none(id=identity.account_id)
    if account is None:
        account = await _create(identity)
    return account if account.is_active else None


async def _create(identity: GatewayIdentity) -> BaseAccount:
    """Insert the derived account, tolerating a concurrent inserter.

    Two requests from the same new caller race here, and the loser's INSERT violates the primary
    key or the unique username. Both are the same benign outcome — the row now exists — so the
    loser re-reads it instead of failing a request that did nothing wrong.
    """
    try:
        return await Account.create(
            id=identity.account_id,
            username=identity.username,
            # No password login: this account is only ever reachable by presenting the verified
            # headers. An empty hash cannot match any candidate password.
            password_hash="",
            display_name=identity.display_name,
            is_active=True,
        )
    except IntegrityError:
        existing = await Account.get_or_none(id=identity.account_id)
        if existing is None:  # pragma: no cover - the racer's row is committed by definition
            raise
        return existing
