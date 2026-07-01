"""Routes for aigw-antigravity-backend."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter

from screamingface.plugins.aigw_base import (
    AigwBackend,
    AigwInterpreter,
    build_aigw_auth_proxy_router,
    build_profile_defaults_from_settings,
)
from screamingface.plugins.aigw_base.config import resolve_aigw_runtime_config
from screamingface.plugins.llm_base.routes_shared import (
    BackendApiConfig,
    BackendApiRouteBundle,
    build_backend_api_route_bundle,
)

if TYPE_CHECKING:
    from screamingface.plugins.aigw_antigravity_backend.plugin import (
        AigwAntigravityBackendSettings,
    )

_GATEWAY_PROVIDER = "antigravity"
_PATH_PREFIX = "/antigravity"
_DEFAULT_MODEL = "antigravity/gemini-3-flash"


def create_route_bundle(
    settings: AigwAntigravityBackendSettings,
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
            name="aigw-antigravity-backend",
            path_prefix=_PATH_PREFIX,
            default_model=_DEFAULT_MODEL,
            backend=backend,
            settings=settings,
            app=app,
            build_interpreter=build_interpreter,
            span_prefix="aigw_antigravity",
        )
    )
    router = bundle.router
    profile_defaults = build_profile_defaults_from_settings(settings)
    router.include_router(
        build_aigw_auth_proxy_router(
            path_prefix=_PATH_PREFIX,
            gateway_url=gateway_url,
            gateway_provider=_GATEWAY_PROVIDER,
            profile_name=settings.auth_profile,
            app=app,
            defaults=profile_defaults or None,
        )
    )
    return bundle


def create_router(
    settings: AigwAntigravityBackendSettings,
    app: Any = None,
    *,
    backend: AigwBackend | None = None,
) -> APIRouter:
    return create_route_bundle(settings, app, backend=backend).router


def _gateway_url(app: Any, fallback: str) -> str:
    if app is None:
        return fallback
    return resolve_aigw_runtime_config(app).gateway_url
