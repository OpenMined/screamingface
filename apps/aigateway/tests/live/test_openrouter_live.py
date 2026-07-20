"""End-to-end live BYOK smoke against openrouter.ai (OME-428 Phase 4, optional).

Owner-gated: skipped unless AIGW_LIVE=1 AND AIGW_LIVE_OPENROUTER_KEY is set —
the key is a real OpenRouter API key supplied by the owner for this run only.
It is stored through the normal encrypted connection lifecycle (never via env
fallback inside the gateway: the poisoned-globals contract tests pin that) and
never echoed by any response.

Model defaults to a cheap upstream and can be overridden with
AIGW_LIVE_OPENROUTER_MODEL (gateway form: openrouter/<author>/<model>).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aigateway.main import create_app
from aigateway.plugins.openrouter_provider import plugin as openrouter_plugin_module
from aigateway.plugins.openrouter_provider.settings import OpenRouterPluginSettings

pytestmark = pytest.mark.live

_CONNECTION_LABEL = "live-openrouter-smoke"

_database_prepared = False


def _live_enabled() -> bool:
    return os.environ.get("AIGW_LIVE") == "1"


def _live_openrouter_key() -> str:
    key = os.environ.get("AIGW_LIVE_OPENROUTER_KEY")
    if not key:
        pytest.skip("Live OpenRouter test requires AIGW_LIVE_OPENROUTER_KEY")
    return key


def _live_model() -> str:
    return os.environ.get("AIGW_LIVE_OPENROUTER_MODEL", "openrouter/openai/gpt-4o-mini")


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
            "failed to migrate live AIGateway database before OpenRouter live test\n"
            f"stdout:\n{exc.stdout}\n"
            f"stderr:\n{exc.stderr}"
        )

    _database_prepared = True


def _live_client() -> TestClient:
    _prepare_live_database()
    return TestClient(create_app())


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


def _ensure_connection(client: TestClient, api_key: str) -> None:
    """Create the smoke connection, or refresh its key so reruns stay green.

    PUT api-key re-activates an errored connection, so a previous failed run
    (e.g. a revoked key that tripped the local-401 invalidation) self-heals.
    """
    listing = client.get("/v1/oauth/connections", params={"provider": "openrouter"})
    assert listing.status_code == 200, listing.text
    existing = next(
        (c for c in listing.json()["connections"] if c["label"] == _CONNECTION_LABEL),
        None,
    )
    if existing is None:
        created = client.post(
            "/v1/oauth/connections/api-key",
            json={"provider": "openrouter", "label": _CONNECTION_LABEL, "api_key": api_key},
        )
        assert created.status_code == 201, created.text
        assert api_key not in created.text  # the key is never echoed
        return
    replaced = client.put(
        f"/v1/oauth/connections/{existing['id']}/api-key",
        json={"api_key": api_key},
    )
    assert replaced.status_code == 200, replaced.text
    assert api_key not in replaced.text


@pytest.mark.skipif(not _live_enabled(), reason="AIGW_LIVE=1 not set")
def test_openrouter_byok_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    api_key = _live_openrouter_key()
    _live_admin_password()
    monkeypatch.setattr(
        openrouter_plugin_module.PLUGIN, "settings", OpenRouterPluginSettings(enabled=True)
    )

    with _live_client() as client:
        _login_admin(client)
        _ensure_connection(client, api_key)

        resp = client.post(
            "/v1/chat/completions",
            headers={"X-Profile": _CONNECTION_LABEL},
            json={
                "model": _live_model(),
                "messages": [{"role": "user", "content": "Reply with exactly: PONG"}],
                "max_tokens": 16,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # Native metadata survives the gateway (D10): OpenRouter generation id,
        # text, finish reason, and token usage all present and untouched.
        assert str(data.get("id", "")), data
        content = data["choices"][0]["message"]["content"]
        assert content and content.strip()
        assert data["choices"][0]["finish_reason"]
        usage = data.get("usage")
        assert isinstance(usage, dict), data
        assert usage.get("prompt_tokens", 0) > 0
        assert usage.get("completion_tokens", 0) > 0

        # The BYOK credential never appears in any response body.
        assert api_key not in resp.text
