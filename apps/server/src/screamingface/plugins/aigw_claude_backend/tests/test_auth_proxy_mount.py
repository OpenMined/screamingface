"""Confirms that the aigw-claude-backend plugin mounts the auth-proxy
routes at /claude/auth/{start,status} when its router is built.

We don't drive the upstream gateway here — that's covered by the
auth_proxy unit tests and the e2e test. This guard test only asserts
that the routes exist on the FastAPI app the plugin produces.
"""

from __future__ import annotations

from fastapi import FastAPI

from screamingface.plugins.aigw_claude_backend.plugin import (
    AigwClaudeBackendPlugin,
    AigwClaudeBackendSettings,
)


def test_aigw_claude_backend_mounts_auth_proxy_routes() -> None:
    app = FastAPI()
    settings = AigwClaudeBackendSettings()
    router = AigwClaudeBackendPlugin.create_router(settings, app=app)
    app.include_router(router)

    paths = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/claude/auth/start" in paths
    assert "/claude/auth/status" in paths


def test_aigw_claude_backend_declares_gateway_provider() -> None:
    assert AigwClaudeBackendPlugin.gateway_provider == "anthropic"
