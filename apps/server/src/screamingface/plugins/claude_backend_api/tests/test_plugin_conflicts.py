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

    def test_conflicts_with_claude_backend(self):
        assert "claude-backend" in ClaudeBackendApiPlugin.conflicts

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
        from screamingface.plugins.claude_backend_api.models import ClaudeProfile

        s = ClaudeBackendApiSettings(
            profiles={
                "default": ClaudeProfile(),
                "code-review": ClaudeProfile(),
                "reviewer_1": ClaudeProfile(),
            }
        )
        assert set(s.profiles.keys()) == {"default", "code-review", "reviewer_1"}

    def test_profile_name_validator_rejects_invalid_names(self):
        import pytest

        from screamingface.plugins.claude_backend_api.models import ClaudeProfile

        # Capitalized
        with pytest.raises(ValueError, match="Invalid profile name"):
            ClaudeBackendApiSettings(profiles={"Default": ClaudeProfile()})

        # Leading dash
        with pytest.raises(ValueError, match="Invalid profile name"):
            ClaudeBackendApiSettings(profiles={"-bad": ClaudeProfile()})

        # Contains period
        with pytest.raises(ValueError, match="Invalid profile name"):
            ClaudeBackendApiSettings(profiles={"a.b": ClaudeProfile()})


class TestEnvPrefixIndependence:
    """Ensure the env prefix is different from claude-backend so the two
    plugins can be configured independently even if both are defined
    (only one will be active, per the conflicts declaration)."""

    def test_env_prefix_differs_from_claude_backend(self):
        # Rebuild the settings class's config to read the prefix
        config = ClaudeBackendApiSettings.model_config
        assert config.get("env_prefix") == "SF_CLAUDE_BACKEND_API__"

    def test_env_prefix_does_not_collide_with_claude_backend(self):
        from screamingface.plugins.claude_backend.plugin import ClaudeBackendSettings

        assert ClaudeBackendApiSettings.model_config.get(
            "env_prefix"
        ) != ClaudeBackendSettings.model_config.get("env_prefix")
