"""Antigravity provider settings.

Experimental Google Antigravity provider (D-AIGW-019 / SF-293). It reuses the
Google Code Assist OAuth + Code Assist generation surface but with a distinct
installed-app OAuth client, an extended scope set, and the Antigravity Code
Assist hosts.

GATE-2 (Option B): ``client_secret`` is an OPTIONAL ``SecretStr`` sourced only
from the ``AIGW_ANTIGRAVITY_CLIENT_SECRET`` environment variable. No secret
literal is committed here. The token exchange/refresh requires the public
installed-app secret param (RFC 8252 — not confidential), but per the task
Non-Goal we never commit, print, or document the value; PKCE is the real
protection. Without the env var, the secret is ``None`` and the OAuth
exchange/refresh raises a specific actionable error (handled in auth.py).
"""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import SettingsConfigDict

from aigateway.core.plugin_base import ModelEntry, PluginSettings

# Pinned Antigravity installed-app OAuth client id, extracted from agy v1.0.10
# (findings §2 / U17). Public installed-app identifier, not a secret.
ANTIGRAVITY_CLIENT_ID = "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"

ANTIGRAVITY_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
ANTIGRAVITY_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Reuse Gemini's loopback callback path. A 2026-06-19 probe confirmed Google
# validates only the loopback *host* for this installed-app client (RFC 8252
# §7.3), so reusing /oauth2callback keeps the Desktop loopback policy and
# callback-bridge route unchanged (zero redirect-path delta). See plan §4.1.
ANTIGRAVITY_REDIRECT_PATH = "/oauth2callback"


def _default_scopes() -> list[str]:
    """Antigravity OAuth scopes (findings U13).

    Same three Google Code Assist scopes Gemini uses, plus ``cclog`` and
    ``experimentsandconfigs`` (the only real scope delta), confirmed from the
    agy binary + spec. ``openid`` is intentionally omitted — identity
    extraction works off id_token claims / the userinfo endpoint without it.
    """
    return [
        "https://www.googleapis.com/auth/cloud-platform",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/cclog",
        "https://www.googleapis.com/auth/experimentsandconfigs",
    ]


def _default_authorize_extra_params() -> dict[str, str]:
    """Refresh-token correctness (findings U2).

    ``access_type=offline`` makes Google return a refresh_token;
    ``prompt=consent`` forces re-consent so the refresh_token is reissued.
    Without these every connection dies at ~1h token expiry.
    """
    return {"access_type": "offline", "prompt": "consent"}


def _default_models() -> list[ModelEntry]:
    """Confirmed-served model seed (findings U1).

    Start from the single model agy actually used (``gemini-3.5-flash``). Do
    NOT copy gemini-2.5-* slugs — none were confirmed served by Antigravity,
    and SF-284 mandates deriving model examples from the live ``/v1/models``
    registry rather than hardcoding drift-prone lists. SF's model dropdown
    surfaces these via the gateway registry, not a copied SF list.
    """
    names = ["gemini-3.5-flash"]
    return [
        ModelEntry(
            model_name=f"antigravity/{name}", litellm_params={"model": f"antigravity/{name}"}
        )
        for name in names
    ]


class AntigravityPluginSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIGW_ANTIGRAVITY_",
        extra="ignore",
        populate_by_name=True,
    )

    authorize_url: str = ANTIGRAVITY_AUTHORIZE_URL
    token_url: str = ANTIGRAVITY_TOKEN_URL
    client_id: str = ANTIGRAVITY_CLIENT_ID
    # GATE-2 Option B: env-sourced (AIGW_ANTIGRAVITY_CLIENT_SECRET), never
    # committed. SecretStr redacts in repr/str/model_dump; only the token POST
    # body reads .get_secret_value().
    client_secret: SecretStr | None = None
    scopes: list[str] = Field(default_factory=_default_scopes)
    redirect_path: str = ANTIGRAVITY_REDIRECT_PATH
    authorize_extra_params: dict[str, str] = Field(default_factory=_default_authorize_extra_params)

    # Code Assist hosts (findings U12): daily- primary, prod fallback on 404/5xx.
    code_assist_endpoint: str = "https://daily-cloudcode-pa.googleapis.com"
    code_assist_fallback_endpoint: str = "https://cloudcode-pa.googleapis.com"
    code_assist_api_version: str = "v1internal"

    # Antigravity-specific user agent (configurable; not the Gemini CLI UA).
    user_agent: str = "Antigravity/1.0.10 (aigateway)"

    models: list[ModelEntry] = Field(default_factory=_default_models)
