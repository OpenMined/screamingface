"""Cloudflare Access assertion verification and claim mapping."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import jwt

from .jwks import CloudflareAccessJwks

#: The IdP namespace stored in `accounts.external_idp`.
CF_ACCESS_IDP = "cf_access"

#: Cloudflare signs with RS256 only. Pinning it here (rather than accepting
#: whatever the token's header claims) is what prevents algorithm-confusion —
#: notably an attacker re-signing a payload with HS256 using the public cert as
#: the HMAC key.
_ALGORITHMS = ["RS256"]

#: `accounts.username` column width.
_USERNAME_MAX_LENGTH = 64


class CfAccessVerificationError(Exception):
    """The assertion is not a valid, current token for this application."""


@dataclass(frozen=True, slots=True)
class CfAccessIdentity:
    """The identity an assertion asserts."""

    subject: str
    email: str | None
    is_service_token: bool

    @property
    def username(self) -> str:
        """A stable `accounts.username` derived from the SUBJECT.

        INVARIANT: derived from `subject`, never from `email`. `username` is
        UNIQUE, so deriving it from a mutable, reassignable email means two
        distinct subjects that ever share an address collide and the second user
        cannot be provisioned at all — reintroducing, through the back door, the
        very email-as-identity coupling this module rejects. The email is carried
        on `display_name`/`email` for humans instead.

        Long subjects are hashed rather than truncated: `username` caps at 64
        chars and a raw truncation could map two distinct subjects onto one name.
        """
        candidate = f"{CF_ACCESS_IDP}:{self.subject}"
        if len(candidate) <= _USERNAME_MAX_LENGTH:
            return candidate
        digest = hashlib.sha256(self.subject.encode("utf-8")).hexdigest()
        return f"{CF_ACCESS_IDP}:{digest}"[:_USERNAME_MAX_LENGTH]


def identity_from_claims(claims: dict) -> CfAccessIdentity:
    """Map verified claims onto an identity.

    INVARIANT: the identity key is `sub` (a stable Access user UUID) or, for
    service tokens, `common_name` (the client ID). NEVER email — email is
    mutable at the IdP and can be reassigned to a different human, so keying on
    it would silently hand one person another's account.

    AIDEV-NOTE: the service-token claim shape (empty `sub`, no `email`,
    `common_name` set) is asserted here but is NOT documented on Cloudflare's
    JWT-validation page. Confirm against a real service-token assertion before
    relying on it in production; see the OME-591 spec's open-verification item.
    """
    subject = claims.get("sub") or ""
    common_name = claims.get("common_name") or ""

    if subject:
        email = claims.get("email")
        return CfAccessIdentity(
            subject=subject,
            email=email if isinstance(email, str) and email else None,
            is_service_token=False,
        )
    if common_name:
        return CfAccessIdentity(subject=common_name, email=None, is_service_token=True)
    raise CfAccessVerificationError("assertion carries neither 'sub' nor 'common_name'")


class CfAccessVerifier:
    """Verifies an assertion against the team's published keys."""

    def __init__(self, jwks: CloudflareAccessJwks, *, audience: str, team_domain: str) -> None:
        self._jwks = jwks
        self._audience = audience
        self._issuer = f"https://{team_domain}"

    async def verify(self, token: str) -> CfAccessIdentity:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError as exc:
            raise CfAccessVerificationError(f"unreadable token header: {exc}") from exc

        kid = header.get("kid")
        if not isinstance(kid, str) or not kid:
            raise CfAccessVerificationError("token header carries no 'kid'")

        try:
            key = await self._jwks.get_key(kid)
        except Exception as exc:
            raise CfAccessVerificationError(f"no usable signing key: {exc}") from exc

        try:
            claims = jwt.decode(
                token,
                key=key,
                algorithms=_ALGORITHMS,
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "aud", "iss"]},
            )
        except jwt.InvalidTokenError as exc:
            raise CfAccessVerificationError(f"assertion rejected: {exc}") from exc

        return identity_from_claims(claims)
