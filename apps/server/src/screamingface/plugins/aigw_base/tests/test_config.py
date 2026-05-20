from __future__ import annotations

from types import SimpleNamespace

from screamingface.plugins.aigw_base.config import resolve_aigw_runtime_config


def _app(plugin_config: dict) -> SimpleNamespace:
    return SimpleNamespace(
        state=SimpleNamespace(
            config=SimpleNamespace(plugin_config=plugin_config),
            plugins=SimpleNamespace(active_plugins={}),
        )
    )


def test_shared_base_gateway_url_wins_over_backend_local_url() -> None:
    config = resolve_aigw_runtime_config(
        _app(
            {
                "aigw-base": {"gateway_url": "https://gateway.example.com", "mode": "external"},
                "aigw-claude-backend": {"gateway_url": "http://127.0.0.1:9105"},
            }
        )
    )

    assert config.mode == "external"
    assert config.gateway_url == "https://gateway.example.com"
    assert not config.gateway_url_conflict


def test_promotes_single_backend_local_gateway_url_for_compatibility() -> None:
    config = resolve_aigw_runtime_config(
        _app({"aigw-claude-backend": {"gateway_url": "http://127.0.0.1:19105/"}})
    )

    assert config.gateway_url == "http://127.0.0.1:19105"
    assert not config.gateway_url_conflict


def test_flags_multiple_backend_local_gateway_urls() -> None:
    config = resolve_aigw_runtime_config(
        _app(
            {
                "aigw-claude-backend": {"gateway_url": "http://127.0.0.1:9105"},
                "aigw-codex-backend": {"gateway_url": "http://127.0.0.1:9106"},
            }
        )
    )

    assert config.gateway_url_conflict


def test_legacy_auth_enabled_infers_external_mode() -> None:
    config = resolve_aigw_runtime_config(_app({"aigw-runner": {"auth_enabled": True}}))

    assert config.mode == "external"
