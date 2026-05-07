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
from screamingface.plugins.llm_base.routes_shared import (
    BackendApiConfig,
    build_backend_api_router,
)

if TYPE_CHECKING:
    from screamingface.plugins.aigw_claude_backend.plugin import AigwClaudeBackendSettings


_DEFAULT_MODEL = "anthropic/claude-sonnet-4-5"


def create_router(settings: AigwClaudeBackendSettings, app: Any = None) -> APIRouter:
    backend = AigwBackend(
        gateway_url=settings.gateway_url,
        profile_name=settings.auth_profile,
    )

    def build_interpreter() -> Any:
        return AigwInterpreter(app=app, settings=settings, backend=backend)

    router = build_backend_api_router(
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
    router.include_router(
        build_aigw_auth_proxy_router(
            path_prefix="/claude",
            gateway_url=settings.gateway_url,
            gateway_provider="anthropic",
            profile_name=settings.auth_profile,
        )
    )
    return router
