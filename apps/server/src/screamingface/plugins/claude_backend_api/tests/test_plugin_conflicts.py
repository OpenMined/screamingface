"""Tests that the claude-backend-api plugin declares its dependency and
conflict relationships correctly.

These are pure class-attribute checks — they run without starting any
server, touching any routes, or importing the FastAPI layer. Their
purpose is to catch accidental changes to the plugin's static metadata
(depends, conflicts, name) that would silently break operator
expectations.

Actual enforcement of ``conflicts`` happens in the SF plugin loader
(``screamingface.core.registry``). That logic is tested by the loader's
own tests; here we just confirm we declared the right strings.
"""

from __future__ import annotations

from screamingface.plugins.claude_backend_api.plugin import (
    ClaudeBackendApiPlugin,
    ClaudeBackendApiSettings,
)


class TestPluginMetadata:
    def test_name_is_canonical(self):
        assert ClaudeBackendApiPlugin.name == "claude-backend-api"

    def test_depends_on_llm_base(self):
        assert "llm-base" in ClaudeBackendApiPlugin.depends

    def test_depends_on_backend_api_base(self):
        assert "backend-api-base" in ClaudeBackendApiPlugin.depends

    def test_settings_class_set(self):
        assert ClaudeBackendApiPlugin.settings_class is ClaudeBackendApiSettings


class TestSettings:
    def test_default_settings_load_cleanly(self):
        s = ClaudeBackendApiSettings()
        assert s.default_effort == "medium"
        assert s.timeout_seconds == 300.0
        assert s.profiles == {}
        # Default interpreter_system_prompt is non-empty
        assert s.interpreter_system_prompt

    def test_profile_name_validator_accepts_valid_names(self):
        from screamingface.plugins.claude_backend_api.models import BackendProfile

        s = ClaudeBackendApiSettings(
            profiles={
                "default": BackendProfile(),
                "code-review": BackendProfile(),
                "reviewer_1": BackendProfile(),
            }
        )
        assert set(s.profiles.keys()) == {"default", "code-review", "reviewer_1"}

    def test_profile_name_validator_rejects_invalid_names(self):
        import pytest

        from screamingface.plugins.claude_backend_api.models import BackendProfile

        # Capitalized
        with pytest.raises(ValueError, match="Invalid profile name"):
            ClaudeBackendApiSettings(profiles={"Default": BackendProfile()})

        # Leading dash
        with pytest.raises(ValueError, match="Invalid profile name"):
            ClaudeBackendApiSettings(profiles={"-bad": BackendProfile()})

        # Contains period
        with pytest.raises(ValueError, match="Invalid profile name"):
            ClaudeBackendApiSettings(profiles={"a.b": BackendProfile()})


class TestEnvPrefix:
    def test_env_prefix_is_namespaced(self):
        config = ClaudeBackendApiSettings.model_config
        assert config.get("env_prefix") == "SF_CLAUDE_BACKEND_API__"
