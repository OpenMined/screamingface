"""Routes for aigw-gemini-backend."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter

from screamingface.plugins.aigw_base import (
    AigwBackend,
    AigwInterpreter,
    build_aigw_auth_proxy_router,
    build_profile_defaults_from_settings,
)
from screamingface.plugins.llm_base.routes_shared import (
    BackendApiConfig,
    build_backend_api_router,
)

if TYPE_CHECKING:
    from screamingface.plugins.aigw_gemini_backend.plugin import AigwGeminiBackendSettings

_GATEWAY_PROVIDER = "gemini-cli"
_PATH_PREFIX = "/gemini"
_DEFAULT_MODEL = "gemini-cli/gemini-2.5-flash"


def create_router(
    settings: AigwGeminiBackendSettings,
    app: Any = None,
    *,
    backend: AigwBackend | None = None,
) -> APIRouter:
    backend = backend or AigwBackend(
        gateway_url=settings.gateway_url,
        profile_name=settings.auth_profile,
        gateway_provider=_GATEWAY_PROVIDER,
    )

    def build_interpreter() -> Any:
        return AigwInterpreter(
            app=app,
            settings=settings,
            backend=backend,
            gateway_provider=_GATEWAY_PROVIDER,
        )

    router = build_backend_api_router(
        BackendApiConfig(
            name="aigw-gemini-backend",
            path_prefix=_PATH_PREFIX,
            default_model=_DEFAULT_MODEL,
            backend=backend,
            settings=settings,
            app=app,
            build_interpreter=build_interpreter,
            span_prefix="aigw_gemini",
        )
    )
    profile_defaults = build_profile_defaults_from_settings(settings)
    router.include_router(
        build_aigw_auth_proxy_router(
            path_prefix=_PATH_PREFIX,
            gateway_url=settings.gateway_url,
            gateway_provider=_GATEWAY_PROVIDER,
            profile_name=settings.auth_profile,
            defaults=profile_defaults or None,
        )
    )
    return router
