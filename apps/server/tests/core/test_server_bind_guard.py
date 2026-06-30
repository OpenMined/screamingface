from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig, ServerConfig


def test_server_config_defaults_to_loopback() -> None:
    assert ServerConfig().host == "127.0.0.1"


def test_create_app_rejects_non_loopback_bind_without_override() -> None:
    config = AppConfig(server=ServerConfig(host="0.0.0.0"))

    with pytest.raises(RuntimeError, match="non-loopback"):
        create_app(config)


def test_create_app_rejects_empty_bind_without_override() -> None:
    config = AppConfig(server=ServerConfig(host=""))

    with pytest.raises(RuntimeError, match="non-loopback"):
        create_app(config)


def test_create_app_allows_non_loopback_bind_with_explicit_override(monkeypatch) -> None:
    monkeypatch.setenv("SF_SERVER_ALLOW_LAN", "1")
    config = AppConfig(server=ServerConfig(host="0.0.0.0"))

    app = create_app(config)

    assert TestClient(app).get("/health").status_code == 200


def test_create_app_requires_shared_lan_override_for_non_loopback(monkeypatch) -> None:
    monkeypatch.setenv("SF_BACKEND_API_ALLOW_LAN", "1")
    monkeypatch.setenv("SF_AIGW_ALLOW_LAN", "1")
    config = AppConfig(server=ServerConfig(host="0.0.0.0"))

    with pytest.raises(RuntimeError, match="SF_SERVER_ALLOW_LAN=1"):
        create_app(config)
