"""backend-api-base — shared wire-format models for HTTP-facing backend plugins.

This plugin owns the request/response/profile shapes used on every
``*_backend_api`` plugin's ``/run`` endpoint. It is a pure Python
library — no routes, no hooks, no settings. It exists as an SF plugin
only so other plugins can declare ``depends = ["backend-api-base"]``.

See :mod:`llm_base` for provider-agnostic LLM abstractions (CoreMessage,
AuthStrategy, Adapter, Backend). Those are domain-neutral. The types
here are specific to our HTTP wire contract for the direct-API
backends and therefore live in their own module.
"""

from __future__ import annotations

from screamingface.plugins.backend_api_base.models import (
    BackendProfile,
    ClaudeProfile,
    ClaudeRunRequest,
    ClaudeRunResponse,
    FileInput,
    RunRequest,
    RunResponse,
)

__all__ = [
    "BackendProfile",
    "FileInput",
    "RunRequest",
    "RunResponse",
    # Legacy aliases (one-release back-compat)
    "ClaudeProfile",
    "ClaudeRunRequest",
    "ClaudeRunResponse",
]
