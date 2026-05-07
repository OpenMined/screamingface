"""End-to-end live test against api.anthropic.com.

Skipped unless AIGW_LIVE=1 is set. Requires a working Claude Code keychain
entry on this machine — it does NOT mock the credential store. Confirms
that an OAuth token from the real keychain successfully authenticates a
real LiteLLM call.
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
def test_anthropic_round_trip() -> None:
    client = TestClient(create_app())
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "anthropic/claude-haiku-4-5",
            "messages": [{"role": "user", "content": "Reply with the single word 'pong'."}],
            "max_tokens": 10,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["choices"][0]["message"]["content"]
