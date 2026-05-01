import base64
import hashlib

from aigateway.core.oauth_pkce import generate_pkce, generate_state


def test_pkce_returns_verifier_and_challenge_pair() -> None:
    verifier, challenge = generate_pkce()
    assert 43 <= len(verifier) <= 128
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert challenge == expected


def test_state_is_url_safe_and_unique() -> None:
    a = generate_state()
    b = generate_state()
    assert a != b
    assert len(a) >= 32
    assert all(c.isalnum() or c in "-_" for c in a)
