"""Request/response/profile models for claude-backend-api.

Re-exports the shared wire-format models from :mod:`backend_api_base`.
All ``*_backend_api`` plugins speak the same HTTP contract so the
ensemble fan-out system can send identical request shapes to any
backend.
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
