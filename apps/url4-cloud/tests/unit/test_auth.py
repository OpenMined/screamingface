"""Behaviour tests for the url4-cloud auth primitives (OME-517; docs/protocol.md §7)."""

import re
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from url4_cloud.app import create_app
from url4_cloud.auth import (
    IatWindowExceeded,
    InvalidToken,
    JwtCodec,
    MissingIat,
    TokenExpired,
    VerifiedClaims,
    install_problem_handlers,
    new_topic,
)
from url4_cloud.config import Settings

WINDOW_S = 60
SECRET = "unit-test-secret"
T0 = datetime(2026, 7, 21, 9, 0, 0, tzinfo=UTC)


def _codec() -> JwtCodec:
    return JwtCodec(secret=SECRET, iat_window_s=WINDOW_S)


# --- token.py -------------------------------------------------------------


def test_new_topic_is_64_alnum() -> None:
    topic = new_topic()
    assert re.fullmatch(r"[A-Za-z0-9]{64}", topic) is not None


def test_new_topic_is_non_repeating() -> None:
    assert new_topic() != new_topic()


# --- jwt.py: sign / verify ------------------------------------------------


def test_sign_verify_roundtrip() -> None:
    topic = new_topic()
    codec = _codec()
    token = codec.sign(topic, T0)
    claims = codec.verify(token, T0)
    assert claims["sub"] == topic
    iat, exp, jti = claims["iat"], claims["exp"], claims["jti"]
    assert isinstance(iat, int) and isinstance(exp, int)
    assert exp == iat + WINDOW_S
    assert isinstance(jti, str) and jti


def test_fresh_token_inside_window_accepted() -> None:
    codec = _codec()
    token = codec.sign("topic", T0)
    claims = codec.verify(token, T0 + timedelta(seconds=WINDOW_S - 1))
    assert claims["sub"] == "topic"


def test_wrong_secret_rejected() -> None:
    token = _codec().sign("topic", T0)
    with pytest.raises(InvalidToken):
        JwtCodec(secret="other-secret", iat_window_s=WINDOW_S).verify(token, T0)


def test_malformed_token_rejected() -> None:
    with pytest.raises(InvalidToken):
        _codec().verify("not-a-jwt", T0)


def test_missing_iat_rejected() -> None:
    # WHY: forge a signature-valid token that omits `iat` — verify must reject on the claim, not
    # on the signature (a token without a fresh-issue timestamp cannot be windowed).
    forged = pyjwt.encode({"sub": "topic"}, SECRET, algorithm="HS256")
    with pytest.raises(MissingIat):
        _codec().verify(forged, T0)


def test_iat_window_exceeded_rejected() -> None:
    token = _codec().sign("topic", T0)
    with pytest.raises(IatWindowExceeded):
        _codec().verify(token, T0 + timedelta(seconds=WINDOW_S + 1))


def test_exp_boundary_rejected() -> None:
    # exp == iat + window; at now == exp the token is expired (RFC 7519: valid requires now < exp).
    token = _codec().sign("topic", T0)
    with pytest.raises(TokenExpired):
        _codec().verify(token, T0 + timedelta(seconds=WINDOW_S))


def test_error_text_never_leaks_secret_or_token() -> None:
    token = _codec().sign("topic", T0)
    try:
        _codec().verify(token, T0 + timedelta(seconds=WINDOW_S + 1))
    except IatWindowExceeded as exc:
        assert SECRET not in str(exc)
        assert token not in str(exc)
    else:  # pragma: no cover - guarded by the assertion above
        pytest.fail("expected IatWindowExceeded")


# --- dependency + RFC 9457 problem+json -----------------------------------


def _protected_app(now: datetime) -> FastAPI:
    app = create_app(Settings(jwt_secret=SECRET, iat_window_s=WINDOW_S))
    install_problem_handlers(app)
    app.state.clock = lambda: now

    @app.get("/protected")
    def protected(claims: VerifiedClaims) -> dict[str, str]:
        return {"sub": str(claims["sub"])}

    return app


def test_dependency_accepts_valid_capability() -> None:
    token = _codec().sign("topic-abc", T0)
    client = TestClient(_protected_app(T0))
    resp = client.get("/protected", headers={"URL4-Capability": token})
    assert resp.status_code == 200
    assert resp.json() == {"sub": "topic-abc"}


def test_dependency_rejects_expired_as_problem_json() -> None:
    token = _codec().sign("topic", T0)
    client = TestClient(_protected_app(T0 + timedelta(seconds=WINDOW_S + 5)))
    resp = client.get("/protected", headers={"URL4-Capability": token})
    assert resp.status_code == 401
    assert resp.headers["content-type"].startswith("application/problem+json")
    body = resp.json()
    assert body["status"] == 401
    assert body["title"]
    assert "type" in body


def test_dependency_rejects_missing_capability() -> None:
    client = TestClient(_protected_app(T0))
    resp = client.get("/protected")
    assert resp.status_code == 401
    assert resp.headers["content-type"].startswith("application/problem+json")


def test_dependency_rejects_tampered_capability() -> None:
    client = TestClient(_protected_app(T0))
    resp = client.get("/protected", headers={"URL4-Capability": "garbage.token.value"})
    assert resp.status_code == 401
    assert resp.headers["content-type"].startswith("application/problem+json")


def test_dependency_error_body_omits_token() -> None:
    token = _codec().sign("secret-topic", T0)
    client = TestClient(_protected_app(T0 + timedelta(seconds=WINDOW_S + 5)))
    resp = client.get("/protected", headers={"URL4-Capability": token})
    assert token not in resp.text


def test_dependency_ignores_authorization_bearer_header() -> None:
    # INVARIANT: the capability rides URL4-Capability ONLY — a valid token on the primary
    # Authorization slot is NOT accepted, so the two credentials never conflate (OME-556).
    token = _codec().sign("topic-abc", T0)
    client = TestClient(_protected_app(T0))
    resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert resp.headers["content-type"].startswith("application/problem+json")
