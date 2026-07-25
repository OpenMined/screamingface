"""The resolver end-to-end: token discovery, rejection shape, log hygiene."""

from __future__ import annotations

import logging

import jwt
import pytest
from fastapi import Request

from aigateway.core.auth.cf_access import (
    ASSERTION_COOKIE,
    ASSERTION_HEADER,
    build_cf_access_resolver,
)
from aigateway.core.auth.log_filter import RedactProvisioningTokenFilter
from aigateway.core.auth.models import Account
from aigateway.core.auth.resolvers import IdentityResolver, LocalJwtResolver, Rejection

from .conftest import AUDIENCE, TEAM_DOMAIN, FakeCerts, claims

pytestmark = pytest.mark.asyncio


def _resolver(certs: FakeCerts, **kwargs):
    return build_cf_access_resolver(
        team_domain=TEAM_DOMAIN,
        audience=AUDIENCE,
        http_client_factory=certs.factory(),
        **kwargs,
    )


def _request(headers: list[tuple[bytes, bytes]]) -> Request:
    return Request(
        {"type": "http", "method": "GET", "path": "/", "headers": headers, "query_string": b""}
    )


async def test_resolver_satisfies_the_identity_resolver_port(certs) -> None:
    assert isinstance(_resolver(certs), IdentityResolver)


async def test_injected_header_authenticates_and_provisions(db, certs, signing_key) -> None:
    token = signing_key.sign(claims())
    request = _request([(ASSERTION_HEADER.lower().encode(), token.encode())])

    account = await _resolver(certs).resolve(request)

    assert isinstance(account, Account)
    assert account.external_subject == "cf-user-uuid-1"


async def test_browser_cookie_authenticates(db, certs, signing_key) -> None:
    # The prior prototype of this feature read ONLY `Authorization: Bearer`, so
    # browser/cookie SSO silently never worked. Guard that regression.
    token = signing_key.sign(claims())
    request = _request([(b"cookie", f"{ASSERTION_COOKIE}={token}".encode())])

    account = await _resolver(certs).resolve(request)

    assert isinstance(account, Account)


async def test_bearer_token_authenticates_for_api_clients(db, certs, signing_key) -> None:
    token = signing_key.sign(claims())
    request = _request([(b"authorization", f"Bearer {token}".encode())])

    account = await _resolver(certs).resolve(request)

    assert isinstance(account, Account)


async def test_abstains_when_no_credential_is_present(db, certs) -> None:
    assert await _resolver(certs).resolve(_request([])) is None


async def test_abstains_on_a_local_hs256_session_token(db, certs) -> None:
    # INVARIANT: recognition across the chain is disjoint. A local session token
    # belongs to LocalJwtResolver, so this resolver must abstain rather than
    # reject — otherwise it would claim and 401 every local login.
    local = jwt.encode({"sub": "x"}, "s" * 32, algorithm="HS256")
    request = _request([(b"authorization", f"Bearer {local}".encode())])

    assert await _resolver(certs).resolve(request) is None


async def test_forged_assertion_is_rejected_without_provisioning(db, certs) -> None:
    from .conftest import SigningKey

    forged = SigningKey("kid-current").sign(claims())
    request = _request([(ASSERTION_HEADER.lower().encode(), forged.encode())])

    outcome = await _resolver(certs).resolve(request)

    assert isinstance(outcome, Rejection)
    assert outcome.status_code == 401
    assert await Account.all().count() == 0, "a rejected assertion must not create an account"


async def test_rejection_detail_does_not_leak_the_configuration(db, certs, signing_key) -> None:
    # WHY: the underlying error names the exact failure (wrong audience, unknown
    # kid). Useful in the operator's log, but handing it to an unauthenticated
    # caller describes this gateway's Access configuration back to them.
    token = signing_key.sign(claims(audience="b" * 64))
    request = _request([(ASSERTION_HEADER.lower().encode(), token.encode())])

    outcome = await _resolver(certs).resolve(request)

    assert isinstance(outcome, Rejection)
    assert AUDIENCE not in str(outcome.detail)
    assert "aud" not in str(outcome.detail).lower()


async def test_admin_allowlist_is_honoured_through_the_resolver(db, certs, signing_key) -> None:
    request = _request([(ASSERTION_HEADER.lower().encode(), signing_key.sign(claims()).encode())])

    account = await _resolver(certs, admin_emails=frozenset({"user@example.com"})).resolve(request)

    assert isinstance(account, Account)
    assert account.is_admin is True


async def test_the_local_resolver_abstains_on_a_cloudflare_assertion(certs, signing_key) -> None:
    # The other half of disjoint recognition, asserted from the local side.
    token = signing_key.sign(claims())
    request = _request([(b"authorization", f"Bearer {token}".encode())])

    assert await LocalJwtResolver().resolve(request) is None


async def test_assertion_headers_are_redacted_from_logs(caplog) -> None:
    # INVARIANT: a leaked assertion is a replayable identity until it expires.
    logger = logging.getLogger("aigateway.test.cf_access")
    logger.addFilter(RedactProvisioningTokenFilter())

    with caplog.at_level(logging.INFO):
        logger.info("headers: Cf-Access-Jwt-Assertion: ey.SECRET.sig")
        logger.info("headers: cf-access-client-secret=SUPERSECRET")
        logger.info("raw %s", [(b"cf-access-jwt-assertion", b"ey.SECRET.sig")])

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert "SECRET" not in rendered
    assert "SUPERSECRET" not in rendered
    assert "[REDACTED]" in rendered
