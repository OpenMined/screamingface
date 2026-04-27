"""Shared constants used across ``*_backend_api`` plugins.

Moved here so every direct-API backend plugin uses the same field
list, the same truncation limits, and the same default max-tokens
budget — no more drift between copy-pasted tuples.
"""

from __future__ import annotations

# Fields accepted on RunRequest for drop-in compatibility with the
# Claude CLI / sf.json profiles, but silently dropped by every
# direct-API backend (there is no subprocess to honor them). Recorded
# as OTEL span attributes so the drop stays observable.
CLI_ONLY_FIELDS: tuple[str, ...] = (
    "add_dirs",
    "mcp_config",
    "permission_mode",
    "dangerously_skip_permissions",
    "no_session_persistence",
    "tools",
    "allowed_tools",
    "disallowed_tools",
)

# Default values for each CLI-only field on RunRequest. A request is
# rejected at the route boundary when any of these is set to a value
# other than the default. Kept here (not derived from RunRequest at
# import time) to avoid a circular import between llm_base and
# backend_api_base.
CLI_ONLY_FIELD_DEFAULTS: dict[str, object] = {
    "add_dirs": None,
    "mcp_config": None,
    "permission_mode": None,
    "dangerously_skip_permissions": False,
    "no_session_persistence": True,
    "tools": None,
    "allowed_tools": None,
    "disallowed_tools": None,
}

# Default max_tokens for a single backend run when the caller doesn't
# specify one. Chosen empirically to cover the cookbook examples
# without consuming the whole 200k-token context.
DEFAULT_MAX_TOKENS: int = 16000

# Preview length for OTEL span attributes that carry response bodies
# or long prompt strings. Longer content is truncated and an ellipsis
# footer ``... (N more chars)`` is appended so the consumer knows.
PROMPT_PREVIEW_LIMIT: int = 4000

# Stdout preview length recorded on success spans (shorter than
# PROMPT_PREVIEW_LIMIT because stdout is usually the full model reply
# and 1k chars is enough for dashboards).
STDOUT_PREVIEW_LIMIT: int = 1000
