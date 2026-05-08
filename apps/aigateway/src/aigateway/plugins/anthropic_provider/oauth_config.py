from __future__ import annotations

# Authorize URL: claude.ai/oauth/authorize is the user-consent surface
# (the page where the user approves the OAuth request). The Claude Code
# binary points at platform.claude.com but claude.ai forwards there and
# is the cleaner consent UX the user sees.
ANTHROPIC_AUTHORIZE_URL = "https://claude.ai/oauth/authorize"
# Token URL: platform.claude.com/v1/oauth/token — verified from the
# @anthropic-ai/claude-code binary. console.anthropic.com/v1/oauth/token
# (the previous setting) rejects this client_id with the API "Invalid
# request format" error and is NOT the right token endpoint for the
# public Claude Code OAuth client.
ANTHROPIC_TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
ANTHROPIC_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"  # public Claude Code OAuth app
ANTHROPIC_SCOPES = [
    "org:create_api_key",
    "user:profile",
    "user:inference",
    "user:sessions:claude_code",
    "user:mcp_servers",
    "user:file_upload",
]
# Required by the Claude Code OAuth app on /authorize. Without it, the
# server returns a console-admin form instead of the user-consent screen.
ANTHROPIC_AUTHORIZE_EXTRA_PARAMS = {"code": "true"}
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_BETA = ",".join(
    [
        "claude-code-20250219",
        "oauth-2025-04-20",
        "interleaved-thinking-2025-05-14",
        "prompt-caching-scope-2026-01-05",
    ]
)
ANTHROPIC_REDIRECT_PATH = "/v1/auth/anthropic/callback"
