"""Tiny httpx.MockTransport-backed fake aigateway for SF-169 e2e tests.

Returns canned token responses for a fixed connection_id; rejects all
others with 404. Asserts the Authorization header matches an expected JWT.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx


def make_fake_aigw(
    *,
    expected_connection_id: str,
    expected_jwt: str,
    access_token: str = "aigw-fake-token",
    ttl_seconds: int = 3600,
) -> httpx.MockTransport:
    def handler(req: httpx.Request) -> httpx.Response:
        path = f"/v1/oauth/connections/{expected_connection_id}/token"
        if req.url.path != path:
            return httpx.Response(404, json={"detail": "connection_not_found"})
        auth = req.headers.get("authorization", "")
        if auth != f"Bearer {expected_jwt}":
            return httpx.Response(401, json={"detail": "jwt invalid"})
        expires_at = (datetime.now(UTC) + timedelta(seconds=ttl_seconds)).isoformat()
        return httpx.Response(200, json={"access_token": access_token, "expires_at": expires_at})

    return httpx.MockTransport(handler)


__all__ = ["make_fake_aigw"]
