"""Ollama auth strategy — optional bearer token, no refresh.

Ollama runs locally by default and accepts unauthenticated requests. For
remote or hardened deployments an optional bearer token can be supplied
via plugin settings (``api_key``) or the ``OLLAMA_API_KEY`` env var. When
no token is configured, no ``Authorization`` header is sent.

This deliberately does **not** inherit the OAuth/keychain/refresh
complexity of ``claude_backend_api.auth.ClaudeCodeOAuth`` or
``codex_backend_api.auth.CodexOAuth`` — Ollama has no token-exchange
flow. The class still implements the :class:`AuthStrategy` ABC so the
backend/adapter/interpreter stack can be shared unchanged.
"""

from __future__ import annotations

import os

from screamingface.plugins.llm_base.auth_base import AuthStrategy


class OllamaAuth(AuthStrategy):
    """Optional-bearer auth for Ollama."""

    def __init__(self, *, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("OLLAMA_API_KEY") or None

    async def get_authorization_header(self) -> dict[str, str]:
        if self._api_key:
            return {"Authorization": f"Bearer {self._api_key}"}
        return {}

    async def refresh(self) -> None:
        return None

    def invalidate_cache(self) -> None:
        return None
