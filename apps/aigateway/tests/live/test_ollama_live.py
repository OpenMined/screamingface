from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient

from aigateway.main import create_app
from aigateway.plugins.ollama_provider.discovery import resolve_ollama_host

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
            "failed to migrate live AIGateway database before Ollama live test\n"
            f"stdout:\n{exc.stdout}\n"
            f"stderr:\n{exc.stderr}"
        )

    _database_prepared = True


def _live_client() -> TestClient:
    _prepare_live_database()
    return TestClient(create_app())


def _live_admin_password() -> str:
    password = os.environ.get("AIGW_LIVE_ADMIN_PASSWORD") or os.environ.get(
        "AIGATEWAY_ADMIN_PASSWORD"
    )
    if not password:
        pytest.skip("Live auth tests require AIGW_LIVE_ADMIN_PASSWORD or AIGATEWAY_ADMIN_PASSWORD")
    assert password is not None
    return password


def _login_admin(client: TestClient) -> None:
    response = client.post(
        "/v1/auth/login",
        json={"username": "admin", "password": _live_admin_password()},
    )
    assert response.status_code == 200, response.text
    client.headers.update({"Authorization": f"Bearer {response.json()['token']}"})


def _first_live_model(host: str) -> str:
    try:
        response = httpx.get(f"{host}/api/tags", timeout=2.0)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        pytest.skip(f"Ollama not reachable at {host}: {exc}")
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        pytest.skip(f"Ollama /api/tags at {host} returned malformed payload")
        raise AssertionError("unreachable")
    assert isinstance(models, list)
    for entry in models:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            return entry["name"]
    pytest.skip(f"Ollama at {host} has no installed models")
    raise AssertionError("unreachable")


def _is_local_ollama_failure(response) -> bool:
    if response.status_code >= 500:
        return True
    try:
        detail = response.json().get("detail")
    except Exception:
        return False
    if not isinstance(detail, dict):
        return False
    return detail.get("code") in {"bad_request", "provider_error", "provider_unavailable"}


@pytest.mark.skipif(not _live_enabled(), reason="AIGW_LIVE=1 not set")
def test_ollama_round_trip_without_profile() -> None:
    host = resolve_ollama_host()
    model = _first_live_model(host)

    with _live_client() as client:
        app = cast(Any, client.app)
        if app.state.settings.auth_enabled:
            _login_admin(client)
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": f"ollama/{model}",
                "messages": [{"role": "user", "content": "Reply with the single word 'pong'."}],
                "max_tokens": 10,
            },
        )

    if response.status_code != 200:
        if _is_local_ollama_failure(response):
            pytest.skip(f"local Ollama model {model!r} failed through gateway: {response.text}")
        assert response.status_code == 200, response.text
    content = response.json()["choices"][0]["message"]["content"]
    assert "pong" in content.lower()
