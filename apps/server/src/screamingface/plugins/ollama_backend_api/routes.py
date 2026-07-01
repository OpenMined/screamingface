"""Routes for ollama-backend-api — thin adapter over the shared router factory."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter

from screamingface.plugins.llm_base.routes_shared import (
    BackendApiConfig,
    BackendApiRouteBundle,
    build_backend_api_route_bundle,
)
from screamingface.plugins.ollama_backend_api.auth import OllamaAuth
from screamingface.plugins.ollama_backend_api.backend import OllamaBackend

if TYPE_CHECKING:
    from screamingface.plugins.ollama_backend_api.plugin import OllamaBackendApiSettings


_DEFAULT_MODEL = "llama3.2"


def create_route_bundle(
    settings: OllamaBackendApiSettings, app: Any = None
) -> BackendApiRouteBundle:
    backend = OllamaBackend(
        base_url=settings.base_url,
        auth=OllamaAuth(api_key=settings.api_key),
    )

    def build_interpreter() -> Any:
        from screamingface.plugins.ollama_backend_api.interpreter import (
            OllamaBackendApiInterpreter,
        )

        return OllamaBackendApiInterpreter(app=app, settings=settings, backend=backend)

    return build_backend_api_route_bundle(
        BackendApiConfig(
            name="ollama-backend-api",
            path_prefix="/ollama",
            default_model=_DEFAULT_MODEL,
            backend=backend,
            settings=settings,
            app=app,
            build_interpreter=build_interpreter,
            span_prefix="ollama",
        )
    )


def create_router(settings: OllamaBackendApiSettings, app: Any = None) -> APIRouter:
    return create_route_bundle(settings, app).router
