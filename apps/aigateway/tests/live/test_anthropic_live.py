"""End-to-end live test against api.anthropic.com via the profile-based path.

Skipped unless AIGW_LIVE=1. Requires the gateway's `anthropic:default`
profile to be authenticated — typically achieved on this machine by the
Claude Code bootstrap importing existing CC credentials.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from aigateway.main import create_app

pytestmark = pytest.mark.live


def _live_enabled() -> bool:
    return os.environ.get("AIGW_LIVE") == "1"


@pytest.mark.skipif(not _live_enabled(), reason="AIGW_LIVE=1 not set")
def test_anthropic_round_trip_via_default_profile() -> None:
    with TestClient(create_app()) as client:
        listing = client.get("/v1/auth/profiles").json()
        ids = {p["id"] for p in listing["profiles"]}
        assert "anthropic:default" in ids, (
            "anthropic:default profile not present. "
            "Run `claude auth login` or seed a profile via /v1/auth/anthropic/profiles."
        )

        resp = client.post(
            "/v1/chat/completions",
            headers={"X-Profile": "default"},
            json={
                "model": "anthropic/claude-haiku-4-5",
                "messages": [{"role": "user", "content": "Reply with the single word 'pong'."}],
                "max_tokens": 10,
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["choices"][0]["message"]["content"]
