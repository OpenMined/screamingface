"""Tests for gemini-backend-api plugin metadata."""

from __future__ import annotations

from screamingface.plugins.gemini_backend_api.plugin import (
    GeminiBackendApiPlugin,
    GeminiBackendApiSettings,
)


class TestPluginMetadata:
    def test_name(self):
        assert GeminiBackendApiPlugin.name == "gemini-backend-api"

    def test_depends(self):
        assert "llm-base" in GeminiBackendApiPlugin.depends

    def test_no_conflicts(self):
        assert GeminiBackendApiPlugin.conflicts == []

    def test_backend_call_paths(self):
        assert GeminiBackendApiPlugin.backend_call_paths == ["/gemini"]

    def test_settings_class(self):
        assert GeminiBackendApiPlugin.settings_class is GeminiBackendApiSettings


class TestSettings:
    def test_defaults(self):
        s = GeminiBackendApiSettings()
        assert s.default_effort == "medium"
        assert s.timeout_seconds == 300.0
        assert s.profiles == {}

    def test_env_prefix(self):
        assert GeminiBackendApiSettings.model_config.get("env_prefix") == "SF_GEMINI_BACKEND_API__"

    def test_env_prefix_unique(self):
        from screamingface.plugins.claude_backend_api.plugin import ClaudeBackendApiSettings
        from screamingface.plugins.codex_backend_api.plugin import CodexBackendApiSettings

        gemini_prefix = GeminiBackendApiSettings.model_config.get("env_prefix")
        assert gemini_prefix != ClaudeBackendApiSettings.model_config.get("env_prefix")
        assert gemini_prefix != CodexBackendApiSettings.model_config.get("env_prefix")
