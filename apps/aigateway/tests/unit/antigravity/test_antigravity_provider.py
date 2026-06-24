"""Unit 2 — Antigravity provider skeleton.

Covers loader discovery, provider id, model seed, OAuth config (loopback
`/oauth2callback` + offline/consent + Antigravity scopes, NO openid), settings
(pinned client_id, public installed-app `client_secret` as a SecretStr default
with optional env override per GATE-2 Option A), and LiteLLM registration under
provider="antigravity" (must not collide with gemini-cli).
"""

from __future__ import annotations

import inspect

import litellm
import pytest

from aigateway.core.loader import load_plugins
from aigateway.core.registry import ProviderRegistry
from aigateway.plugins.antigravity_provider import settings as antigravity_settings_module
from aigateway.plugins.antigravity_provider.settings import (
    ANTIGRAVITY_CLIENT_SECRET,
    AntigravityPluginSettings,
)

# Pinned Antigravity (agy v1.0.10) installed-app client id; see findings §2/U17.
ANTIGRAVITY_CLIENT_ID = "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com"


def test_loader_discovers_antigravity_provider() -> None:
    reg = ProviderRegistry()
    load_plugins(reg)
    plugin = reg.get("antigravity")
    assert plugin is not None
    assert plugin.custom_llm_provider == "antigravity"
    assert plugin.credential_service_provider() == "antigravity"


def test_registers_confirmed_model_seed() -> None:
    reg = ProviderRegistry()
    load_plugins(reg)
    plugin = reg.get("antigravity")
    assert plugin is not None
    models = plugin.register_models()
    names = {m.model_name for m in models}
    # Live-listed seed: verified via fetchAvailableModels + generateContent.
    assert "antigravity/gemini-3-flash" in names
    # Must NOT copy gemini-2.5-* slugs (SF-284 "derive, don't copy").
    assert not any("gemini-2.5" in name for name in names)
    for m in models:
        assert m.litellm_params["model"].startswith("antigravity/")


def test_oauth_config_loopback_and_scopes() -> None:
    reg = ProviderRegistry()
    load_plugins(reg)
    plugin = reg.get("antigravity")
    assert plugin is not None
    cfg = plugin.oauth_config()
    assert cfg is not None
    assert cfg.authorize_url == "https://accounts.google.com/o/oauth2/v2/auth"
    assert cfg.token_url == "https://oauth2.googleapis.com/token"
    assert cfg.client_id == ANTIGRAVITY_CLIENT_ID
    # Reuse gemini's loopback path (probe-confirmed Google validates host only).
    assert cfg.redirect_path == "/oauth2callback"
    # Refresh-token correctness (findings U2): offline + forced consent.
    assert cfg.extra_authorize_params == {"access_type": "offline", "prompt": "consent"}
    # No per-auth loopback listener; uses the normal gateway callback path.
    assert cfg.loopback_redirect_ports is None
    # Antigravity scope set (findings U13): + cclog/experimentsandconfigs, NO openid.
    assert cfg.scopes == [
        "https://www.googleapis.com/auth/cloud-platform",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/cclog",
        "https://www.googleapis.com/auth/experimentsandconfigs",
    ]
    assert not any("openid" in scope for scope in cfg.scopes)


def test_settings_defaults_and_endpoint_fallback() -> None:
    s = AntigravityPluginSettings()
    assert s.client_id == ANTIGRAVITY_CLIENT_ID
    # GATE-2 Option A: public installed-app secret is present by default, like Gemini.
    assert s.client_secret is not None
    assert s.client_secret.get_secret_value() == ANTIGRAVITY_CLIENT_SECRET
    # Code Assist host: daily- primary + prod fallback (findings U12).
    assert s.code_assist_endpoint == "https://daily-cloudcode-pa.googleapis.com"
    assert s.code_assist_fallback_endpoint == "https://cloudcode-pa.googleapis.com"
    assert s.user_agent  # configurable, non-empty


def test_settings_secret_env_override_and_redacted(monkeypatch) -> None:
    monkeypatch.setenv("AIGW_ANTIGRAVITY_CLIENT_SECRET", "GOCSPX-sentinel-not-real")
    s = AntigravityPluginSettings()
    assert s.client_secret is not None
    # SecretStr redacts everywhere except .get_secret_value().
    assert "GOCSPX" not in repr(s.client_secret)
    assert "GOCSPX" not in str(s.client_secret)
    assert "GOCSPX" not in str(s.model_dump())
    assert s.client_secret.get_secret_value() == "GOCSPX-sentinel-not-real"


def test_default_secret_not_serialized_from_settings() -> None:
    """GATE-2 Option A still keeps the public secret out of repr/model dumps."""
    s = AntigravityPluginSettings()
    assert s.client_secret is not None
    assert ANTIGRAVITY_CLIENT_SECRET in inspect.getsource(antigravity_settings_module)
    assert ANTIGRAVITY_CLIENT_SECRET not in repr(s.client_secret)
    assert ANTIGRAVITY_CLIENT_SECRET not in str(s.client_secret)
    assert ANTIGRAVITY_CLIENT_SECRET not in str(s.model_dump())


