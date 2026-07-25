"""Assertion verification — the layer that must never fail open."""

from __future__ import annotations

import asyncio

import jwt
import pytest

from aigateway.core.auth.cf_access import (
    CfAccessVerificationError,
    CfAccessVerifier,
    CloudflareAccessJwks,
)

from .conftest import AUDIENCE, TEAM_DOMAIN, FakeCerts, SigningKey, claims

pytestmark = pytest.mark.asyncio


def _verifier(certs: FakeCerts, **kwargs) -> CfAccessVerifier:
    jwks = CloudflareAccessJwks(
        TEAM_DOMAIN,
        http_client_factory=certs.factory(),
        **kwargs,
    )
    return CfAccessVerifier(jwks, audience=AUDIENCE, team_domain=TEAM_DOMAIN)


async def test_valid_idp_assertion_yields_the_subject_and_email(certs, signing_key) -> None:
    identity = await _verifier(certs).verify(signing_key.sign(claims()))

    assert identity.subject == "cf-user-uuid-1"
    assert identity.email == "user@example.com"
    assert identity.is_service_token is False


async def test_service_token_assertion_is_keyed_on_common_name(certs, signing_key) -> None:
    # A service-token assertion carries an empty `sub` and no email.
    token = signing_key.sign(claims(sub="", email=None, common_name="client-id-abc"))

    identity = await _verifier(certs).verify(token)

    assert identity.subject == "client-id-abc"
    assert identity.email is None
    assert identity.is_service_token is True


async def test_assertion_with_neither_sub_nor_common_name_is_rejected(certs, signing_key) -> None:
    token = signing_key.sign(claims(sub="", email=None))

    with pytest.raises(CfAccessVerificationError):
        await _verifier(certs).verify(token)


async def test_wrong_audience_is_rejected(certs, signing_key) -> None:
    # INVARIANT: `aud` scopes the assertion to THIS application. Without this
    # check any Access app in the same team could authenticate to the gateway.
    token = signing_key.sign(claims(audience="b" * 64))

    with pytest.raises(CfAccessVerificationError):
        await _verifier(certs).verify(token)


async def test_wrong_issuer_is_rejected(certs, signing_key) -> None:
    token = signing_key.sign(claims(issuer="https://attacker.cloudflareaccess.com"))

    with pytest.raises(CfAccessVerificationError):
        await _verifier(certs).verify(token)


async def test_expired_assertion_is_rejected(certs, signing_key) -> None:
    token = signing_key.sign(claims(expires_in=-1))

    with pytest.raises(CfAccessVerificationError):
        await _verifier(certs).verify(token)


async def test_unsigned_alg_none_token_is_rejected(certs) -> None:
    token = jwt.encode(claims(), key="", algorithm="none", headers={"kid": "kid-current"})

    with pytest.raises(CfAccessVerificationError):
        await _verifier(certs).verify(token)


async def test_hs256_forgery_using_the_public_key_is_rejected(certs, signing_key) -> None:
    # INVARIANT: the classic algorithm-confusion attack — re-sign the payload
    # with HS256 using the PUBLIC key bytes as the HMAC secret. Rejected because
    # the verifier pins algorithms=["RS256"] rather than trusting the header.
    public_jwk = signing_key.as_jwk()
    token = jwt.encode(
        claims(),
        key=public_jwk["n"],
        algorithm="HS256",
        headers={"kid": "kid-current"},
    )

    with pytest.raises(CfAccessVerificationError):
        await _verifier(certs).verify(token)


async def test_token_without_a_kid_is_rejected(certs, signing_key) -> None:
    with pytest.raises(CfAccessVerificationError):
        await _verifier(certs).verify(jwt.encode(claims(), key="k" * 32, algorithm="HS256"))


async def test_key_rotation_previous_key_still_verifies(certs, rotated_key) -> None:
    # Cloudflare rotates every 6 weeks and serves current + previous for 7 days.
    certs.keys.append(rotated_key)

    identity = await _verifier(certs).verify(rotated_key.sign(claims()))

    assert identity.subject == "cf-user-uuid-1"


async def test_unknown_kid_refetches_once_then_rate_limits(certs, signing_key) -> None:
    # WHY rate-limit: a forged `kid` must not let an unauthenticated caller drive
    # unbounded outbound requests to Cloudflare.
    verifier = _verifier(certs)
    forged = SigningKey("kid-does-not-exist")

    for _ in range(3):
        with pytest.raises(CfAccessVerificationError):
            await verifier.verify(forged.sign(claims()))

    assert certs.requests == 1


