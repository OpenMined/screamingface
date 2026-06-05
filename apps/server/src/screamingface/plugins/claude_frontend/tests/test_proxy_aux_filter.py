from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

import screamingface.plugins.claude_frontend.proxy as proxy_mod
from screamingface.plugins.claude_frontend.plugin import ClaudeFrontendSettings
from screamingface.plugins.claude_frontend.proxy import create_router


def _app(*, utility_models: list[str], enabled: bool = True) -> FastAPI:
    settings = ClaudeFrontendSettings(
        active_spec="MainOne",
        utility_models=utility_models,
        filter_auxiliary_requests=enabled,
    )
    plugin = MagicMock()
    plugin.get_active_expression.return_value = "($prompt)!'spec'"
    app = FastAPI()
    app.state.blob_store = None
    app.include_router(create_router(settings, app=app, plugin=plugin, hooks=None))
    return app


def _post(app: FastAPI, body: dict[str, Any]) -> httpx.Response:
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        return client.post("/v1/messages", json=body)


@pytest.fixture
def patched_resolve(monkeypatch):
    mock = AsyncMock(return_value=("RESOLVED-BY-ENSEMBLE", None))
    monkeypatch.setattr(proxy_mod, "resolve_prompt_expression", mock)
    return mock


def test_haiku_aux_probe_synthesized_without_resolution(patched_resolve):
    app = _app(utility_models=["haiku"])
    resp = _post(
        app,
        {
            "model": "claude-haiku-4-5",
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "quota"}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "message" and body["role"] == "assistant"
    assert body["content"][0]["text"] == ""
    patched_resolve.assert_not_called()


def test_haiku_aux_streaming_synthesized_without_resolution(patched_resolve):
    app = _app(utility_models=["haiku"])
    resp = _post(
        app,
        {
            "model": "claude-haiku-4-5",
            "stream": True,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "topic?"}],
        },
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    assert b"message_start" in resp.content and b"message_stop" in resp.content
    patched_resolve.assert_not_called()


def test_haiku_main_loop_turn_reaches_ensemble(patched_resolve):
    app = _app(utility_models=["haiku"])
    resp = _post(
        app,
        {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 1024,
            "system": [{"type": "text", "text": "You are Claude Code, Anthropic's official CLI."}],
            "tools": [{"name": "Bash"}],
            "messages": [{"role": "user", "content": "real question"}],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["content"][0]["text"] == "RESOLVED-BY-ENSEMBLE"
    patched_resolve.assert_awaited_once()


def test_opus_turn_reaches_ensemble(patched_resolve):
    app = _app(utility_models=["haiku"])
    resp = _post(
        app,
        {
            "model": "claude-opus-4-1-20250805",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": "hi"}],
        },
    )
    assert resp.json()["content"][0]["text"] == "RESOLVED-BY-ENSEMBLE"
    patched_resolve.assert_awaited_once()


def test_disabled_filtering_lets_haiku_reach_ensemble(patched_resolve):
    app = _app(utility_models=["haiku"], enabled=False)
    resp = _post(
        app,
        {
            "model": "claude-haiku-4-5",
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "quota"}],
        },
    )
    assert resp.json()["content"][0]["text"] == "RESOLVED-BY-ENSEMBLE"
    patched_resolve.assert_awaited_once()
