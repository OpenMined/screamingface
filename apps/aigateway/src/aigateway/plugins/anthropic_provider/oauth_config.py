from __future__ import annotations

# Claude Code's public OAuth client lives on platform.claude.com. Verified
# from the official @anthropic-ai/claude-code binary (strings on the bundled
# claude.exe shows /oauth/authorize and /v1/oauth/token paths under
# platform.claude.com — not console.anthropic.com or claude.ai).
# console.anthropic.com/v1/oauth/token does not accept this client_id and
# returns the API "Invalid request format" error; claude.ai/oauth/authorize
# happens to forward to platform.claude.com but the canonical surface is
# platform.claude.com.
ANTHROPIC_AUTHORIZE_URL = "https://platform.claude.com/oauth/authorize"
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
