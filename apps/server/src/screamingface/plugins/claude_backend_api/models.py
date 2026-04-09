"""Request/response/profile models for claude-backend-api.

These are **identical** to the models in ``claude_backend/models.py``
by design: the whole point of claude-backend-api is to be a drop-in
replacement for claude-backend, and that means the wire shapes must
be byte-for-byte compatible.

Rather than copy-paste (which would drift), we re-export the classes
directly from claude_backend. This creates a one-way dependency
claude_backend_api → claude_backend at the Python import level, but
NOT at the plugin level (the two plugins still conflict in
``sf.json``). The import works because the claude_backend package is
always present on disk; only its SF Plugin class is disabled when
claude-backend-api is active.

Rationale:

- **Drop-in compat is exact, not approximate.** Every field, every
  alias, every default is guaranteed identical because it's literally
  the same Python class.
- **Tests don't have to re-verify** alias compatibility across the
  two plugins — it's impossible for them to disagree.
- **Future schema changes** happen in exactly one place.

If we ever need to deprecate claude_backend entirely, this module
becomes the owning location by copying the class definitions over.
Until then, forwarding is the right call.
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
