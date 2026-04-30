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
