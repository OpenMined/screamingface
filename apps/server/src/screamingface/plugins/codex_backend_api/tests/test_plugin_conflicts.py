"""Tests that the codex-backend-api plugin declares its metadata correctly.

Pure class-attribute checks -- no server, no routes, no FastAPI layer.
"""

from __future__ import annotations

from screamingface.plugins.codex_backend_api.plugin import (
    CodexBackendApiPlugin,
    CodexBackendApiSettings,
)


class TestPluginMetadata:
    def test_name_is_canonical(self):
        assert CodexBackendApiPlugin.name == "codex-backend-api"

    def test_depends_on_llm_base(self):
        assert "llm-base" in CodexBackendApiPlugin.depends

    def test_no_conflicts(self):
        # codex-backend-api coexists with claude-backend-api
        assert CodexBackendApiPlugin.conflicts == []

    def test_backend_call_paths(self):
        assert CodexBackendApiPlugin.backend_call_paths == ["/codex"]

    def test_settings_class_set(self):
        assert CodexBackendApiPlugin.settings_class is CodexBackendApiSettings


class TestSettings:
    def test_default_settings_load_cleanly(self):
        s = CodexBackendApiSettings()
        assert s.default_effort == "medium"
        assert s.timeout_seconds == 300.0
        assert s.profiles == {}
        assert s.interpreter_system_prompt

    def test_profile_name_validator_accepts_valid_names(self):
        from screamingface.plugins.codex_backend_api.models import ClaudeProfile

        s = CodexBackendApiSettings(
            profiles={
                "default": ClaudeProfile(),
                "code-review": ClaudeProfile(),
                "reviewer_1": ClaudeProfile(),
            }
        )
        assert set(s.profiles.keys()) == {"default", "code-review", "reviewer_1"}

    def test_profile_name_validator_rejects_invalid_names(self):
        import pytest

        from screamingface.plugins.codex_backend_api.models import ClaudeProfile

        with pytest.raises(ValueError, match="Invalid profile name"):
            CodexBackendApiSettings(profiles={"Default": ClaudeProfile()})

        with pytest.raises(ValueError, match="Invalid profile name"):
            CodexBackendApiSettings(profiles={"-bad": ClaudeProfile()})

        with pytest.raises(ValueError, match="Invalid profile name"):
            CodexBackendApiSettings(profiles={"a.b": ClaudeProfile()})


class TestEnvPrefixIndependence:
    def test_env_prefix_is_codex(self):
        config = CodexBackendApiSettings.model_config
        assert config.get("env_prefix") == "SF_CODEX_BACKEND_API__"

    def test_env_prefix_differs_from_claude_backend_api(self):
        from screamingface.plugins.claude_backend_api.plugin import ClaudeBackendApiSettings

        assert CodexBackendApiSettings.model_config.get(
            "env_prefix"
        ) != ClaudeBackendApiSettings.model_config.get("env_prefix")

    def test_env_prefix_differs_from_claude_backend(self):
        from screamingface.plugins.claude_backend.plugin import ClaudeBackendSettings

        assert CodexBackendApiSettings.model_config.get(
            "env_prefix"
        ) != ClaudeBackendSettings.model_config.get("env_prefix")
