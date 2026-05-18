"""Unit tests for the shared backend-api route helpers.

Specifically covers the SF-115 boundary check that rejects CLI-only
fields explicitly at the ``/run`` route.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from screamingface.plugins.backend_api_base.models import RunRequest
from screamingface.plugins.llm_base.backend_base import Backend, HealthStatus
from screamingface.plugins.llm_base.constants import (
    CLI_ONLY_FIELD_DEFAULTS,
    CLI_ONLY_FIELDS,
)
from screamingface.plugins.llm_base.errors import BackendError
from screamingface.plugins.llm_base.messages import CoreMessage, ToolDefinition
from screamingface.plugins.llm_base.routes_shared import (
    BackendApiConfig,
    _reject_cli_only_fields,
    build_backend_api_router,
)


def _default_request(**overrides) -> RunRequest:
    return RunRequest(prompt="hi", **overrides)


def test_default_request_passes() -> None:
    _reject_cli_only_fields(_default_request(), "provider-backend-api")


@pytest.mark.parametrize(
    "field,value",
    [
        ("add_dirs", ["/tmp"]),
        ("mcp_config", "/etc/mcp.json"),
        ("permission_mode", "ask"),
        ("dangerously_skip_permissions", True),
        ("no_session_persistence", False),  # default is True; False is non-default
        ("tools", ["bash"]),
        ("allowed_tools", ["read"]),
        ("disallowed_tools", ["write"]),
    ],
)
def test_each_cli_field_rejected(field: str, value: object) -> None:
    req = _default_request(**{field: value})
    with pytest.raises(HTTPException) as ei:
        _reject_cli_only_fields(req, "provider-backend-api")
    assert ei.value.status_code == 422
    assert field in ei.value.detail
    assert "provider-backend-api" in ei.value.detail


def test_multiple_offending_fields_all_named() -> None:
    req = _default_request(mcp_config="/x", tools=["bash"], permission_mode="ask")
    with pytest.raises(HTTPException) as ei:
        _reject_cli_only_fields(req, "provider-backend-api")
    detail = ei.value.detail
    for f in ("mcp_config", "tools", "permission_mode"):
        assert f in detail


def test_constant_covers_runrequest_defaults() -> None:
    """Defaults map must match the actual RunRequest defaults — guards
    drift if a new CLI-only field is added without updating both."""
    req = _default_request()
    for f in CLI_ONLY_FIELDS:
        assert getattr(req, f) == CLI_ONLY_FIELD_DEFAULTS[f], (
            f"Default mismatch for {f}: model={getattr(req, f)!r} "
            f"vs constant={CLI_ONLY_FIELD_DEFAULTS[f]!r}"
        )


class _RateLimitedBackend(Backend):
    async def health(self, model: str | None = None) -> HealthStatus:  # noqa: ARG002
        return HealthStatus(authenticated=True)

    async def run(
        self,
        messages: list[CoreMessage],  # noqa: ARG002
        *,
        model: str,
        system: str | None = None,  # noqa: ARG002
        tools: list[ToolDefinition] | None = None,  # noqa: ARG002
        max_tokens: int = 16000,  # noqa: ARG002
        temperature: float | None = None,  # noqa: ARG002
        timeout_seconds: float = 300.0,  # noqa: ARG002
    ) -> CoreMessage:
        raise BackendError("rate limited", status=429, retry_after=2.1)


class _FallbackBackend(Backend):
    def __init__(self) -> None:
        self.models: list[str] = []

    async def health(self, model: str | None = None) -> HealthStatus:  # noqa: ARG002
        return HealthStatus(authenticated=True)

    async def run(
        self,
        messages: list[CoreMessage],  # noqa: ARG002
        *,
        model: str,
        system: str | None = None,  # noqa: ARG002
        tools: list[ToolDefinition] | None = None,  # noqa: ARG002
        max_tokens: int = 16000,  # noqa: ARG002
        temperature: float | None = None,  # noqa: ARG002
        timeout_seconds: float = 300.0,  # noqa: ARG002
    ) -> CoreMessage:
        self.models.append(model)
        if model == "primary/model":
            raise BackendError("rate limited", status=429, retry_after=2.1)
        return CoreMessage(role="assistant", content="fallback ok")


class _OkBackend(Backend):
    async def health(self, model: str | None = None) -> HealthStatus:  # noqa: ARG002
        return HealthStatus(authenticated=True)

    async def run(
        self,
        messages: list[CoreMessage],  # noqa: ARG002
        *,
        model: str,
        system: str | None = None,  # noqa: ARG002
        tools: list[ToolDefinition] | None = None,  # noqa: ARG002
        max_tokens: int = 16000,  # noqa: ARG002
        temperature: float | None = None,  # noqa: ARG002
        timeout_seconds: float = 300.0,  # noqa: ARG002
    ) -> CoreMessage:
        return CoreMessage(role="assistant", content="ok")


def test_backend_error_retry_after_becomes_response_header() -> None:
    app = FastAPI()
    settings = SimpleNamespace(default_model=None, timeout_seconds=300.0, profiles={})
    router = build_backend_api_router(
        BackendApiConfig(
            name="test-backend-api",
            path_prefix="/test",
            default_model="test/model",
            backend=_RateLimitedBackend(),
            settings=settings,
            app=app,
            build_interpreter=lambda: None,
            span_prefix="test",
        )
    )
    app.include_router(router)

    resp = TestClient(app).post("/test/run", json={"prompt": "hi"})

    assert resp.status_code == 429
    assert resp.headers["retry-after"] == "3"


def test_run_retries_configured_fallback_model_on_429() -> None:
    app = FastAPI()
    backend = _FallbackBackend()
    settings = SimpleNamespace(
        default_model=None,
        fallback_model="fallback/model",
        timeout_seconds=300.0,
        profiles={},
    )
    router = build_backend_api_router(
        BackendApiConfig(
            name="test-backend-api",
            path_prefix="/test",
            default_model="primary/model",
            backend=backend,
            settings=settings,
            app=app,
            build_interpreter=lambda: None,
            span_prefix="test",
        )
    )
    app.include_router(router)

    resp = TestClient(app).post("/test/run", json={"prompt": "hi"})

    assert resp.status_code == 200
    assert resp.json()["so"] == "fallback ok"
    assert backend.models == ["primary/model", "fallback/model"]


def test_aigw_run_route_rejects_missing_desktop_secret_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("SF_DESKTOP_SECRET", "test-secret")
    app = FastAPI()
    settings = SimpleNamespace(default_model=None, timeout_seconds=300.0, profiles={})
    router = build_backend_api_router(
        BackendApiConfig(
            name="aigw-test-backend",
            path_prefix="/test",
            default_model="test/model",
            backend=_OkBackend(),
            settings=settings,
            app=app,
            build_interpreter=lambda: None,
            span_prefix="test",
        )
    )
    app.include_router(router)
    client = TestClient(app)

    missing = client.post("/test/run", json={"prompt": "hi"})
    allowed = client.post(
        "/test/run",
        json={"prompt": "hi"},
        headers={"X-SF-Desktop-Secret": "test-secret"},
    )

    assert missing.status_code == 401
    assert allowed.status_code == 200
