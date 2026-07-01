"""Routes for gemini-backend-api — thin adapter over the shared router factory."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter

from screamingface.plugins.gemini_backend_api.backend import GeminiBackend
from screamingface.plugins.llm_base.routes_shared import (
    BackendApiConfig,
    BackendApiRouteBundle,
    build_backend_api_route_bundle,
)

if TYPE_CHECKING:
    from screamingface.plugins.gemini_backend_api.plugin import GeminiBackendApiSettings


_DEFAULT_MODEL = "gemini-2.5-flash"


def create_route_bundle(
    settings: GeminiBackendApiSettings, app: Any = None
) -> BackendApiRouteBundle:
    from screamingface.plugins.gemini_backend_api.plugin import _maybe_aigw_source

    backend = GeminiBackend(
        fallback_models=list(settings.fallback_models),
        max_total_wait_seconds=settings.max_total_429_wait_seconds,
        aigw_source=_maybe_aigw_source(settings, app),
    )

    def build_interpreter() -> Any:
        from screamingface.plugins.gemini_backend_api.interpreter import (
            GeminiBackendApiInterpreter,
        )

        return GeminiBackendApiInterpreter(app=app, settings=settings, backend=backend)

    return build_backend_api_route_bundle(
        BackendApiConfig(
            name="gemini-backend-api",
            path_prefix="/gemini",
            default_model=_DEFAULT_MODEL,
            backend=backend,
            settings=settings,
            app=app,
            build_interpreter=build_interpreter,
            span_prefix="gemini",
        )
    )


def create_router(settings: GeminiBackendApiSettings, app: Any = None) -> APIRouter:
    return create_route_bundle(settings, app).router
