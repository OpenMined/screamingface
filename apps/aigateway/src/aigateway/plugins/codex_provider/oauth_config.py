from __future__ import annotations

import os

CODEX_OAUTH_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_OAUTH_SCOPE = "openid profile email"
CODEX_CHATGPT_API_BASE = "https://chatgpt.com/backend-api/codex"
CODEX_CHATGPT_RESPONSES_URL = f"{CODEX_CHATGPT_API_BASE}/responses"
CODEX_ORIGINATOR = "codex_cli_rs"


def codex_chatgpt_responses_url() -> str:
    """Return the Codex responses endpoint, with a test-only e2e override."""
    return os.getenv("AIGATEWAY_FAKE_CODEX_RESPONSES_URL") or CODEX_CHATGPT_RESPONSES_URL
