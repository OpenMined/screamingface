"""The Cloudflare Access identity resolver."""

from __future__ import annotations

import logging

import jwt
from fastapi import Request

from ..resolvers.base import Rejection, Resolution
from ..resolvers.local_jwt import bearer_token
from .identity import CfAccessVerificationError, CfAccessVerifier
from .provisioning import get_or_create_cf_access_account

logger = logging.getLogger(__name__)

#: The header Cloudflare Access injects into every request it forwards.
ASSERTION_HEADER = "Cf-Access-Jwt-Assertion"

#: The cookie Access sets on browser logins.
ASSERTION_COOKIE = "CF_Authorization"

_ALGORITHM = "RS256"

_REJECTION = Rejection(
    detail={
        "code": "cf_access_denied",
        "message": "Cloudflare Access identity could not be verified",
    }
)


class CfAccessResolver:
    """Authenticate a verified Cloudflare Access assertion, provisioning on first sight.

    INVARIANT: the mere presence of ``Cf-Access-Jwt-Assertion`` proves nothing —
    it is an ordinary header that anyone reaching the origin off-path can set.
    Every request is verified against Cloudflare's published keys here, so this
    layer holds even if the deployment's ingress isolation is later weakened.
    """

    name = "cf_access"

    def __init__(self, verifier: CfAccessVerifier, *, admin_emails: frozenset[str]) -> None:
        self._verifier = verifier
        self._admin_emails = admin_emails

    async def resolve(self, request: Request) -> Resolution:
        token = self._token(request)
        if token is None:
            return None

        try:
            identity = await self._verifier.verify(token)
        except CfAccessVerificationError as exc:
            # WHY the detail is generic: the exception text names the exact
            # failure (bad audience, unknown kid, expired) and is useful to an
            # operator in the log, but handing it to the caller would describe
            # this gateway's Access configuration to an unauthenticated party.
            logger.info("cf_access assertion rejected: %s", exc)
            return _REJECTION

        account = await get_or_create_cf_access_account(
            identity,
            admin_emails=self._admin_emails,
        )
        if account is None:
            return _REJECTION
        return account

    def _token(self, request: Request) -> str | None:
        """Find the assertion, in order of trustworthiness.

        The injected header comes straight from Cloudflare and is what makes
        browser SSO work at all; the cookie covers browsers whose request did not
        get the header; `Authorization: Bearer` is the API-client path
        (`cloudflared access token`). Only RS256 bearer tokens are claimed, so a
        local HS256 session token still belongs to LocalJwtResolver.
        """
        header = request.headers.get(ASSERTION_HEADER)
        if header:
            return header

        cookie = request.cookies.get(ASSERTION_COOKIE)
        if cookie:
            return cookie

        token = bearer_token(request)
        if token is None:
            return None
        try:
            algorithm = jwt.get_unverified_header(token).get("alg")
        except jwt.InvalidTokenError:
            return None
        return token if algorithm == _ALGORITHM else None
