"""Tests that the ABCs actually enforce their contracts.

These tests catch the case where someone adds a new abstract method to
the base class but forgets to implement it in the concrete subclass —
the ABC machinery should refuse to instantiate incomplete subclasses.

Also includes sanity checks that the llm-base plugin itself is loadable
and registers nothing (no routes, no settings).
"""

from __future__ import annotations

import pytest

from screamingface.plugins.llm_base import (
    Adapter,
    AuthStrategy,
    Backend,
    CredentialStore,
)
from screamingface.plugins.llm_base.plugin import LlmBasePlugin


class TestAuthStrategyABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError, match="abstract"):
            AuthStrategy()  # type: ignore[abstract]

    def test_concrete_subclass_instantiates(self):
        class FakeAuth(AuthStrategy):
            async def get_authorization_header(self):
                return {"Authorization": "Bearer fake"}

            async def refresh(self):
                pass

        FakeAuth()  # should not raise


class TestBackendABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError, match="abstract"):
            Backend()  # type: ignore[abstract]

    def test_concrete_subclass_instantiates(self):
        from screamingface.plugins.llm_base.messages import CoreMessage

        class FakeBackend(Backend):
            async def run(
                self,
                messages,
                *,
                model,
                system=None,
                tools=None,
                max_tokens=16000,
                temperature=None,
                timeout_seconds=300.0,
            ):
                return CoreMessage(role="assistant", content="fake")

        FakeBackend()  # should not raise


class TestAdapterABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError, match="abstract"):
            Adapter()  # type: ignore[abstract]

    def test_concrete_subclass_instantiates(self):
        from screamingface.plugins.llm_base.messages import CoreMessage

        class FakeAdapter(Adapter):
            def to_provider_format(
                self,
                messages,
                *,
                model,
                system=None,
                tools=None,
                max_tokens=16000,
                temperature=None,
            ):
                return {"model": model}

            def from_provider_response(self, data):
                return CoreMessage(role="assistant", content="fake")

        FakeAdapter()  # should not raise


class TestCredentialStoreABC:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError, match="abstract"):
            CredentialStore()  # type: ignore[abstract]

    def test_missing_method_still_abstract(self):
        """A subclass that implements only one abstract method still can't instantiate."""

        class HalfStore(CredentialStore):
            def read(self, service, account):
                return None

            # write is NOT implemented

        with pytest.raises(TypeError, match="abstract"):
            HalfStore()  # type: ignore[abstract]


class TestLlmBasePlugin:
    def test_plugin_class_attributes(self):
        assert LlmBasePlugin.name == "llm-base"
        assert LlmBasePlugin.depends == []
        assert LlmBasePlugin.conflicts == []
        assert LlmBasePlugin.settings_class is None

    def test_plugin_instantiates(self):
        LlmBasePlugin()  # no args required

    def test_plugin_preflight_succeeds(self):
        plugin = LlmBasePlugin()
        ok, reason = plugin.preflight()
        assert ok is True
        assert reason == ""

    def test_setup_is_noop(self):
        """setup() takes the standard args and registers nothing."""
        plugin = LlmBasePlugin()
        # Pass None for each arg — llm-base should never touch them
        plugin.setup(None, None, None, None)  # type: ignore[arg-type]
