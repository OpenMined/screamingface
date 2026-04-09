"""Tests for gemini-frontend plugin metadata and settings."""

from __future__ import annotations

import shutil
from unittest.mock import patch

from screamingface.plugins.gemini_frontend.plugin import (
    GeminiFrontendPlugin,
    GeminiFrontendSettings,
)


class TestPluginMetadata:
    def test_name(self):
        assert GeminiFrontendPlugin.name == "gemini-frontend"

    def test_depends(self):
        assert "url4-specs" in GeminiFrontendPlugin.depends

    def test_settings_class(self):
        assert GeminiFrontendPlugin.settings_class is GeminiFrontendSettings


class TestSettings:
    def test_defaults(self):
        s = GeminiFrontendSettings()
        assert s.upstream_url == "https://generativelanguage.googleapis.com"
        assert s.listen_port == 9103
        assert s.listen_host == "127.0.0.1"

    def test_env_prefix(self):
        assert GeminiFrontendSettings.model_config.get("env_prefix") == "SF_GEMINI_FRONTEND__"


class TestPreflight:
    def test_passes_when_gemini_installed(self):
        plugin = GeminiFrontendPlugin()
        with patch.object(shutil, "which", return_value="/usr/bin/gemini"):
            ok, reason = plugin.preflight()
        assert ok is True

    def test_fails_when_gemini_missing(self):
        plugin = GeminiFrontendPlugin()
        with patch.object(shutil, "which", return_value=None):
            ok, reason = plugin.preflight()
        assert ok is False
        assert "gemini cli not found" in reason.lower()
