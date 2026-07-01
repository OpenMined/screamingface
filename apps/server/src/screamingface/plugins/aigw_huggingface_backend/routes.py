"""Routes for aigw-huggingface-backend."""

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
    build_backend_api_router,
)

if TYPE_CHECKING:
    from screamingface.plugins.aigw_huggingface_backend.plugin import (
        AigwHuggingfaceBackendSettings,
    )

_GATEWAY_PROVIDER = "huggingface"
_PATH_PREFIX = "/huggingface"
_DEFAULT_MODEL = "huggingface/deepseek-ai/DeepSeek-R1:novita"


def create_router(
    settings: AigwHuggingfaceBackendSettings,
    app: Any = None,
    *,
    backend: AigwBackend | None = None,
) -> APIRouter:
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

    router = build_backend_api_router(
        BackendApiConfig(
            name="aigw-huggingface-backend",
            path_prefix=_PATH_PREFIX,
            default_model=_DEFAULT_MODEL,
            backend=backend,
            settings=settings,
            app=app,
            build_interpreter=build_interpreter,
            span_prefix="aigw_huggingface",
        )
    )
    profile_defaults = build_profile_defaults_from_settings(settings)
    router.include_router(
        build_aigw_auth_proxy_router(
            path_prefix=_PATH_PREFIX,
            gateway_url=gateway_url,
            gateway_provider=_GATEWAY_PROVIDER,
            profile_name=settings.auth_profile,
            app=app,
            defaults=profile_defaults or None,
            # HF is api-key only: the gateway exposes no OAuth/profile auth router,
            # so mount only the (working) api-key connection routes.
            include_oauth_routes=False,
        )
    )
    return router


def _gateway_url(app: Any, fallback: str) -> str:
    if app is None:
        return fallback
    return resolve_aigw_runtime_config(app).gateway_url
