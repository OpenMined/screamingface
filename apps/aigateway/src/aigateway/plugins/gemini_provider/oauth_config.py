from __future__ import annotations

GEMINI_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GEMINI_TOKEN_URL = "https://oauth2.googleapis.com/token"
GEMINI_CLIENT_ID = "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com"
GEMINI_CLIENT_SECRET = "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"
GEMINI_REDIRECT_PATH = "/oauth2callback"
GEMINI_SCOPES = [
    # Gemini CLI 0.42.0 chunk-DN4XSYRG.js:245649-245652 uses these Code Assist scopes.
    "https://www.googleapis.com/auth/cloud-platform",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]
GEMINI_AUTHORIZE_EXTRA_PARAMS = {
    "access_type": "offline",
    # Google returns refresh_token only on first offline consent unless re-consent is forced.
    "prompt": "consent",
}
