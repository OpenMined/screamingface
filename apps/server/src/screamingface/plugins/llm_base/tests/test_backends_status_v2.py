from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from screamingface.core.app import create_app
from screamingface.core.config import AppConfig
from screamingface.plugins.llm_base import routes as status_routes
from screamingface.plugins.llm_base.routes import STATUS_V2_ACCEPT, create_router


def test_legacy_backends_status_no_auth_required() -> None:
    app = FastAPI()
    app.include_router(create_router(app=None))

    response = TestClient(app).get("/backends/status")

    assert response.status_code == 200
    assert response.json() == {}


def test_status_v2_no_auth_required() -> None:
    app = FastAPI()
    app.include_router(create_router(app=None))

    response = TestClient(app).get("/backends/status", headers={"accept": STATUS_V2_ACCEPT})

    assert response.status_code == 200
    assert response.json()["version"] == 2


def test_health_no_auth_required() -> None:
    app = create_app(AppConfig(plugins=[]))

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_external_auth_disabled_gateway_fails_closed(monkeypatch) -> None:
    async def reachable(_gateway_url: str) -> bool:
        return True

    async def auth_disabled(_gateway_url: str, *, token: str | None) -> int:  # noqa: ARG001
        return 200

    monkeypatch.setattr(status_routes, "_probe_gateway_healthz", reachable)
    monkeypatch.setattr(status_routes, "_probe_gateway_me", auth_disabled)
    app = SimpleNamespace(
        state=SimpleNamespace(
            config=SimpleNamespace(
                plugin_config={
                    "aigw-base": {
                        "mode": "external",
                        "gateway_url": "https://gateway.example.com",
                    }
                }
            ),
            plugins=SimpleNamespace(active_plugins={}),
        )
    )

    payload = await status_routes._build_status_v2(app)

    assert payload["action"] == "gateway_misconfigured"
    assert payload["gateway"]["reachable"] is True
    assert payload["gateway"]["authenticated"] is False
    assert "provider_auth" not in payload
    assert "backends" not in payload


def test_provider_auth_status_exposes_supports_api_key() -> None:
    """The desktop reads supports_api_key per provider to gate the API-key UI."""

    def _plugin(provider, path, *, supports=None):
        ns = SimpleNamespace(
            gateway_provider=provider,
            backend_call_paths=[path],
            settings=SimpleNamespace(auth_profile="default"),
        )
        if supports is not None:
            ns.supports_api_key = supports
        return ns

    app = SimpleNamespace(
        state=SimpleNamespace(
            plugins=SimpleNamespace(
                active_plugins={
                    "claude": _plugin("anthropic", "/claude", supports=True),
                    "gemini": _plugin("gemini-cli", "/gemini", supports=True),
                    "codex": _plugin("codex", "/codex", supports=False),
                    # A plugin that never declares the attr defaults to False.
                    "ollama": _plugin("ollama", "/ollama"),
                }
            )
        )
    )

    providers = status_routes._provider_auth_status(app, {})

    assert providers["claude"]["supports_api_key"] is True
    assert providers["gemini"]["supports_api_key"] is True
    assert providers["codex"]["supports_api_key"] is False
    assert providers["ollama"]["supports_api_key"] is False


def test_create_app_registers_validation_redactor() -> None:
    app = create_app(AppConfig(plugins=[]))
    assert RequestValidationError in app.exception_handlers


@pytest.mark.anyio
async def test_validation_redactor_strips_input() -> None:
    """A 422 must not echo the submitted body (e.g. a raw API key) — SF-291 F1."""
    from pydantic import BaseModel, ValidationError

    from screamingface.core.app import _redact_validation_errors

    class _Body(BaseModel):
        provider: str
        api_key: str

    try:
        _Body.model_validate({"api_key": "sk-secret-XYZ"})
        raise AssertionError("expected validation to fail")
    except ValidationError as err:
        exc = RequestValidationError(err.errors())

    resp = await _redact_validation_errors(None, exc)  # type: ignore[arg-type]
    body = bytes(resp.body)
    assert b"sk-secret-XYZ" not in body
    for entry in json.loads(body)["detail"]:
        assert "input" not in entry
