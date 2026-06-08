"""Tests for the claude-env plugin."""

from __future__ import annotations

import os
import shutil
import subprocess
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
    """Redirect shell_profiles() to a temp file."""
    with patch(
        "screamingface.plugins.claude_env_intercept.shellenv.shell_profiles",
        return_value=[profile_file],
    ):
        yield


# ===================================================================
# shellenv.py tests
# ===================================================================


class TestShellEnv:
    """Tests for shell environment variable management."""

    @pytest.mark.usefixtures("_patch_profile")
    def test_add_exports(self, profile_file: Path) -> None:
        from screamingface.plugins.claude_env_intercept.shellenv import (
            MARKER_BEGIN,
            MARKER_END,
            add_exports,
        )

        add_exports({"ANTHROPIC_BASE_URL": "https://localhost:8000", "FOO": "bar"})
        content = profile_file.read_text()

        assert MARKER_BEGIN in content
        assert MARKER_END in content
        assert 'export ANTHROPIC_BASE_URL="https://localhost:8000"' in content
        assert 'export FOO="bar"' in content
        assert "# existing content" in content

    @pytest.mark.usefixtures("_patch_profile")
    def test_add_exports_idempotent(self, profile_file: Path) -> None:
        from screamingface.plugins.claude_env_intercept.shellenv import MARKER_BEGIN, add_exports

        add_exports({"A": "1"})
        add_exports({"A": "2"})
        content = profile_file.read_text()

        assert content.count(MARKER_BEGIN) == 1
        assert 'export A="2"' in content
        assert 'export A="1"' not in content

    @pytest.mark.usefixtures("_patch_profile")
    def test_remove_exports(self, profile_file: Path) -> None:
        from screamingface.plugins.claude_env_intercept.shellenv import (
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
        from screamingface.plugins.claude_env_intercept.shellenv import remove_exports

        original = profile_file.read_text()
        remove_exports()
        assert profile_file.read_text() == original

    @pytest.mark.usefixtures("_patch_profile")
    def test_has_exports(self) -> None:
        from screamingface.plugins.claude_env_intercept.shellenv import add_exports, has_exports

        assert has_exports() is False
        add_exports({"A": "1"})
        assert has_exports() is True

    @pytest.mark.usefixtures("_patch_profile")
    def test_current_exports(self) -> None:
        from screamingface.plugins.claude_env_intercept.shellenv import add_exports, current_exports

        add_exports({"ANTHROPIC_BASE_URL": "https://localhost:9000", "FOO": "bar"})
        exports = current_exports()

        assert exports == {"ANTHROPIC_BASE_URL": "https://localhost:9000", "FOO": "bar"}

    @pytest.mark.usefixtures("_patch_profile")
    def test_current_exports_empty(self) -> None:
        from screamingface.plugins.claude_env_intercept.shellenv import current_exports

        assert current_exports() == {}

    def test_render_banner_with_spec(self) -> None:
        from screamingface.plugins.claude_env_intercept.shellenv import render_gateway_banner

        out = render_gateway_banner("my-spec", "(https://x/r.txt)!$prompt")
        assert "url4 ensemble gateway" in out
        assert "my-spec" in out
        assert "(https://x/r.txt)!$prompt" in out

    def test_render_banner_no_spec_warns(self) -> None:
        from screamingface.plugins.claude_env_intercept.shellenv import render_gateway_banner

        for name, expr in [(None, None), ("", None), ("x", None)]:
            out = render_gateway_banner(name, expr)
            assert "WARNING" in out
            assert "active url4 spec" in out

    @pytest.mark.parametrize("shell", ["sh", "bash", "zsh"])
    def test_function_prints_banner_to_stderr_and_runs_claude(self, tmp_path, shell) -> None:
        from screamingface.plugins.claude_env_intercept.shellenv import (
            build_claude_banner_function,
            render_gateway_banner,
        )

        if shutil.which(shell) is None:
            pytest.skip(f"{shell} not installed")

        banner = render_gateway_banner("s p e c", "(a|b)!$prompt '\"`x` $(y) ! ()")
        func = build_claude_banner_function(banner)

        bindir = tmp_path / "bin"
        bindir.mkdir()
        fake = bindir / "claude"
        fake.write_text('#!/bin/sh\necho REAL_CLAUDE_RAN "$@"\n')
        fake.chmod(0o755)

        script = f"{func}\nclaude --model x\n"
        env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}"}
        r = subprocess.run([shell, "-c", script], capture_output=True, text=True, env=env)

        assert r.returncode == 0, r.stderr
        assert "REAL_CLAUDE_RAN --model x" in r.stdout
        assert "REAL_CLAUDE_RAN" not in r.stderr
        assert "url4 ensemble gateway" in r.stderr
        assert "$prompt" in r.stderr
        assert "$(y)" in r.stderr

    @pytest.mark.usefixtures("_patch_profile")
    def test_add_exports_with_extra_lines_in_block(self, profile_file) -> None:
        from screamingface.plugins.claude_env_intercept.shellenv import (
            MARKER_BEGIN,
            MARKER_END,
            add_exports,
        )

        add_exports(
            {"ANTHROPIC_BASE_URL": "http://127.0.0.1:9101"}, extra_lines=["claude() { :; }"]
        )
        content = profile_file.read_text()
        assert 'export ANTHROPIC_BASE_URL="http://127.0.0.1:9101"' in content
        assert "claude() { :; }" in content
        assert content.index(MARKER_BEGIN) < content.index("claude() {") < content.index(MARKER_END)

    @pytest.mark.usefixtures("_patch_profile")
    def test_remove_exports_removes_extra_lines(self, profile_file) -> None:
        from screamingface.plugins.claude_env_intercept.shellenv import (
            MARKER_BEGIN,
            add_exports,
            remove_exports,
        )

        add_exports({"A": "1"}, extra_lines=["claude() { :; }"])
        remove_exports()
        content = profile_file.read_text()
        assert MARKER_BEGIN not in content
        assert "claude() {" not in content


