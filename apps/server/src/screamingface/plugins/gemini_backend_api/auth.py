"""Gemini CLI auth strategy — reads credentials from the Gemini CLI store.

The Gemini CLI credential location and format are TBD (spike needed).
This module provides a placeholder that checks for GOOGLE_API_KEY /
GEMINI_API_KEY environment variables as the primary auth path.

When the Gemini CLI credential store format is validated, this module
will be updated with file-based reading similar to CodexOAuth.
"""

from __future__ import annotations

import logging
import os

from screamingface.plugins.llm_base.auth_base import AuthStrategy
from screamingface.plugins.llm_base.errors import CredentialNotFoundError

logger = logging.getLogger(__name__)


class GeminiAuth(AuthStrategy):
    """Auth strategy for Google AI Gemini API.

    Priority:
    1. GOOGLE_API_KEY env var
    2. GEMINI_API_KEY env var
    3. (Future) Gemini CLI credential store

    The Google AI API uses ``x-goog-api-key`` header (not Bearer token).
    """

    async def get_authorization_header(self) -> dict[str, str]:
        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise CredentialNotFoundError(
                "No Google AI API key found. Set GOOGLE_API_KEY or GEMINI_API_KEY, "
                "or install and authenticate the Gemini CLI."
            )
        return {"x-goog-api-key": api_key}

    async def refresh(self) -> None:
        # API key auth doesn't need refresh
        pass

    def invalidate_cache(self) -> None:
        pass
