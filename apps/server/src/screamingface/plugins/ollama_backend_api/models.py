"""Request/response schemas for ollama-backend-api.

Re-exports the shared request/response/profile models from
``claude_backend_api.models`` — ollama-backend-api accepts exactly the
same wire shapes on its routes so that sf.json configuration and client
code stay uniform across all *_backend_api plugins.
"""

from __future__ import annotations

from screamingface.plugins.claude_backend_api.models import (
    ClaudeProfile,
    ClaudeRunRequest,
    ClaudeRunResponse,
)

__all__ = ["ClaudeProfile", "ClaudeRunRequest", "ClaudeRunResponse"]
