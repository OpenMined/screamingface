"""Routes for codex-backend-api — thin adapter over the shared router factory."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter

from screamingface.plugins.codex_backend_api.backend import OpenAIBackend
from screamingface.plugins.llm_base.routes_shared import (
    BackendApiConfig,
    BackendApiRouteBundle,
    build_backend_api_route_bundle,
)

if TYPE_CHECKING:
    from screamingface.plugins.codex_backend_api.plugin import CodexBackendApiSettings


_DEFAULT_MODEL = "o4-mini"


def create_route_bundle(
    settings: CodexBackendApiSettings, app: Any = None
) -> BackendApiRouteBundle:
    from screamingface.plugins.codex_backend_api.plugin import _maybe_aigw_source

    backend = OpenAIBackend(aigw_source=_maybe_aigw_source(settings, app))

    def build_interpreter() -> Any:
        from screamingface.plugins.codex_backend_api.interpreter import (
            CodexBackendApiInterpreter,
        )

        return CodexBackendApiInterpreter(app=app, settings=settings, backend=backend)

    return build_backend_api_route_bundle(
        BackendApiConfig(
            name="codex-backend-api",
            path_prefix="/codex",
            default_model=_DEFAULT_MODEL,
            backend=backend,
            settings=settings,
            app=app,
            build_interpreter=build_interpreter,
            span_prefix="codex",
        )
    )


def create_router(settings: CodexBackendApiSettings, app: Any = None) -> APIRouter:
    return create_route_bundle(settings, app).router
