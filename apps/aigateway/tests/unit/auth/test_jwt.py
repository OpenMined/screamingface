from __future__ import annotations

import jwt
import pytest

from aigateway.core.auth.jwt import decode_token, encode_token


def test_encode_decode_token_round_trip() -> None:
    token, expires_at = encode_token(
        account_id="account-id",
        username="admin",
        secret="s" * 32,
        ttl_seconds=60,
    )
    claims = decode_token(token, "s" * 32)
    assert claims["sub"] == "account-id"
    assert claims["username"] == "admin"
    assert claims["exp"] >= int(expires_at.timestamp())


def test_alg_none_rejected() -> None:
    token = jwt.encode(
        {"sub": "x", "username": "u", "iat": 1, "exp": 4_102_444_800},
        key="",
        algorithm="none",
    )
    with pytest.raises(jwt.InvalidAlgorithmError):
        decode_token(token, "s" * 32)


def test_missing_required_claim_rejected() -> None:
    token = jwt.encode({"sub": "x", "exp": 4_102_444_800}, "s" * 32, algorithm="HS256")
    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_token(token, "s" * 32)
