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

    def test_depends_on_backend_api_base(self):
        assert "backend-api-base" in CodexBackendApiPlugin.depends

    def test_conflicts_with_gateway_backed_backend(self):
        assert CodexBackendApiPlugin.conflicts == ["aigw-codex-backend"]

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
        from screamingface.plugins.codex_backend_api.models import BackendProfile

        s = CodexBackendApiSettings(
            profiles={
                "default": BackendProfile(),
                "code-review": BackendProfile(),
                "reviewer_1": BackendProfile(),
            }
        )
        assert set(s.profiles.keys()) == {"default", "code-review", "reviewer_1"}

    def test_profile_name_validator_rejects_invalid_names(self):
        import pytest

        from screamingface.plugins.codex_backend_api.models import BackendProfile

        with pytest.raises(ValueError, match="Invalid profile name"):
            CodexBackendApiSettings(profiles={"Default": BackendProfile()})

        with pytest.raises(ValueError, match="Invalid profile name"):
            CodexBackendApiSettings(profiles={"-bad": BackendProfile()})

        with pytest.raises(ValueError, match="Invalid profile name"):
            CodexBackendApiSettings(profiles={"a.b": BackendProfile()})


class TestEnvPrefix:
    def test_env_prefix_is_codex(self):
        config = CodexBackendApiSettings.model_config
        assert config.get("env_prefix") == "SF_CODEX_BACKEND_API__"

    def test_env_prefix_differs_from_claude_backend_api(self):
        from screamingface.plugins.claude_backend_api.plugin import ClaudeBackendApiSettings

        assert CodexBackendApiSettings.model_config.get(
            "env_prefix"
        ) != ClaudeBackendApiSettings.model_config.get("env_prefix")
