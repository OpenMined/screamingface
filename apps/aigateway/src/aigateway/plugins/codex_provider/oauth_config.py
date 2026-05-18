from __future__ import annotations

CODEX_AUTH_BASE = "https://auth.openai.com"
CODEX_AUTHORIZE_URL = f"{CODEX_AUTH_BASE}/oauth/authorize"
CODEX_TOKEN_URL = f"{CODEX_AUTH_BASE}/oauth/token"
CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_REDIRECT_PATH = "/auth/callback"
CODEX_REDIRECT_PORTS = [1455, 1457]
CODEX_SCOPES = [
    "openid",
    "profile",
    "email",
    "offline_access",
    "api.connectors.read",
    "api.connectors.invoke",
]
CODEX_AUTHORIZE_EXTRA_PARAMS = {
    "id_token_add_organizations": "true",
    "codex_cli_simplified_flow": "true",
    "originator": "codex_cli_rs",
}
CODEX_REFRESH_SCOPE = "openid profile email"
