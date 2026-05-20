"""Tests for config resolution: SF_CONFIG env var, --config-json, subprocess mode."""

from __future__ import annotations

import json
import logging
import os

from fastapi import FastAPI

from screamingface.core.app import create_app
from screamingface.core.config import CONFIG_ENV_VAR, AppConfig


def test_config_env_var_constant() -> None:
    assert CONFIG_ENV_VAR == "SF_CONFIG"


def test_create_app_with_direct_config() -> None:
    config = AppConfig(plugins=[])
    app = create_app(config)
    assert isinstance(app, FastAPI)
    assert app.state.config.plugins == []


def test_create_app_suppresses_http_client_request_logs() -> None:
    create_app(AppConfig(plugins=[]))
    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING


def test_create_app_from_runtime_env(monkeypatch) -> None:
    """_SF_RUNTIME_CONFIG env var is consumed by create_app."""
    cfg = AppConfig(plugins=["claude-frontend"], server={"port": 9999})  # type: ignore[arg-type]
    monkeypatch.setenv("_SF_RUNTIME_CONFIG", cfg.model_dump_json())
    app = create_app()
    assert app.state.config.server.port == 9999
    assert app.state.config.plugins == ["claude-frontend"]
    # Env var should be consumed (popped)
    assert os.environ.get("_SF_RUNTIME_CONFIG", "") == ""


def test_subprocess_ready_event(monkeypatch, capsys) -> None:
    """In subprocess mode, create_app emits a JSON ready event during lifespan."""
    monkeypatch.setenv("_SF_SUBPROCESS", "1")
    config = AppConfig(
        plugins=[],
        server={"host": "127.0.0.1", "port": 12345, "ssl": False},  # type: ignore[arg-type]
    )
    app = create_app(config)

    # Trigger lifespan manually
    from fastapi.testclient import TestClient

    with TestClient(app):
        pass  # lifespan runs during context

    captured = capsys.readouterr()
    ready = json.loads(captured.out.strip())
    assert ready["event"] == "ready"
    assert ready["port"] == 12345
    assert ready["host"] == "127.0.0.1"
    assert ready["scheme"] == "http"
    assert "pid" in ready


def test_no_ready_event_without_subprocess_flag(monkeypatch, capsys) -> None:
    """Without _SF_SUBPROCESS, no ready event is emitted."""
    monkeypatch.delenv("_SF_SUBPROCESS", raising=False)
    config = AppConfig(plugins=[])
    app = create_app(config)

    from fastapi.testclient import TestClient

    with TestClient(app):
        pass

    captured = capsys.readouterr()
    assert captured.out == ""
