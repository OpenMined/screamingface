"""End-to-end live test against api.anthropic.com via the profile-based path.

Skipped unless AIGW_LIVE=1. Requires the gateway's `anthropic:default`
profile to be authenticated — typically achieved on this machine by the
Claude Code bootstrap importing existing CC credentials.
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

from aigateway.main import create_app

pytestmark = pytest.mark.live


def _live_enabled() -> bool:
    return os.environ.get("AIGW_LIVE") == "1"


def _require_default_profile(client: TestClient) -> None:
    listing = client.get("/v1/auth/profiles")
    assert listing.status_code == 200, listing.text
    profiles = {p["id"]: p for p in listing.json()["profiles"]}
    profile = profiles.get("anthropic:default")
    if profile is None:
        pytest.skip(
            "anthropic:default profile not present. Run `claude auth login` or seed a "
            "profile via /v1/auth/anthropic/profiles."
        )
    assert profile is not None
    state = profile["state"]
    if state != "authenticated":
        pytest.skip(
            f"anthropic:default profile is {state!r}, not 'authenticated'. "
            "Complete auth before running live Anthropic tests."
        )


def _login_admin(client: TestClient) -> None:
    password = os.environ.get("AIGW_LIVE_ADMIN_PASSWORD") or os.environ.get(
        "AIGATEWAY_ADMIN_PASSWORD"
    )
    if not password:
        pytest.skip("Live auth tests require AIGW_LIVE_ADMIN_PASSWORD or AIGATEWAY_ADMIN_PASSWORD")
    response = client.post("/v1/auth/login", json={"username": "admin", "password": password})
    assert response.status_code == 200, response.text
    client.headers.update({"Authorization": f"Bearer {response.json()['token']}"})


@pytest.mark.skipif(not _live_enabled(), reason="AIGW_LIVE=1 not set")
def test_anthropic_round_trip_via_default_profile() -> None:
    with TestClient(create_app()) as client:
        _login_admin(client)
        _require_default_profile(client)

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


@pytest.mark.skipif(not _live_enabled(), reason="AIGW_LIVE=1 not set")
def test_anthropic_streaming() -> None:
    with TestClient(create_app()) as client:
        _login_admin(client)
        _require_default_profile(client)

        with client.stream(
            "POST",
            "/v1/chat/completions",
            headers={"X-Profile": "default"},
            json={
                "model": "anthropic/claude-haiku-4-5",
                "messages": [{"role": "user", "content": "Reply with the word stream."}],
                "max_tokens": 20,
                "stream": True,
            },
        ) as resp:
            assert resp.status_code == 200, resp.text
            data_lines = [
                line.removeprefix("data: ")
                for line in resp.iter_lines()
                if line.startswith("data: ")
            ]

    assert data_lines
    assert data_lines[-1] == "[DONE]"

    chunks = [json.loads(line) for line in data_lines[:-1]]
    text = "".join(
        choice.get("delta", {}).get("content") or ""
        for chunk in chunks
        for choice in chunk.get("choices", [])
    )
    assert chunks
    assert text.strip()


@pytest.mark.skipif(not _live_enabled(), reason="AIGW_LIVE=1 not set")
def test_anthropic_tool_calls() -> None:
    with TestClient(create_app()) as client:
        _login_admin(client)
        _require_default_profile(client)

        resp = client.post(
            "/v1/chat/completions",
            headers={"X-Profile": "default"},
            json={
                "model": "anthropic/claude-haiku-4-5",
                "messages": [
                    {
                        "role": "user",
                        "content": "Use the get_weather tool for Paris, France.",
                    }
                ],
                "max_tokens": 128,
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "description": "Get the current weather for a location.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "location": {
                                        "type": "string",
                                        "description": "City and country, e.g. Paris, France.",
                                    }
                                },
                                "required": ["location"],
                            },
                        },
                    }
                ],
                "tool_choice": {"type": "function", "function": {"name": "get_weather"}},
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        tool_calls = body["choices"][0]["message"].get("tool_calls") or []
        assert tool_calls
        assert tool_calls[0]["function"]["name"] == "get_weather"
