from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import jwt
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.utils import base64url_encode
from tortoise.contrib.test import tortoise_test_context

TEAM_DOMAIN = "example-team.cloudflareaccess.com"
AUDIENCE = "a" * 64
CERTS_URL = f"https://{TEAM_DOMAIN}/cdn-cgi/access/certs"


class SigningKey:
    """An RSA keypair that can both sign assertions and publish itself as a JWK."""

    def __init__(self, kid: str) -> None:
        self.kid = kid
        self._private = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def as_jwk(self) -> dict[str, str]:
        numbers = self._private.public_key().public_numbers()

        def b64(value: int) -> str:
            raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
            return base64url_encode(raw).decode()

        return {
            "kty": "RSA",
            "kid": self.kid,
            "alg": "RS256",
            "use": "sig",
            "n": b64(numbers.n),
            "e": b64(numbers.e),
        }

    def sign(self, claims: dict[str, Any]) -> str:
        return jwt.encode(claims, self._private, algorithm="RS256", headers={"kid": self.kid})


class FakeCerts:
    """Serves the certs endpoint, with controllable key set and failure mode."""

    def __init__(self, *keys: SigningKey) -> None:
        self.keys = list(keys)
        self.fail = False
        self.requests = 0
        #: Extra raw JWK dicts served alongside `keys` (to simulate a junk entry).
        self.malformed: list[dict] = []
        #: Replaces the whole response body when set (to simulate a broken endpoint).
        self.payload_override: object | None = None

    def factory(self):
        async def _handler(request: httpx.Request) -> httpx.Response:
            # WHY async + sleep(0): a purely synchronous mock transport never
            # yields, so "concurrent" coroutines actually run to completion one
            # after another and any lock/re-check path stays unexercised. The
            # yield point is what makes contention real in tests.
            await asyncio.sleep(0)
            self.requests += 1
            if self.fail:
                raise httpx.ConnectError("certs unreachable", request=request)
            if self.payload_override is not None:
                return httpx.Response(200, json=self.payload_override)
            body = {"keys": [key.as_jwk() for key in self.keys] + self.malformed}
            return httpx.Response(200, json=body)

        def _factory() -> httpx.AsyncClient:
            return httpx.AsyncClient(transport=httpx.MockTransport(_handler))

        return _factory


def claims(
    *,
    sub: str = "cf-user-uuid-1",
    email: str | None = "user@example.com",
    common_name: str | None = None,
    audience: str = AUDIENCE,
    issuer: str = f"https://{TEAM_DOMAIN}",
    expires_in: int = 3600,
) -> dict[str, Any]:
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": sub,
        "aud": audience,
        "iss": issuer,
        "iat": now,
        "exp": now + expires_in,
    }
    if email is not None:
        payload["email"] = email
    if common_name is not None:
        payload["common_name"] = common_name
    return payload


@pytest.fixture
def signing_key() -> SigningKey:
    return SigningKey("kid-current")


@pytest.fixture
def rotated_key() -> SigningKey:
    return SigningKey("kid-previous")


@pytest.fixture
def certs(signing_key: SigningKey) -> FakeCerts:
    return FakeCerts(signing_key)


@pytest_asyncio.fixture
async def db():
    async with tortoise_test_context(["aigateway.core.auth.models"]):
        yield
