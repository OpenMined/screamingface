from __future__ import annotations

from fastapi import FastAPI
from starlette.routing import Route

from screamingface.plugins.aigw_antigravity_backend.plugin import (
    AigwAntigravityBackendPlugin,
    AigwAntigravityBackendSettings,
)


def test_mounts_browser_auth_proxy_routes_for_antigravity_path() -> None:
    app = FastAPI()
    settings = AigwAntigravityBackendSettings()
    router = AigwAntigravityBackendPlugin.create_router(settings, app=app)
    app.include_router(router)

    routes = {r.path: r for r in app.routes if isinstance(r, Route)}
    assert "/antigravity/auth/start" in routes
    assert "/antigravity/auth/status" in routes
    assert "/antigravity/auth/profiles" in routes
    assert "/antigravity/auth/profiles/{name}" in routes
    assert "/antigravity/auth/exchange-code" in routes
    # Does not collide with the gemini backend's /gemini path.
    assert "/gemini/auth/start" not in routes
