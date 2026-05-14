"""Routes for aigw-codex-backend."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter

from screamingface.plugins.aigw_base import (
    AigwBackend,
    AigwInterpreter,
    build_aigw_auth_proxy_router,
)
from screamingface.plugins.aigw_codex_backend._defaults import (
    _build_profile_defaults_from_settings,
)
from screamingface.plugins.llm_base.routes_shared import (
    BackendApiConfig,
    build_backend_api_router,
)

if TYPE_CHECKING:
    from screamingface.plugins.aigw_codex_backend.plugin import AigwCodexBackendSettings


_DEFAULT_MODEL = "codex/gpt-5.4-mini"


def create_router(settings: AigwCodexBackendSettings, app: Any = None) -> APIRouter:
    backend = AigwBackend(
        gateway_url=settings.gateway_url,
        profile_name=settings.auth_profile,
        gateway_provider="codex",
    )

    def build_interpreter() -> Any:
        return AigwInterpreter(app=app, settings=settings, backend=backend)

    router = build_backend_api_router(
        BackendApiConfig(
            name="aigw-codex-backend",
            path_prefix="/codex",
            default_model=_DEFAULT_MODEL,
            backend=backend,
            settings=settings,
            app=app,
            build_interpreter=build_interpreter,
            span_prefix="aigw_codex",
        )
    )
    profile_defaults = _build_profile_defaults_from_settings(settings)
    router.include_router(
        build_aigw_auth_proxy_router(
            path_prefix="/codex",
            gateway_url=settings.gateway_url,
            gateway_provider="codex",
            profile_name=settings.auth_profile,
            defaults=profile_defaults or None,
            enabled_routes={"status", "profiles", "delete", "import"},
        )
    )
    return router
