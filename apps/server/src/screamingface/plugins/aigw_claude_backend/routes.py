"""Routes for aigw-claude-backend.

The four endpoints (health, run, url4, profile) come from the shared
build_backend_api_router factory; this module supplies the
gateway-routed pieces (AigwBackend, AigwInterpreter, default model).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter

from screamingface.plugins.aigw_base import (
    AigwBackend,
    AigwInterpreter,
    build_aigw_auth_proxy_router,
)
from screamingface.plugins.aigw_base.config import resolve_aigw_runtime_config
from screamingface.plugins.aigw_claude_backend._defaults import (
    _build_profile_defaults_from_settings,
)
from screamingface.plugins.llm_base.routes_shared import (
    BackendApiConfig,
    BackendApiRouteBundle,
    build_backend_api_route_bundle,
)

if TYPE_CHECKING:
    from screamingface.plugins.aigw_claude_backend.plugin import AigwClaudeBackendSettings


_DEFAULT_MODEL = "anthropic/claude-sonnet-4-5"
_GATEWAY_PROVIDER = "anthropic"


def create_route_bundle(
    settings: AigwClaudeBackendSettings,
    app: Any = None,
    *,
    backend: AigwBackend | None = None,
) -> BackendApiRouteBundle:
    gateway_url = _gateway_url(app, settings.gateway_url)
    backend = backend or AigwBackend(
        gateway_url=gateway_url,
        profile_name=settings.auth_profile,
        gateway_provider=_GATEWAY_PROVIDER,
        app=app,
    )

    def build_interpreter() -> Any:
        return AigwInterpreter(
            app=app,
            settings=settings,
            backend=backend,
            gateway_provider=_GATEWAY_PROVIDER,
        )

    bundle = build_backend_api_route_bundle(
        BackendApiConfig(
            name="aigw-claude-backend",
            path_prefix="/claude",
            default_model=_DEFAULT_MODEL,
            backend=backend,
            settings=settings,
            app=app,
            build_interpreter=build_interpreter,
            span_prefix="aigw_claude",
        )
    )
    router = bundle.router
    profile_defaults = _build_profile_defaults_from_settings(settings)
    router.include_router(
        build_aigw_auth_proxy_router(
            path_prefix="/claude",
            gateway_url=gateway_url,
            gateway_provider=_GATEWAY_PROVIDER,
            profile_name=settings.auth_profile,
            app=app,
            defaults=profile_defaults or None,
        )
    )
    return bundle


def create_router(
    settings: AigwClaudeBackendSettings,
    app: Any = None,
    *,
    backend: AigwBackend | None = None,
) -> APIRouter:
    return create_route_bundle(settings, app, backend=backend).router


def _gateway_url(app: Any, fallback: str) -> str:
    if app is None:
        return fallback
    return resolve_aigw_runtime_config(app).gateway_url