async def test_jwks_outage_with_a_warm_cache_still_verifies(certs, signing_key) -> None:
    verifier = _verifier(certs)
    await verifier.verify(signing_key.sign(claims()))

    certs.fail = True
    identity = await verifier.verify(signing_key.sign(claims()))

    assert identity.subject == "cf-user-uuid-1"


async def test_jwks_outage_with_a_cold_cache_refuses(certs, signing_key) -> None:
    # INVARIANT: degraded, never open. With no cached key there is nothing to
    # verify against, so the request must be refused — not admitted.
    certs.fail = True

    with pytest.raises(CfAccessVerificationError):
        await _verifier(certs).verify(signing_key.sign(claims()))


async def test_empty_key_set_refuses(signing_key) -> None:
    with pytest.raises(CfAccessVerificationError):
        await _verifier(FakeCerts()).verify(signing_key.sign(claims()))


async def test_a_malformed_key_does_not_discard_the_rest_of_the_key_set(certs, signing_key) -> None:
    # INVARIANT: one unusable JWK must not take the whole key set down with it.
    # During a rotation the set holds current + previous; discarding everything
    # because one entry is junk would 401 the entire fleet.
    certs.malformed = [{"kty": "RSA", "kid": "junk", "n": "!!not-base64!!", "e": "AQAB"}]

    identity = await _verifier(certs).verify(signing_key.sign(claims()))

    assert identity.subject == "cf-user-uuid-1"


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"keys": "not-a-list"},
        {"keys": [{"kid": "no-key-material"}]},
        {"keys": ["not-an-object"]},
        {"keys": [{"kty": "RSA", "n": "x", "e": "AQAB"}]},
        {},
    ],
    ids=[
        "not-an-object",
        "keys-not-a-list",
        "unusable-key",
        "entry-not-an-object",
        "key-without-kid",
        "no-keys-field",
    ],
)
async def test_an_unusable_certs_response_refuses_rather_than_fails_open(
    signing_key, payload
) -> None:
    # INVARIANT: degraded, never open. A certs endpoint returning something we
    # cannot parse must refuse the request, not skip verification.
    certs = FakeCerts(signing_key)
    certs.payload_override = payload

    with pytest.raises(CfAccessVerificationError):
        await _verifier(certs).verify(signing_key.sign(claims()))


async def test_a_failed_refresh_does_not_wipe_the_cached_key_set(certs, signing_key) -> None:
    # WHY this is distinct from the warm-cache test above: that one never reaches
    # the refresh path at all (a known `kid` is served straight from cache). THIS
    # forces a refresh with an unknown `kid`, fails it, and then proves the
    # previously-cached key still verifies — i.e. the failed fetch degraded the
    # cache rather than emptying it. Without stale-on-error, one Cloudflare blip
    # would 401 the entire fleet.
    # min_refetch_interval_seconds=0 stands in for "the refetch window has
    # elapsed". Without it the rate limiter short-circuits first and _refresh is
    # never even attempted — the two defenses overlap, and this is the ordering
    # that decides which one answers.
    verifier = _verifier(certs, min_refetch_interval_seconds=0)
    await verifier.verify(signing_key.sign(claims()))

    certs.fail = True
    unknown = SigningKey("kid-never-published")
    with pytest.raises(CfAccessVerificationError):
        await verifier.verify(unknown.sign(claims()))

    identity = await verifier.verify(signing_key.sign(claims()))
    assert identity.subject == "cf-user-uuid-1", "the cached key must survive a failed refresh"


async def test_the_rate_limiter_answers_before_a_refresh_is_attempted(certs, signing_key) -> None:
    # The other side of that ordering: inside the refetch window an unknown `kid`
    # must NOT reach the network at all, so a forged kid cannot be used to drive
    # outbound requests to Cloudflare.
    verifier = _verifier(certs)
    await verifier.verify(signing_key.sign(claims()))
    requests_after_warmup = certs.requests

    unknown = SigningKey("kid-never-published")
    with pytest.raises(CfAccessVerificationError):
        await verifier.verify(unknown.sign(claims()))

    assert certs.requests == requests_after_warmup


async def test_concurrent_cold_start_fetches_the_key_set_only_once(certs, signing_key) -> None:
    # INVARIANT: the lock + re-check must collapse a cold-start stampede into one
    # fetch. A fleet restarting behind Cloudflare would otherwise hit the certs
    # endpoint once per in-flight request.
    verifier = _verifier(certs)
    token = signing_key.sign(claims())

    identities = await asyncio.gather(*(verifier.verify(token) for _ in range(8)))

    assert certs.requests == 1
    assert {identity.subject for identity in identities} == {"cf-user-uuid-1"}
