"""Tests for codex-frontend plugin metadata and settings."""

from __future__ import annotations

import shutil
from unittest.mock import patch

from screamingface.plugins.codex_frontend.plugin import (
    CodexFrontendPlugin,
    CodexFrontendSettings,
)


class TestPluginMetadata:
    def test_name(self):
        assert CodexFrontendPlugin.name == "codex-frontend"

    def test_depends(self):
        assert "url4-specs" in CodexFrontendPlugin.depends
        assert "url4-executor" in CodexFrontendPlugin.depends

    def test_settings_class(self):
        assert CodexFrontendPlugin.settings_class is CodexFrontendSettings


class TestSettings:
    def test_defaults(self):
        s = CodexFrontendSettings()
        assert s.upstream_url == "https://api.openai.com"
        assert s.listen_port == 9102
        assert s.listen_host == "127.0.0.1"
        assert s.active_spec is None
        assert s.embed_target == "user"
        assert s.embed_mode == "concat"

    def test_env_prefix(self):
        config = CodexFrontendSettings.model_config
        assert config.get("env_prefix") == "SF_CODEX_FRONTEND__"

    def test_env_prefix_differs_from_claude(self):
        from screamingface.plugins.claude_frontend.plugin import ClaudeFrontendSettings

        assert CodexFrontendSettings.model_config.get(
            "env_prefix"
        ) != ClaudeFrontendSettings.model_config.get("env_prefix")


class TestPreflight:
    def test_passes_when_codex_installed(self):
        plugin = CodexFrontendPlugin()
        with patch.object(shutil, "which", return_value="/usr/bin/codex"):
            ok, reason = plugin.preflight()
        assert ok is True
        assert reason == ""

    def test_fails_when_codex_missing(self):
        plugin = CodexFrontendPlugin()
        with patch.object(shutil, "which", return_value=None):
            ok, reason = plugin.preflight()
        assert ok is False
        assert "codex cli not found" in reason.lower()
        assert "npm install" in reason
