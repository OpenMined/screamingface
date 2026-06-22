"""Tests for the core Google Code Assist OAuth helpers.

These helpers were extracted from ``gemini_provider`` (findings U5) so a second
Google Code Assist provider (Antigravity) can reuse the same-contract token
normalization, identity extraction, and retry-after parsing without a
plugin-to-plugin import. Core owns the single source of truth; the providers
import from here.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx
import pytest

from aigateway.core.errors import AuthError
from aigateway.core.google_code_assist import (
    AccountIdentity,
    account_label_from_credentials,
    compound_duration_to_seconds,
    decode_jwt_claims,
    expires_at_ms,
    extract_account_identity,
    normalize_token_response,
    parse_google_retry_after,
)


def _jwt(payload: dict[str, Any]) -> str:
    def encode(value: dict[str, Any] | bytes) -> str:
        raw = value if isinstance(value, bytes) else json.dumps(value).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{encode({'alg': 'none', 'typ': 'JWT'})}.{encode(payload)}.{encode(b'sig')}"


def _http_factory(transport: httpx.MockTransport):
    def factory():
        return httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(5.0))

    return factory


# --- token normalization ---------------------------------------------------


def test_normalize_token_response_requires_access_and_refresh_tokens() -> None:
    creds = normalize_token_response(
        {"access_token": "ya29.x", "refresh_token": "r-1", "expires_in": 3600}
    )
    assert creds["access_token"] == "ya29.x"
    assert creds["refresh_token"] == "r-1"
    assert creds["token_type"] == "Bearer"
    assert isinstance(creds["expires_at_ms"], int)


def test_normalize_token_response_carries_refresh_token_from_previous() -> None:
    creds = normalize_token_response(
        {"access_token": "ya29.new", "expires_in": 3600},
        {"refresh_token": "r-prev"},
    )
    assert creds["refresh_token"] == "r-prev"


def test_normalize_token_response_missing_access_token_raises() -> None:
    with pytest.raises(AuthError, match="access_token"):
        normalize_token_response({"refresh_token": "r-1"})


def test_normalize_token_response_missing_refresh_token_raises() -> None:
    with pytest.raises(AuthError, match="refresh_token"):
        normalize_token_response({"access_token": "ya29.x"})


def test_expires_at_ms_from_expires_in() -> None:
    before = int(time.time() * 1000)
    value = expires_at_ms({"expires_in": 3600}, {})
    assert value is not None
    assert value >= before + 3600 * 1000 - 5000


def test_expires_at_ms_none_without_signal() -> None:
    assert expires_at_ms({}, {}) is None


# --- identity --------------------------------------------------------------


def test_decode_jwt_claims_reads_payload() -> None:
    claims = decode_jwt_claims(_jwt({"email": "a@b.com", "sub": "s-1"}))
    assert claims["email"] == "a@b.com"
    assert claims["sub"] == "s-1"


def test_decode_jwt_claims_malformed_returns_empty() -> None:
    assert decode_jwt_claims("not-a-jwt") == {}


@pytest.mark.asyncio
async def test_extract_identity_prefers_id_token_claims() -> None:
    identity = await extract_account_identity(
        {
            "access_token": "unused",
            "id_token": _jwt({"email": "user@example.com", "name": "User"}),
        }
    )
    assert identity is not None
    assert identity.email == "user@example.com"
    assert identity.name == "User"


@pytest.mark.asyncio
async def test_extract_identity_falls_back_to_userinfo() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer ya29.userinfo"
        return httpx.Response(200, json={"sub": "sub-1", "name": "Google User"})

    identity = await extract_account_identity(
        {"access_token": "ya29.userinfo", "id_token": _jwt({"aud": "client"})},
        http_client_factory=_http_factory(httpx.MockTransport(handler)),
    )
    assert identity is not None
    assert identity.subject == "sub-1"
    assert identity.name == "Google User"


@pytest.mark.asyncio
async def test_extract_identity_none_on_userinfo_401() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_token"})

    identity = await extract_account_identity(
        {"access_token": "bad"},
        http_client_factory=_http_factory(httpx.MockTransport(handler)),
    )
    assert identity is None


def test_account_identity_as_dict_drops_empty() -> None:
    assert AccountIdentity(email="a@b.com").as_dict() == {"email": "a@b.com"}
    assert AccountIdentity().as_dict() == {}


def test_account_label_prefers_persisted_then_id_token() -> None:
    assert account_label_from_credentials({"account_label": "l@x.com"}) == "l@x.com"
    assert (
        account_label_from_credentials({"account_identity": {"name": "Named", "subject": "s"}})
        == "Named"
    )
    assert (
        account_label_from_credentials({"id_token": _jwt({"email": "t@x.com", "sub": "s2"})})
        == "t@x.com"
    )


# --- retry-after -----------------------------------------------------------


def test_parse_google_retry_after_prefers_header() -> None:
    assert parse_google_retry_after("reset after 9s", {"retry-after": "2"}) == 2.0


def test_parse_google_retry_after_from_retry_delay() -> None:
    body = '{"error": {"details": [{"@type": "...RetryInfo", "retryDelay": "5s"}]}}'
    assert parse_google_retry_after(body, {}) == 5.0


def test_parse_google_retry_after_compound_daily_quota() -> None:
    body = "Your quota will reset after 22h11m3s."
    assert parse_google_retry_after(body, {}) == 22 * 3600 + 11 * 60 + 3


def test_parse_google_retry_after_none_when_absent() -> None:
    assert parse_google_retry_after('{"error": {"code": 429}}', {}) is None


def test_compound_duration_to_seconds() -> None:
    assert compound_duration_to_seconds("1m30s") == 90.0
    assert compound_duration_to_seconds("8s") == 8.0
    assert compound_duration_to_seconds("nope") is None
