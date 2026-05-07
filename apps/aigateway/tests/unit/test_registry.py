from __future__ import annotations

import pytest

from aigateway.core.plugin_base import ModelEntry, ProviderPluginBase
from aigateway.core.registry import ProviderRegistry


class _Stub(ProviderPluginBase):
    custom_llm_provider = "stub"

    def register_models(self) -> list[ModelEntry]:
        return [ModelEntry(model_name="stub/m", litellm_params={"model": "stub/m"})]


def test_register_and_lookup() -> None:
    reg = ProviderRegistry()
    plugin = _Stub()
    reg.register(plugin)
    assert reg.get("stub") is plugin
    assert reg.all() == [plugin]


def test_duplicate_registration_raises() -> None:
    reg = ProviderRegistry()
    reg.register(_Stub())
    with pytest.raises(ValueError, match="duplicate provider plugin"):
        reg.register(_Stub())


def test_provider_plugin_base_exposes_oauth_config() -> None:
    """Plugins now declare OAuth provider metadata so the gateway can
    dispatch start/callback without per-provider knowledge in the routes."""
    from aigateway.core.plugin_base import OAuthConfig, ProviderPluginBase

    class P(ProviderPluginBase):
        custom_llm_provider = "stub"

        def register_models(self):
            return []

        def oauth_config(self):
            return OAuthConfig(
                authorize_url="https://stub.example/authorize",
                token_url="https://stub.example/token",
                client_id="cid",
                scopes=["s1"],
                redirect_path="/v1/auth/stub/callback",
            )

    cfg = P().oauth_config()
    assert cfg.authorize_url == "https://stub.example/authorize"
    assert cfg.scopes == ["s1"]


def test_provider_plugin_base_strategy_factory() -> None:
    """oauth_strategy_for(profile_name) returns a per-profile strategy."""
    from aigateway.core.plugin_base import OAuthStrategy, ProviderPluginBase

    class FakeStrat(OAuthStrategy):
        def __init__(self, profile_name: str) -> None:
            self.profile_name = profile_name

        async def get_authorization_header(self):
            return {"Authorization": f"Bearer tok-{self.profile_name}"}

    class P(ProviderPluginBase):
        custom_llm_provider = "stub"

        def register_models(self):
            return []

        def oauth_strategy_for(self, profile_name: str):
            return FakeStrat(profile_name)

    a = P().oauth_strategy_for("work")
    b = P().oauth_strategy_for("personal")
    assert isinstance(a, FakeStrat)
    assert a.profile_name == "work"
    assert b.profile_name == "personal"
