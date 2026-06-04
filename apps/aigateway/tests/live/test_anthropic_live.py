"""End-to-end live test against api.anthropic.com via the profile-based path.

Skipped unless AIGW_LIVE=1. Requires the logged-in admin account to have an
authenticated `anthropic:default` profile — typically achieved on this machine
by the Claude Code bootstrap importing existing CC credentials.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import litellm
import pytest
from fastapi.testclient import TestClient

from aigateway.main import create_app

pytestmark = pytest.mark.live

_database_prepared = False


def _live_enabled() -> bool:
    return os.environ.get("AIGW_LIVE") == "1"


def _prepare_live_database() -> None:
    global _database_prepared
    if _database_prepared:
        return

    app_dir = Path(__file__).resolve().parents[2]
    command = [sys.executable, "-m", "tortoise", "-c", "aigateway.db.TORTOISE_CONFIG", "migrate"]
    try:
        subprocess.run(
            command,
            cwd=app_dir,
            env=os.environ.copy(),
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        pytest.fail(
            "failed to migrate live AIGateway database before Anthropic live test\n"
            f"stdout:\n{exc.stdout}\n"
            f"stderr:\n{exc.stderr}"
        )

    _database_prepared = True


def _live_client() -> TestClient:
    _prepare_live_database()
    return TestClient(create_app())


def _require_default_profile(client: TestClient) -> None:
    listing = client.get("/v1/auth/profiles")
    assert listing.status_code == 200, listing.text
    profile = next(
        (
            p
            for p in listing.json()["profiles"]
            if p["provider"] == "anthropic" and p["name"] == "default"
        ),
        None,
    )
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
    password = _live_admin_password()
    response = client.post("/v1/auth/login", json={"username": "admin", "password": password})
    assert response.status_code == 200, response.text
    client.headers.update({"Authorization": f"Bearer {response.json()['token']}"})


def _live_admin_password() -> str:
    password = os.environ.get("AIGW_LIVE_ADMIN_PASSWORD") or os.environ.get(
        "AIGATEWAY_ADMIN_PASSWORD"
    )
    if not password:
        pytest.skip("Live auth tests require AIGW_LIVE_ADMIN_PASSWORD or AIGATEWAY_ADMIN_PASSWORD")
    assert password is not None
    return password


def _assert_premium_model_round_trip(client: TestClient, model: str, expected: str) -> None:
    resp = client.post(
        "/v1/chat/completions",
        headers={"X-Profile": "default"},
        json={
            "model": f"anthropic/{model}",
            "messages": [{"role": "user", "content": f"Reply with exactly: {expected}"}],
            "max_tokens": 20,
        },
    )
    assert resp.status_code == 200, resp.text
    content = resp.json()["choices"][0]["message"]["content"]
    assert content.strip()
    assert expected in content


@pytest.mark.skipif(not _live_enabled(), reason="AIGW_LIVE=1 not set")
def test_anthropic_round_trip_via_default_profile() -> None:
    _live_admin_password()
    with _live_client() as client:
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
def test_anthropic_premium_sonnet_round_trip_via_default_profile() -> None:
    _live_admin_password()
    with _live_client() as client:
        _login_admin(client)
        _require_default_profile(client)
        _assert_premium_model_round_trip(client, "claude-sonnet-4-6", "sonnet-premium-ok")


@pytest.mark.skipif(not _live_enabled(), reason="AIGW_LIVE=1 not set")
def test_anthropic_premium_opus_round_trip_via_default_profile() -> None:
    _live_admin_password()
    with _live_client() as client:
        _login_admin(client)
        _require_default_profile(client)
        _assert_premium_model_round_trip(client, "claude-opus-4-7", "opus-premium-ok")


@pytest.mark.skipif(not _live_enabled(), reason="AIGW_LIVE=1 not set")
def test_anthropic_streaming() -> None:
    _live_admin_password()
    with _live_client() as client:
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
    _live_admin_password()
    with _live_client() as client:
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


# ---------------------------------------------------------------------------
# Fan-out concurrency: prove the per-provider semaphore serializes upstream
# claude calls so a high-concurrency url4 fan-out cannot trip the implicit
# rate limit (which surfaces as a 429 or a masked 400 "credit balance too
# low"). Mirrors AIGW_PROVIDER_MAX_CONCURRENCY_OVERRIDES={"anthropic":1}.
# ---------------------------------------------------------------------------

_FANOUT_N = 6


def _install_inflight_tracker(monkeypatch) -> dict[str, int]:
    """Wrap ``litellm.acompletion`` (the upstream call the anthropic provider
    makes *inside* ``provider_slot``) to record the peak number of concurrent
    in-flight calls while still performing the real request.
    """
    real_acompletion = litellm.acompletion
    inflight = {"cur": 0, "max": 0}

    async def _tracked(*args, **kwargs):
        inflight["cur"] += 1
        inflight["max"] = max(inflight["max"], inflight["cur"])
        try:
            return await real_acompletion(*args, **kwargs)
        finally:
            inflight["cur"] -= 1

    monkeypatch.setattr(litellm, "acompletion", _tracked)
    return inflight


def _fire_concurrent_haiku(client: TestClient, n: int) -> list:
    """Fire ``n`` claude requests at the gateway concurrently (TestClient is
    sync, so we submit from a thread pool; the ASGI app handles them on one
    event loop where ``provider_slot`` gates upstream concurrency)."""

    def _one(i: int):
        return client.post(
            "/v1/chat/completions",
            headers={"X-Profile": "default"},
            json={
                "model": "anthropic/claude-haiku-4-5",
                "messages": [{"role": "user", "content": f"Reply with exactly: ok{i}"}],
                "max_tokens": 10,
            },
        )

    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(_one, range(n)))


@pytest.mark.skipif(not _live_enabled(), reason="AIGW_LIVE=1 not set")
def test_anthropic_fanout_serialized_under_cap_1(monkeypatch) -> None:
    """With anthropic capped to 1, N concurrent claude requests are serialized
    upstream (peak in-flight == 1) and ALL succeed — no implicit 429 /
    'credit balance too low' from a concurrent thundering herd. This is the
    behaviour the ``{"anthropic":1}`` concurrency override delivers.
    """
    _live_admin_password()
    monkeypatch.setenv("AIGW_PROVIDER_MAX_CONCURRENCY_OVERRIDES", '{"anthropic": 1}')
    inflight = _install_inflight_tracker(monkeypatch)

    with _live_client() as client:
        _login_admin(client)
        _require_default_profile(client)
        responses = _fire_concurrent_haiku(client, _FANOUT_N)

    for i, resp in enumerate(responses):
        assert resp.status_code == 200, (
            f"request {i} failed under serialized fan-out "
            f"(HTTP {resp.status_code}): {resp.text[:400]}"
        )
    assert inflight["cur"] == 0
    assert inflight["max"] == 1, (
        f"anthropic cap=1 must serialize upstream calls, but peak in-flight was "
        f"{inflight['max']} (expected 1)"
    )


@pytest.mark.skipif(not _live_enabled(), reason="AIGW_LIVE=1 not set")
def test_anthropic_fanout_overlaps_without_cap(monkeypatch) -> None:
    """Control for the serialization test: with the cap disabled
    (``anthropic:0`` = unlimited), the SAME concurrent fan-out actually
    overlaps upstream (peak in-flight > 1) — proving the tracker observes real
    concurrency, so the cap=1 test's ``max == 1`` is a genuine guarantee, not a
    TestClient artifact. Does not assert success: an unbounded herd is exactly
    the failure mode the cap exists to prevent.
    """
    _live_admin_password()
    monkeypatch.setenv("AIGW_PROVIDER_MAX_CONCURRENCY_OVERRIDES", '{"anthropic": 0}')
    inflight = _install_inflight_tracker(monkeypatch)

    with _live_client() as client:
        _login_admin(client)
        _require_default_profile(client)
        _fire_concurrent_haiku(client, _FANOUT_N)

    assert inflight["max"] > 1, (
        f"with the cap disabled the concurrent fan-out should overlap upstream "
        f"(peak in-flight > 1), but saw {inflight['max']} — the harness is not "
        f"exercising real concurrency, so the cap=1 assertion would be vacuous"
    )
