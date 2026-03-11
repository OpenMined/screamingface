"""Tests for the claude-env plugin."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def profile_file(tmp_path: Path) -> Path:
    """Temp file simulating ~/.zshrc."""
    f = tmp_path / ".zshrc"
    f.write_text("# existing content\n")
    return f


@pytest.fixture
def _patch_profile(profile_file: Path):
    """Redirect shell_profile() to a temp file."""
    with patch(
        "screamingface.plugins.claude_env.shellenv.shell_profile",
        return_value=profile_file,
    ):
        yield


# ===================================================================
# shellenv.py tests
# ===================================================================


class TestShellEnv:
    """Tests for shell environment variable management."""

    @pytest.mark.usefixtures("_patch_profile")
    def test_add_exports(self, profile_file: Path) -> None:
        from screamingface.plugins.claude_env.shellenv import MARKER_BEGIN, MARKER_END, add_exports

        add_exports({"ANTHROPIC_BASE_URL": "https://localhost:8000", "FOO": "bar"})
        content = profile_file.read_text()

        assert MARKER_BEGIN in content
        assert MARKER_END in content
        assert 'export ANTHROPIC_BASE_URL="https://localhost:8000"' in content
        assert 'export FOO="bar"' in content
        assert "# existing content" in content

    @pytest.mark.usefixtures("_patch_profile")
    def test_add_exports_idempotent(self, profile_file: Path) -> None:
        from screamingface.plugins.claude_env.shellenv import MARKER_BEGIN, add_exports

        add_exports({"A": "1"})
        add_exports({"A": "2"})
        content = profile_file.read_text()

        assert content.count(MARKER_BEGIN) == 1
        assert 'export A="2"' in content
        assert 'export A="1"' not in content

    @pytest.mark.usefixtures("_patch_profile")
    def test_remove_exports(self, profile_file: Path) -> None:
        from screamingface.plugins.claude_env.shellenv import (
            MARKER_BEGIN,
            add_exports,
            remove_exports,
        )

        add_exports({"ANTHROPIC_BASE_URL": "https://localhost:8000"})
        assert MARKER_BEGIN in profile_file.read_text()

        remove_exports()
        content = profile_file.read_text()
        assert MARKER_BEGIN not in content
        assert "ANTHROPIC_BASE_URL" not in content
        assert "# existing content" in content

    @pytest.mark.usefixtures("_patch_profile")
    def test_remove_exports_noop(self, profile_file: Path) -> None:
        from screamingface.plugins.claude_env.shellenv import remove_exports

        original = profile_file.read_text()
        remove_exports()
        assert profile_file.read_text() == original

    @pytest.mark.usefixtures("_patch_profile")
    def test_has_exports(self) -> None:
        from screamingface.plugins.claude_env.shellenv import add_exports, has_exports

        assert has_exports() is False
        add_exports({"A": "1"})
        assert has_exports() is True

    @pytest.mark.usefixtures("_patch_profile")
    def test_current_exports(self) -> None:
        from screamingface.plugins.claude_env.shellenv import add_exports, current_exports

        add_exports({"ANTHROPIC_BASE_URL": "https://localhost:9000", "FOO": "bar"})
        exports = current_exports()

        assert exports == {"ANTHROPIC_BASE_URL": "https://localhost:9000", "FOO": "bar"}

    @pytest.mark.usefixtures("_patch_profile")
    def test_current_exports_empty(self) -> None:
        from screamingface.plugins.claude_env.shellenv import current_exports

        assert current_exports() == {}


# ===================================================================
# plugin.py tests
# ===================================================================


class TestClaudeEnvPlugin:
    """Tests for the ClaudeEnvPlugin lifecycle."""

    def test_setup_writes_env_vars(self) -> None:
        from screamingface.plugins.claude_env.plugin import ClaudeEnvPlugin, ClaudeEnvSettings

        plugin = ClaudeEnvPlugin()
        plugin.settings = ClaudeEnvSettings()

        app = MagicMock()
        app.state.config.server.ssl = True
        app.state.config.server.port = 8000
        hooks = MagicMock()
        classes = MagicMock()
        routes = MagicMock()

        with (
            patch(
                "screamingface.plugins.claude_env.plugin._mkcert_ca_root",
                return_value="/fake/rootCA.pem",
            ),
            patch(
                "screamingface.plugins.claude_env.plugin.add_exports"
            ) as mock_add,
            patch("subprocess.run"),  # launchctl
        ):
            plugin.setup(app, hooks, classes, routes)

        mock_add.assert_called_once()
        env_vars = mock_add.call_args[0][0]
        assert env_vars["ANTHROPIC_BASE_URL"] == "https://localhost:8000"
        assert env_vars["NODE_EXTRA_CA_CERTS"] == "/fake/rootCA.pem"

        hooks.register.assert_called_once_with(
            "app.shutdown", plugin._on_shutdown, plugin_name="claude-env"
        )

    def test_setup_custom_base_url(self) -> None:
        from screamingface.plugins.claude_env.plugin import ClaudeEnvPlugin, ClaudeEnvSettings

        plugin = ClaudeEnvPlugin()
        plugin.settings = ClaudeEnvSettings(base_url="https://myhost:9999")

        app = MagicMock()
        hooks = MagicMock()

        with (
            patch(
                "screamingface.plugins.claude_env.plugin._mkcert_ca_root",
                return_value="/fake/rootCA.pem",
            ),
            patch(
                "screamingface.plugins.claude_env.plugin.add_exports"
            ) as mock_add,
            patch("subprocess.run"),
        ):
            plugin.setup(app, hooks, MagicMock(), MagicMock())

        env_vars = mock_add.call_args[0][0]
        assert env_vars["ANTHROPIC_BASE_URL"] == "https://myhost:9999"

    def test_setup_without_ssl(self) -> None:
        from screamingface.plugins.claude_env.plugin import ClaudeEnvPlugin, ClaudeEnvSettings

        plugin = ClaudeEnvPlugin()
        plugin.settings = ClaudeEnvSettings()

        app = MagicMock()
        app.state.config.server.ssl = False
        app.state.config.server.port = 3000
        hooks = MagicMock()

        with (
            patch(
                "screamingface.plugins.claude_env.plugin._mkcert_ca_root",
                return_value=None,
            ),
            patch(
                "screamingface.plugins.claude_env.plugin.add_exports"
            ) as mock_add,
        ):
            plugin.setup(app, hooks, MagicMock(), MagicMock())

        env_vars = mock_add.call_args[0][0]
        assert env_vars["ANTHROPIC_BASE_URL"] == "http://localhost:3000"
        assert "NODE_EXTRA_CA_CERTS" not in env_vars

    def test_teardown_removes_exports(self) -> None:
        from screamingface.plugins.claude_env.plugin import ClaudeEnvPlugin

        plugin = ClaudeEnvPlugin()
        with patch(
            "screamingface.plugins.claude_env.plugin.remove_exports"
        ) as mock_remove:
            plugin.teardown()

        mock_remove.assert_called_once()

    @pytest.mark.anyio
    async def test_on_shutdown_removes_exports(self) -> None:
        from screamingface.plugins.claude_env.plugin import ClaudeEnvPlugin

        plugin = ClaudeEnvPlugin()
        with patch(
            "screamingface.plugins.claude_env.plugin.remove_exports"
        ) as mock_remove:
            await plugin._on_shutdown()

        mock_remove.assert_called_once()


# ===================================================================
# CLI tests
# ===================================================================


class TestClaudeEnvCLI:
    """Tests for sf claude-env status/off CLI commands."""

    def test_status_active(self) -> None:
        from typer.testing import CliRunner

        from screamingface.plugins.claude_env.cli import claude_env_app

        runner = CliRunner()
        with (
            patch(
                "screamingface.plugins.claude_env.cli.has_exports", return_value=True
            ),
            patch(
                "screamingface.plugins.claude_env.cli.current_exports",
                return_value={"ANTHROPIC_BASE_URL": "https://localhost:8000"},
            ),
        ):
            result = runner.invoke(claude_env_app, ["status"])

        assert result.exit_code == 0
        assert "ACTIVE" in result.output
        assert "ANTHROPIC_BASE_URL" in result.output

    def test_status_inactive(self) -> None:
        from typer.testing import CliRunner

        from screamingface.plugins.claude_env.cli import claude_env_app

        runner = CliRunner()
        with patch(
            "screamingface.plugins.claude_env.cli.has_exports", return_value=False
        ):
            result = runner.invoke(claude_env_app, ["status"])

        assert result.exit_code == 0
        assert "INACTIVE" in result.output

    def test_off(self) -> None:
        from typer.testing import CliRunner

        from screamingface.plugins.claude_env.cli import claude_env_app

        runner = CliRunner()
        with patch(
            "screamingface.plugins.claude_env.cli.remove_exports"
        ) as mock_remove:
            result = runner.invoke(claude_env_app, ["off"])

        assert result.exit_code == 0
        mock_remove.assert_called_once()


# ===================================================================
# register_cli hook
# ===================================================================


class TestRegisterCLI:
    def test_registers_cli(self) -> None:
        import typer

        from screamingface.plugins.claude_env.plugin import ClaudeEnvPlugin

        app = typer.Typer()
        ClaudeEnvPlugin.register_cli(app)

        group_names = [
            g.typer_instance.info.name  # type: ignore[union-attr]
            for g in app.registered_groups
        ]
        assert "claude-env" in group_names
