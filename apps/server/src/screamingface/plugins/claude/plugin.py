"""Shared Claude plugin — common Anthropic types and adapters.

Provides the shared types and adapters that both claude_frontend (proxy)
and claude_backend (CLI wrapper/orchestrator) depend on. No routes or
servers — this is purely a type/adapter library.
"""

from __future__ import annotations

from screamingface.plugin import Plugin


class ClaudePlugin(Plugin):
    name = "claude"
    description = "Shared Claude/Anthropic types, session data, and adapters"
    depends: list[str] = []