# ===================================================================
# plugin.py tests
# ===================================================================


class TestClaudeEnvInterceptPlugin:
    """Tests for the ClaudeEnvInterceptPlugin lifecycle."""

    def test_setup_writes_env_vars(self) -> None:
        from screamingface.plugins.claude_env_intercept.plugin import ClaudeEnvInterceptPlugin

        plugin = ClaudeEnvInterceptPlugin()

        cf_plugin = MagicMock()
        cf_plugin.settings.listen_host = "127.0.0.1"
        cf_plugin.settings.listen_port = 9101

        app = MagicMock()
        app.state.plugins.active_plugins = {"claude-frontend": cf_plugin}
        hooks = MagicMock()

        with (
            patch("screamingface.plugins.claude_env_intercept.plugin.add_exports") as mock_add,
            patch("subprocess.run"),  # launchctl
        ):
            plugin.setup(app, hooks, MagicMock(), MagicMock())

        mock_add.assert_called_once()
        env_vars = mock_add.call_args[0][0]
        assert env_vars["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:9101"
        assert "NODE_EXTRA_CA_CERTS" not in env_vars

        hooks.register.assert_called_once_with(
            "app.shutdown", plugin._on_shutdown, plugin_name="claude-env-intercept"
        )

    def test_setup_raises_when_no_frontend(self) -> None:
        from screamingface.plugins.claude_env_intercept.plugin import ClaudeEnvInterceptPlugin

        plugin = ClaudeEnvInterceptPlugin()

        app = MagicMock()
        app.state.plugins.active_plugins = {}
        hooks = MagicMock()

        with pytest.raises(RuntimeError, match="claude-env-intercept requires claude-frontend"):
            plugin.setup(app, hooks, MagicMock(), MagicMock())

    def test_setup_uses_custom_host_port(self) -> None:
        from screamingface.plugins.claude_env_intercept.plugin import ClaudeEnvInterceptPlugin

        plugin = ClaudeEnvInterceptPlugin()

        cf_plugin = MagicMock()
        cf_plugin.settings.listen_host = "192.168.1.10"
        cf_plugin.settings.listen_port = 9201

        app = MagicMock()
        app.state.plugins.active_plugins = {"claude-frontend": cf_plugin}
        hooks = MagicMock()

        with (
            patch("screamingface.plugins.claude_env_intercept.plugin.add_exports") as mock_add,
            patch("subprocess.run"),
        ):
            plugin.setup(app, hooks, MagicMock(), MagicMock())

        env_vars = mock_add.call_args[0][0]
        assert env_vars["ANTHROPIC_BASE_URL"] == "http://192.168.1.10:9201"

    def test_teardown_removes_exports(self) -> None:
        from screamingface.plugins.claude_env_intercept.plugin import ClaudeEnvInterceptPlugin

        plugin = ClaudeEnvInterceptPlugin()
        with patch(
            "screamingface.plugins.claude_env_intercept.plugin.remove_exports",
        ) as mock_remove:
            plugin.teardown()

        mock_remove.assert_called_once()

    @pytest.mark.anyio
    async def test_on_shutdown_removes_exports(self) -> None:
        from screamingface.plugins.claude_env_intercept.plugin import ClaudeEnvInterceptPlugin

        plugin = ClaudeEnvInterceptPlugin()
        with patch(
            "screamingface.plugins.claude_env_intercept.plugin.remove_exports",
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

        from screamingface.plugins.claude_env_intercept.cli import claude_env_intercept_app

        runner = CliRunner()
        with (
            patch("screamingface.plugins.claude_env_intercept.cli.has_exports", return_value=True),
            patch(
                "screamingface.plugins.claude_env_intercept.cli.current_exports",
                return_value={"ANTHROPIC_BASE_URL": "https://localhost:8000"},
            ),
            patch(
                "screamingface.plugins.claude_env_intercept.cli.shell_profiles",
                return_value=[Path("/fake/.zshrc")],
            ),
        ):
            result = runner.invoke(claude_env_intercept_app, ["status"])

        assert result.exit_code == 0
        assert "ACTIVE" in result.output
        assert "ANTHROPIC_BASE_URL" in result.output

    def test_status_inactive(self) -> None:
        from typer.testing import CliRunner

        from screamingface.plugins.claude_env_intercept.cli import claude_env_intercept_app

        runner = CliRunner()
        with patch(
            "screamingface.plugins.claude_env_intercept.cli.has_exports",
            return_value=False,
        ):
            result = runner.invoke(claude_env_intercept_app, ["status"])

        assert result.exit_code == 0
        assert "INACTIVE" in result.output

    def test_off(self) -> None:
        from typer.testing import CliRunner

        from screamingface.plugins.claude_env_intercept.cli import claude_env_intercept_app

        runner = CliRunner()
        with (
            patch("screamingface.plugins.claude_env_intercept.cli.remove_exports") as mock_remove,
            patch(
                "screamingface.plugins.claude_env_intercept.cli.shell_profiles",
                return_value=[Path("/fake/.zshrc")],
            ),
        ):
            result = runner.invoke(claude_env_intercept_app, ["off"])

        assert result.exit_code == 0
        mock_remove.assert_called_once()


# ===================================================================
# register_cli hook
# ===================================================================


class TestRegisterCLI:
    def test_registers_cli(self) -> None:
        import typer

        from screamingface.plugins.claude_env_intercept.plugin import ClaudeEnvInterceptPlugin

        app = typer.Typer()
        ClaudeEnvInterceptPlugin.register_cli(app)

        group_names = [
            g.typer_instance.info.name  # type: ignore[union-attr]
            for g in app.registered_groups
        ]
        assert "claude-env-intercept" in group_names


class TestSetupBanner:
    @pytest.mark.usefixtures("_patch_profile")
    def test_setup_writes_claude_banner_function(self, profile_file, monkeypatch) -> None:
        from unittest.mock import MagicMock

        import screamingface.plugins.claude_env_intercept.plugin as plg

        monkeypatch.setattr(plg.subprocess, "run", lambda *a, **k: None)

        cf = MagicMock()
        cf.settings.active_spec = "cookbook"
        cf.settings.listen_host = "127.0.0.1"
        cf.settings.listen_port = 9101
        cf.get_active_expression.return_value = "(https://x/r.txt)!$prompt"

        app = MagicMock()
        app.state.plugins.active_plugins.get.return_value = cf

        plugin = plg.ClaudeEnvInterceptPlugin()
        plugin.setup(app, MagicMock(), MagicMock(), MagicMock())

        content = profile_file.read_text()
        assert 'export ANTHROPIC_BASE_URL="http://127.0.0.1:9101"' in content
        assert "claude() {" in content
        assert "cookbook" in content
        assert "$prompt" in content

    @pytest.mark.usefixtures("_patch_profile")
    def test_setup_no_active_spec_warns(self, profile_file, monkeypatch) -> None:
        from unittest.mock import MagicMock

        import screamingface.plugins.claude_env_intercept.plugin as plg

        monkeypatch.setattr(plg.subprocess, "run", lambda *a, **k: None)
        cf = MagicMock()
        cf.settings.active_spec = None
        cf.settings.listen_host = "127.0.0.1"
        cf.settings.listen_port = 9101
        cf.get_active_expression.return_value = None
        app = MagicMock()
        app.state.plugins.active_plugins.get.return_value = cf

        plg.ClaudeEnvInterceptPlugin().setup(app, MagicMock(), MagicMock(), MagicMock())
        content = profile_file.read_text()
        assert "claude() {" in content
        assert "WARNING" in content
