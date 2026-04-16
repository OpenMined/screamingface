"""Request/response/profile models for codex-backend-api.

Re-exports the same wire-format models used by claude-backend-api.
The ensemble fan-out system sends identical request shapes to all
backends, so the models must be byte-for-byte compatible.

If codex ever needs a different wire format, this module becomes the
owning location by defining custom classes here.
"""

from __future__ import annotations

from screamingface.plugins.claude_backend.models import (
    ClaudeProfile,
    ClaudeRunRequest,
    ClaudeRunResponse,
    FileInput,
)

__all__ = [
    "ClaudeProfile",
    "ClaudeRunRequest",
    "ClaudeRunResponse",
    "FileInput",
]
