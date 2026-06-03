"""Routes for claude-backend-api.

Wire-compatible drop-in for ``claude_backend/routes.py``. The four
endpoints (health, run, url4, profile) are produced by the shared
:func:`~screamingface.plugins.llm_base.routes_shared.build_backend_api_router`
factory; this module is the ~15-line adapter that supplies the
Anthropic-specific pieces (backend, interpreter, default model).

CLI-only fields on :class:`RunRequest` (``add_dirs``, ``mcp_config``,
``permission_mode``, ``dangerously_skip_permissions``,
``no_session_persistence``, ``tools``, ``allowed_tools``,
``disallowed_tools``) are silently dropped and recorded as OTEL span
attributes — behavior preserved from the original implementation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter

from screamingface.plugins.claude_backend_api.backend import AnthropicBackend
from screamingface.plugins.llm_base.routes_shared import (
    BackendApiConfig,
    build_backend_api_router,
)

if TYPE_CHECKING:
    from screamingface.plugins.claude_backend_api.plugin import ClaudeBackendApiSettings


_DEFAULT_MODEL = "claude-sonnet-4-6"


def create_router(settings: ClaudeBackendApiSettings, app: Any = None) -> APIRouter:
    from screamingface.plugins.claude_backend_api.plugin import _maybe_aigw_source

    backend = AnthropicBackend(aigw_source=_maybe_aigw_source(settings, app))

    def build_interpreter() -> Any:
        # Lazy import — interpreter imports from this module.
        from screamingface.plugins.claude_backend_api.interpreter import (
            ClaudeBackendApiInterpreter,
        )

        return ClaudeBackendApiInterpreter(app=app, settings=settings, backend=backend)

    return build_backend_api_router(
        BackendApiConfig(
            name="claude-backend-api",
            path_prefix="/claude",
            default_model=_DEFAULT_MODEL,
            backend=backend,
            settings=settings,
            app=app,
            build_interpreter=build_interpreter,
            span_prefix="claude",
        )
    )
