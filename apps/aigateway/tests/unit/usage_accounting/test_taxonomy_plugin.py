from __future__ import annotations

from typing import Any

import pytest
from fastapi import Request

from aigateway.plugins.taxonomy.plugin import TaxonomyPlugin
from aigateway.plugins.taxonomy.session import begin_accounting
from aigateway.plugins.taxonomy.settings import TaxonomyPluginSettings


class _Handler:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _ProviderContribution:
    custom_llm_provider = "test"

    @staticmethod
    def usage_accounting_strategy():
        from aigateway.plugins.taxonomy import UsageAccountingStrategy

        return UsageAccountingStrategy.litellm_async_http()


def test_taxonomy_is_enabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("AIGW_TAXONOMY_ENABLED", raising=False)

    assert TaxonomyPluginSettings().enabled is True


def test_taxonomy_can_be_disabled_by_environment(monkeypatch) -> None:
    monkeypatch.setenv("AIGW_TAXONOMY_ENABLED", "false")

    assert TaxonomyPluginSettings().enabled is False


@pytest.mark.asyncio
async def test_enabled_plugin_owns_handler_lifecycle() -> None:
    handler = _Handler()
    plugin = TaxonomyPlugin(TaxonomyPluginSettings(enabled=True))

    assert plugin.start(lambda: handler) is handler
    assert plugin.handler is handler

    await plugin.close()

    assert handler.closed is True
    assert plugin.handler is None


def test_disabled_plugin_does_not_create_handler_or_session() -> None:
    plugin = TaxonomyPlugin(TaxonomyPluginSettings(enabled=False))
    calls = 0

    def _build() -> Any:
        nonlocal calls
        calls += 1
        return _Handler()

    assert plugin.start(_build) is None
    request = Request(
        {
            "type": "http",
            "app": type("App", (), {"state": type("State", (), {"taxonomy_plugin": plugin})()})(),
            "headers": [],
        }
    )
    assert (
        begin_accounting(
            request,
            plugin=_ProviderContribution(),
            provider="test",
            model="test/model",
        )
        is None
    )
    assert calls == 0


def test_plugin_snapshots_enablement_without_exposing_mutable_settings() -> None:
    plugin = TaxonomyPlugin(TaxonomyPluginSettings(enabled=True))

    assert plugin.enabled is True
    assert not hasattr(plugin, "settings")


def test_plugin_removes_reserved_metadata_without_mutating_provider_response() -> None:
    plugin = TaxonomyPlugin()
    provider_response = {"id": "msg_1", "_aigw": {"forged": True}}

    sanitized = plugin.sanitize_provider_response(provider_response)

    assert sanitized == {"id": "msg_1"}
    assert provider_response["_aigw"] == {"forged": True}


def test_sanitizer_does_not_execute_provider_dict_subclass_overrides() -> None:
    class _HostileDict(dict[str, object]):
        def __contains__(self, _key: object) -> bool:
            raise RuntimeError("provider override must not run")

        def __iter__(self):
            raise RuntimeError("provider override must not run")

    provider_response = _HostileDict(id="msg_1", _aigw={"forged": True})

    assert TaxonomyPlugin.sanitize_provider_response(provider_response) == {"id": "msg_1"}


def test_taxonomy_needs_no_additional_core_hook_or_signal_modules() -> None:
    from pathlib import Path

    root = Path(__file__).parents[3] / "src/aigateway/core/usage_accounting"
    assert {path.name for path in root.iterdir() if path.is_file()} == {
        "__init__.py",
        "hooks.py",
        "signals.py",
    }
