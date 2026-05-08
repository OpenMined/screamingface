"""Confirms that the aigw-claude-backend plugin mounts the auth-proxy
routes at /claude/auth/{start,status} when its router is built.

We don't drive the upstream gateway here — that's covered by the
auth_proxy unit tests and the e2e test. This guard test only asserts
that the routes exist on the FastAPI app the plugin produces.
"""

from __future__ import annotations

from fastapi import FastAPI
from starlette.routing import Route

from screamingface.plugins.aigw_claude_backend._defaults import (
    _build_profile_defaults_from_settings,
)
from screamingface.plugins.aigw_claude_backend.plugin import (
    AigwClaudeBackendPlugin,
    AigwClaudeBackendSettings,
)
from screamingface.plugins.backend_api_base.models import BackendProfile


def test_aigw_claude_backend_mounts_auth_proxy_routes() -> None:
    app = FastAPI()
    settings = AigwClaudeBackendSettings()
    router = AigwClaudeBackendPlugin.create_router(settings, app=app)
    app.include_router(router)

    paths = {r.path for r in app.routes if isinstance(r, Route)}
    assert "/claude/auth/start" in paths
    assert "/claude/auth/status" in paths
    assert "/claude/auth/profiles" in paths
    assert "/claude/auth/profiles/{name}" in paths


def test_aigw_claude_backend_declares_gateway_provider() -> None:
    assert AigwClaudeBackendPlugin.gateway_provider == "anthropic"


def test_build_profile_defaults_top_level_settings() -> None:
    settings = AigwClaudeBackendSettings(
        default_model="anthropic/claude-sonnet-4-5",
        default_effort="high",
        timeout_seconds=300.0,
    )
    out = _build_profile_defaults_from_settings(settings)
    assert out == {
        "model": "anthropic/claude-sonnet-4-5",
        "timeout_seconds": 300.0,
        "reasoning_effort": "high",
    }


def test_build_profile_defaults_profile_overrides_top_level() -> None:
    settings = AigwClaudeBackendSettings(
        default_model="anthropic/claude-sonnet-4-5",
        default_effort="medium",
        timeout_seconds=300.0,
        default_profile="default",
        profiles={
            "default": BackendProfile(
                model="anthropic/claude-opus-4-7",
                system_prompt="Profile prompt.",
                effort="high",
                timeout_seconds=120.0,
            )
        },
    )
    out = _build_profile_defaults_from_settings(settings)
    assert out == {
        "model": "anthropic/claude-opus-4-7",
        "system_prompt": "Profile prompt.",
        "timeout_seconds": 120.0,
        "reasoning_effort": "high",
    }


def test_build_profile_defaults_drops_max_effort() -> None:
    settings = AigwClaudeBackendSettings(
        default_model="anthropic/claude-sonnet-4-5",
        default_effort="max",
        timeout_seconds=300.0,
    )
    out = _build_profile_defaults_from_settings(settings)
    assert "reasoning_effort" not in out
    # Other fields still present
    assert out["model"] == "anthropic/claude-sonnet-4-5"
    assert out["timeout_seconds"] == 300.0


def test_build_profile_defaults_all_none_returns_empty() -> None:
    # default_model=None, no profiles. timeout_seconds and default_effort have
    # framework defaults; clear them by overriding.
    settings = AigwClaudeBackendSettings(
        default_model=None,
        default_effort="max",  # dropped (not in gateway enum)
    )
    # Bypass framework default for timeout_seconds via direct attribute set
    # — pydantic settings don't allow None there, so we patch the attribute.
    object.__setattr__(settings, "timeout_seconds", None)
    out = _build_profile_defaults_from_settings(settings)
    assert out == {}


def test_aigw_claude_backend_passes_defaults_to_auth_proxy() -> None:
    """End-to-end: SF settings flow through create_router into the gateway POST body."""
    import httpx
    from fastapi.testclient import TestClient

    from screamingface.plugins.aigw_base import auth_proxy_router as apr

    settings = AigwClaudeBackendSettings(
        default_model="anthropic/claude-sonnet-4-5",
        default_effort="medium",
        timeout_seconds=300.0,
    )

    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        import json as _json

        if req.url.path.endswith("/profiles"):
            captured["body"] = _json.loads(req.read().decode())
            return httpx.Response(201, json={"profile_id": "anthropic:default"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    def http_factory(timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=transport, timeout=timeout)

    # Monkey-patch the default factory so the router (constructed inside
    # create_router without an injected factory) uses our MockTransport.
    original = apr._default_http_factory
    apr._default_http_factory = http_factory  # type: ignore[assignment]
    try:
        app = FastAPI()
        router = AigwClaudeBackendPlugin.create_router(settings, app=app)
        app.include_router(router)
        client = TestClient(app)
        resp = client.post("/claude/auth/start")
        assert resp.status_code == 200
    finally:
        apr._default_http_factory = original  # type: ignore[assignment]

    assert captured["body"] == {
        "name": "default",
        "defaults": {
            "model": "anthropic/claude-sonnet-4-5",
            "timeout_seconds": 300.0,
            "reasoning_effort": "medium",
        },
    }