def test_litellm_registers_under_antigravity_provider() -> None:
    # Importing the plugin module self-registers the handler (defensive map).
    from aigateway.plugins.antigravity_provider import plugin as antigravity_plugin

    antigravity_plugin.ensure_litellm_antigravity_provider_registered()
    providers = {entry.get("provider") for entry in litellm.custom_provider_map}
    assert "antigravity" in providers
    # Must NOT hijack the gemini-cli registration.
    gemini_entries = [e for e in litellm.custom_provider_map if e.get("provider") == "gemini-cli"]
    antigravity_entries = [
        e for e in litellm.custom_provider_map if e.get("provider") == "antigravity"
    ]
    assert len(antigravity_entries) == 1
    # Distinct handler instances per provider (no shared/overwritten handler).
    if gemini_entries:
        assert antigravity_entries[0]["custom_handler"] is not gemini_entries[0]["custom_handler"]


# --- Unit 3 plugin OAuth wiring --------------------------------------------


def _plugin():
    from aigateway.plugins.antigravity_provider.plugin import AntigravityProviderPlugin

    return AntigravityProviderPlugin()


def test_oauth_strategy_for_returns_antigravity_strategy() -> None:
    from aigateway.plugins.antigravity_provider.auth import AntigravityOAuth

    strategy = _plugin().oauth_strategy_for("acct:default")
    assert isinstance(strategy, AntigravityOAuth)
    # U11: strategy namespace matches credential_service_provider().
    assert strategy.credential_service() == "aigateway:antigravity:acct:default"


def test_oauth_strategy_passes_default_secret() -> None:
    from aigateway.plugins.antigravity_provider.auth import AntigravityOAuth

    strategy = _plugin().oauth_strategy_for("default")
    assert isinstance(strategy, AntigravityOAuth)
    assert strategy._client_secret == ANTIGRAVITY_CLIENT_SECRET  # noqa: SLF001


def test_oauth_strategy_passes_env_secret(monkeypatch) -> None:
    from aigateway.plugins.antigravity_provider.auth import AntigravityOAuth

    monkeypatch.setenv("AIGW_ANTIGRAVITY_CLIENT_SECRET", "GOCSPX-env-secret")
    strategy = _plugin().oauth_strategy_for("default")
    # The plugin resolved the env secret into the strategy (private, but the
    # refresh form will carry it — proven indirectly: no missing-secret error).
    assert isinstance(strategy, AntigravityOAuth)
    assert strategy._client_secret == "GOCSPX-env-secret"  # noqa: SLF001


@pytest.mark.asyncio
async def test_exchange_oauth_code_delegates_with_env_secret(monkeypatch) -> None:
    import httpx

    from aigateway.core.plugin_base import OAuthCodeExchangeRequest

    monkeypatch.setenv("AIGW_ANTIGRAVITY_CLIENT_SECRET", "GOCSPX-env-secret")
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(401, json={"error": "no_userinfo"})
        from urllib.parse import parse_qs

        captured["form"] = parse_qs(request.content.decode())
        return httpx.Response(
            200, json={"access_token": "ya29.x", "refresh_token": "r-2", "expires_in": 3600}
        )

    def factory():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=httpx.Timeout(5.0))

    creds = await _plugin().exchange_oauth_code(
        OAuthCodeExchangeRequest(
            code="auth-code",
            code_verifier="verifier",
            redirect_uri="http://localhost:9105/oauth2callback",
            state="state-1",
            http_client_factory=factory,
        )
    )
    assert creds["access_token"] == "ya29.x"
    form = captured["form"]
    assert isinstance(form, dict)
    assert form["client_secret"] == ["GOCSPX-env-secret"]


@pytest.mark.asyncio
async def test_exchange_oauth_code_delegates_with_default_secret() -> None:
    import httpx

    from aigateway.core.plugin_base import OAuthCodeExchangeRequest

    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(401, json={"error": "no_userinfo"})
        from urllib.parse import parse_qs

        captured["form"] = parse_qs(request.content.decode())
        return httpx.Response(
            200, json={"access_token": "ya29.x", "refresh_token": "r-2", "expires_in": 3600}
        )

    def factory():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=httpx.Timeout(5.0))

    creds = await _plugin().exchange_oauth_code(
        OAuthCodeExchangeRequest(
            code="auth-code",
            code_verifier="verifier",
            redirect_uri="http://localhost:9105/oauth2callback",
            state="state-1",
            http_client_factory=factory,
        )
    )
    assert creds["access_token"] == "ya29.x"
    form = captured["form"]
    assert isinstance(form, dict)
    assert form["client_secret"] == [ANTIGRAVITY_CLIENT_SECRET]


@pytest.mark.asyncio
async def test_extract_identity_maps_to_core_account_identity() -> None:
    import base64
    import json as _json

    def _jwt(payload: dict) -> str:
        raw = base64.urlsafe_b64encode(_json.dumps(payload).encode()).rstrip(b"=").decode()
        head = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
        return f"{head}.{raw}.sig"

    identity = await _plugin().extract_identity(
        {"id_token": _jwt({"sub": "s-1", "email": "u@example.com", "name": "U"})}
    )
    assert identity is not None
    assert identity.sub == "s-1"
    assert identity.email == "u@example.com"


def test_account_label_from_credentials_delegates_to_core() -> None:
    label = _plugin().account_label_from_credentials({"account_label": "u@example.com"})
    assert label == "u@example.com"
