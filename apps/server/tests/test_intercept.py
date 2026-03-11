"""End-to-end tests for the intercept plugin."""

from __future__ import annotations

import json
import os
import socket
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    """Temp directory for intercept state file."""
    return tmp_path / "screamingface"


@pytest.fixture
def state_file(state_dir: Path) -> Path:
    return state_dir / "intercept-state.json"


@pytest.fixture
def _patch_state_file(state_file: Path):
    """Redirect STATE_FILE to a temp path for all state tests."""
    with patch("screamingface.plugins.intercept.state.STATE_FILE", state_file):
        yield


@pytest.fixture
def hosts_file(tmp_path: Path) -> Path:
    """Temp file simulating /etc/hosts."""
    f = tmp_path / "hosts"
    f.write_text(textwrap.dedent("""\
        127.0.0.1 localhost
        255.255.255.255 broadcasthost
        ::1 localhost
    """))
    return f


@pytest.fixture
def _patch_hosts_file(hosts_file: Path):
    """Redirect HOSTS_FILE and disable sudo writes for hosts tests."""
    with (
        patch("screamingface.plugins.intercept.hosts.HOSTS_FILE", hosts_file),
        patch(
            "screamingface.plugins.intercept.hosts._write_hosts",
            side_effect=lambda content: hosts_file.write_text(content),
        ),
    ):
        yield


# ===================================================================
# state.py tests
# ===================================================================


class TestState:
    """Tests for intercept state persistence and crash recovery."""

    @pytest.mark.usefixtures("_patch_state_file")
    def test_save_and_load_roundtrip(self, state_file: Path) -> None:
        from screamingface.plugins.intercept.state import InterceptState, load_state, save_state

        state = InterceptState(
            active=True,
            activated_at="2026-01-01T00:00:00+00:00",
            domains=["api.anthropic.com"],
            original_hosts_hash="abc123",
            pid=12345,
        )
        save_state(state)
        assert state_file.exists()

        loaded = load_state()
        assert loaded is not None
        assert loaded.active is True
        assert loaded.domains == ["api.anthropic.com"]
        assert loaded.pid == 12345

    @pytest.mark.usefixtures("_patch_state_file")
    def test_load_returns_none_when_missing(self) -> None:
        from screamingface.plugins.intercept.state import load_state

        assert load_state() is None

    @pytest.mark.usefixtures("_patch_state_file")
    def test_load_returns_none_on_corrupt_json(self, state_file: Path) -> None:
        from screamingface.plugins.intercept.state import load_state

        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text("not valid json{{{")
        assert load_state() is None

    @pytest.mark.usefixtures("_patch_state_file")
    def test_load_returns_none_on_missing_fields(self, state_file: Path) -> None:
        from screamingface.plugins.intercept.state import load_state

        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps({"active": True}))  # missing fields
        assert load_state() is None

    @pytest.mark.usefixtures("_patch_state_file")
    def test_clear_state(self, state_file: Path) -> None:
        from screamingface.plugins.intercept.state import InterceptState, clear_state, save_state

        save_state(InterceptState(
            active=True,
            activated_at="2026-01-01T00:00:00+00:00",
            domains=["api.anthropic.com"],
            original_hosts_hash="abc",
            pid=os.getpid(),
        ))
        assert state_file.exists()
        clear_state()
        assert not state_file.exists()

    @pytest.mark.usefixtures("_patch_state_file")
    def test_clear_state_noop_when_missing(self) -> None:
        from screamingface.plugins.intercept.state import clear_state

        clear_state()  # should not raise

    @pytest.mark.usefixtures("_patch_state_file")
    def test_is_stale_with_dead_pid(self, state_file: Path) -> None:
        from screamingface.plugins.intercept.state import InterceptState, is_stale, save_state

        save_state(InterceptState(
            active=True,
            activated_at="2026-01-01T00:00:00+00:00",
            domains=["api.anthropic.com"],
            original_hosts_hash="abc",
            pid=999999999,  # almost certainly dead
        ))
        assert is_stale() is True

    @pytest.mark.usefixtures("_patch_state_file")
    def test_is_stale_with_live_pid(self, state_file: Path) -> None:
        from screamingface.plugins.intercept.state import InterceptState, is_stale, save_state

        save_state(InterceptState(
            active=True,
            activated_at="2026-01-01T00:00:00+00:00",
            domains=["api.anthropic.com"],
            original_hosts_hash="abc",
            pid=os.getpid(),  # this process is alive
        ))
        assert is_stale() is False

    @pytest.mark.usefixtures("_patch_state_file")
    def test_is_stale_no_state(self) -> None:
        from screamingface.plugins.intercept.state import is_stale

        assert is_stale() is False

    @pytest.mark.usefixtures("_patch_state_file")
    def test_is_stale_inactive_state(self, state_file: Path) -> None:
        from screamingface.plugins.intercept.state import InterceptState, is_stale, save_state

        save_state(InterceptState(
            active=False,
            activated_at="2026-01-01T00:00:00+00:00",
            domains=[],
            original_hosts_hash="abc",
            pid=999999999,
        ))
        assert is_stale() is False


# ===================================================================
# hosts.py tests
# ===================================================================


class TestHosts:
    """Tests for /etc/hosts marker-based manipulation."""

    @pytest.mark.usefixtures("_patch_hosts_file")
    def test_add_entries(self, hosts_file: Path) -> None:
        from screamingface.plugins.intercept.hosts import MARKER_BEGIN, MARKER_END, add_entries

        add_entries(["api.anthropic.com"])
        content = hosts_file.read_text()
        assert MARKER_BEGIN in content
        assert "127.0.0.1 api.anthropic.com" in content
        assert MARKER_END in content
        # Original content preserved
        assert "127.0.0.1 localhost" in content

    @pytest.mark.usefixtures("_patch_hosts_file")
    def test_add_multiple_domains(self, hosts_file: Path) -> None:
        from screamingface.plugins.intercept.hosts import add_entries

        add_entries(["api.anthropic.com", "api.openai.com"])
        content = hosts_file.read_text()
        assert "127.0.0.1 api.anthropic.com" in content
        assert "127.0.0.1 api.openai.com" in content

    @pytest.mark.usefixtures("_patch_hosts_file")
    def test_add_custom_target_ip(self, hosts_file: Path) -> None:
        from screamingface.plugins.intercept.hosts import add_entries

        add_entries(["api.anthropic.com"], target="10.0.0.1")
        content = hosts_file.read_text()
        assert "10.0.0.1 api.anthropic.com" in content

    @pytest.mark.usefixtures("_patch_hosts_file")
    def test_add_entries_idempotent(self, hosts_file: Path) -> None:
        from screamingface.plugins.intercept.hosts import MARKER_BEGIN, add_entries

        add_entries(["api.anthropic.com"])
        add_entries(["api.anthropic.com"])
        content = hosts_file.read_text()
        # Only one marker block
        assert content.count(MARKER_BEGIN) == 1

    @pytest.mark.usefixtures("_patch_hosts_file")
    def test_remove_entries(self, hosts_file: Path) -> None:
        from screamingface.plugins.intercept.hosts import (
            MARKER_BEGIN,
            add_entries,
            remove_entries,
        )

        add_entries(["api.anthropic.com"])
        assert MARKER_BEGIN in hosts_file.read_text()

        remove_entries()
        content = hosts_file.read_text()
        assert MARKER_BEGIN not in content
        assert "api.anthropic.com" not in content
        # Original content preserved
        assert "127.0.0.1 localhost" in content

    @pytest.mark.usefixtures("_patch_hosts_file")
    def test_remove_entries_noop_when_missing(self, hosts_file: Path) -> None:
        from screamingface.plugins.intercept.hosts import remove_entries

        original = hosts_file.read_text()
        remove_entries()  # should not raise
        assert hosts_file.read_text() == original

    @pytest.mark.usefixtures("_patch_hosts_file")
    def test_has_entries(self, hosts_file: Path) -> None:
        from screamingface.plugins.intercept.hosts import add_entries, has_entries

        assert has_entries() is False
        add_entries(["api.anthropic.com"])
        assert has_entries() is True

    @pytest.mark.usefixtures("_patch_hosts_file")
    def test_strip_preserves_surrounding_content(self, hosts_file: Path) -> None:
        from screamingface.plugins.intercept.hosts import add_entries, remove_entries

        # Add custom content after original
        original = hosts_file.read_text()
        hosts_file.write_text(original + "10.0.0.1 myhost.local\n")

        add_entries(["api.anthropic.com"])
        remove_entries()
        content = hosts_file.read_text()
        assert "127.0.0.1 localhost" in content
        assert "10.0.0.1 myhost.local" in content
        assert "api.anthropic.com" not in content


# ===================================================================
# certs.py tests
# ===================================================================


class TestCerts:
    """Tests for intercept cert generation."""

    def test_ensure_intercept_certs_calls_mkcert(self) -> None:
        from screamingface.plugins.intercept.certs import ensure_intercept_certs

        with (
            patch("screamingface.plugins.intercept.certs.ensure_mkcert_installed"),
            patch("screamingface.plugins.intercept.certs.ensure_ca_installed"),
            patch("screamingface.plugins.intercept.certs.DEFAULT_CERT_DIR") as mock_dir,
            patch("subprocess.run") as mock_run,
        ):
            mock_dir.mkdir = MagicMock()
            mock_dir.__truediv__ = lambda self, name: Path(f"/fake/certs/{name}")

            cert, key = ensure_intercept_certs(["api.anthropic.com"])

            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert cmd[0] == "mkcert"
            assert "localhost" in cmd
            assert "127.0.0.1" in cmd
            assert "api.anthropic.com" in cmd

    def test_ensure_intercept_certs_multiple_domains(self) -> None:
        from screamingface.plugins.intercept.certs import ensure_intercept_certs

        with (
            patch("screamingface.plugins.intercept.certs.ensure_mkcert_installed"),
            patch("screamingface.plugins.intercept.certs.ensure_ca_installed"),
            patch("screamingface.plugins.intercept.certs.DEFAULT_CERT_DIR") as mock_dir,
            patch("subprocess.run") as mock_run,
        ):
            mock_dir.mkdir = MagicMock()
            mock_dir.__truediv__ = lambda self, name: Path(f"/fake/certs/{name}")

            ensure_intercept_certs(["api.anthropic.com", "api.openai.com"])

            cmd = mock_run.call_args[0][0]
            assert "api.anthropic.com" in cmd
            assert "api.openai.com" in cmd


# ===================================================================
# plugin.py tests — full lifecycle
# ===================================================================


class TestInterceptPlugin:
    """Tests for the InterceptPlugin orchestrator."""

    def test_preflight_passes_when_mkcert_available(self) -> None:
        from screamingface.plugins.intercept.plugin import InterceptPlugin, InterceptSettings

        plugin = InterceptPlugin()
        plugin.settings = InterceptSettings()
        with patch("shutil.which", return_value="/usr/local/bin/mkcert"):
            ok, reason = plugin.preflight()
        assert ok is True
        assert reason == ""

    def test_preflight_fails_when_mkcert_missing(self) -> None:
        from screamingface.plugins.intercept.plugin import InterceptPlugin, InterceptSettings

        plugin = InterceptPlugin()
        plugin.settings = InterceptSettings()
        with patch("shutil.which", return_value=None):
            ok, reason = plugin.preflight()
        assert ok is False
        assert "mkcert" in reason

    def test_preflight_auto_cleans_stale_state(self) -> None:
        from screamingface.plugins.intercept.plugin import InterceptPlugin, InterceptSettings

        plugin = InterceptPlugin()
        plugin.settings = InterceptSettings(auto_cleanup=True)
        with (
            patch("shutil.which", return_value="/usr/local/bin/mkcert"),
            patch("screamingface.plugins.intercept.plugin.is_stale", return_value=True),
            patch("screamingface.plugins.intercept.plugin._cleanup_stale") as mock_cleanup,
        ):
            ok, reason = plugin.preflight()
        assert ok is True
        mock_cleanup.assert_called_once()

    def test_preflight_fails_on_stale_without_auto_cleanup(self) -> None:
        from screamingface.plugins.intercept.plugin import InterceptPlugin, InterceptSettings

        plugin = InterceptPlugin()
        plugin.settings = InterceptSettings(auto_cleanup=False)
        with (
            patch("shutil.which", return_value="/usr/local/bin/mkcert"),
            patch("screamingface.plugins.intercept.plugin.is_stale", return_value=True),
        ):
            ok, reason = plugin.preflight()
        assert ok is False
        assert "Stale" in reason

    def test_setup_full_lifecycle(self) -> None:
        """Test the full setup: DNS resolve → certs → hosts → pfctl → state → hook."""
        from screamingface.plugins.intercept.plugin import InterceptPlugin, InterceptSettings

        plugin = InterceptPlugin()
        plugin.settings = InterceptSettings(domains=["api.anthropic.com"], server_port=8000)

        app = MagicMock()
        app.state = MagicMock()
        hooks = MagicMock()
        classes = MagicMock()
        routes = MagicMock()

        fake_addr = [(2, 1, 6, "", ("93.184.216.34", 443))]

        with (
            patch("socket.getaddrinfo", return_value=fake_addr),
            patch("screamingface.plugins.intercept.plugin.dns") as mock_dns,
            patch(
                "screamingface.plugins.intercept.plugin.ensure_intercept_certs",
                return_value=(Path("/fake/cert.pem"), Path("/fake/key.pem")),
            ),
            patch("screamingface.plugins.intercept.plugin.ensure_node_trusts_ca"),
            patch("screamingface.plugins.intercept.plugin.add_entries") as mock_add,
            patch("screamingface.plugins.intercept.plugin.flush_dns") as mock_flush,
            patch("screamingface.plugins.intercept.plugin.save_state") as mock_save,
            patch("screamingface.plugins.intercept.plugin.hosts_hash", return_value="abc"),
            patch("screamingface.plugins.intercept.plugin.now_iso", return_value="2026-01-01"),
            patch("subprocess.run"),  # pfctl
        ):
            plugin.setup(app, hooks, classes, routes)

        # DNS override installed with real IPs
        mock_dns.install.assert_called_once_with({"api.anthropic.com": "93.184.216.34"})

        # Certs stored on app.state
        assert app.state.intercept_cert == Path("/fake/cert.pem")
        assert app.state.intercept_key == Path("/fake/key.pem")
        # Hosts modified
        mock_add.assert_called_once_with(["api.anthropic.com"], "127.0.0.1")
        mock_flush.assert_called_once()
        # State saved
        mock_save.assert_called_once()
        saved_state = mock_save.call_args[0][0]
        assert saved_state.active is True
        assert saved_state.domains == ["api.anthropic.com"]
        # Shutdown hook registered
        hooks.register.assert_called_once_with(
            "app.shutdown", plugin._on_shutdown, plugin_name="intercept"
        )

    def test_teardown_cleans_up(self) -> None:
        from screamingface.plugins.intercept.plugin import InterceptPlugin

        plugin = InterceptPlugin()
        with (
            patch("screamingface.plugins.intercept.plugin.dns") as mock_dns,
            patch("screamingface.plugins.intercept.plugin.remove_entries") as mock_remove,
            patch("screamingface.plugins.intercept.plugin.flush_dns") as mock_flush,
            patch("screamingface.plugins.intercept.plugin.clear_state") as mock_clear,
            patch("subprocess.run"),  # pfctl -d
        ):
            plugin.teardown()

        mock_dns.uninstall.assert_called_once()
        mock_remove.assert_called_once()
        mock_flush.assert_called_once()
        mock_clear.assert_called_once()

    @pytest.mark.anyio
    async def test_on_shutdown_cleans_up(self) -> None:
        from screamingface.plugins.intercept.plugin import InterceptPlugin

        plugin = InterceptPlugin()
        with (
            patch("screamingface.plugins.intercept.plugin.dns") as mock_dns,
            patch("screamingface.plugins.intercept.plugin.remove_entries") as mock_remove,
            patch("screamingface.plugins.intercept.plugin.flush_dns") as mock_flush,
            patch("screamingface.plugins.intercept.plugin.clear_state") as mock_clear,
            patch("subprocess.run"),  # pfctl -d
        ):
            await plugin._on_shutdown()

        mock_dns.uninstall.assert_called_once()
        mock_remove.assert_called_once()
        mock_flush.assert_called_once()
        mock_clear.assert_called_once()

    def test_setup_port_forward_calls_pfctl(self) -> None:
        from screamingface.plugins.intercept.plugin import InterceptPlugin

        plugin = InterceptPlugin()
        with patch("subprocess.run") as mock_run:
            plugin._setup_port_forward(8000)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["sudo", "pfctl", "-ef", "-"]
        stdin = mock_run.call_args[1]["input"]
        assert b"port 443" in stdin
        assert b"port 8000" in stdin

    def test_teardown_port_forward_calls_pfctl(self) -> None:
        from screamingface.plugins.intercept.plugin import InterceptPlugin

        with patch("subprocess.run") as mock_run:
            InterceptPlugin._teardown_port_forward()

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["sudo", "pfctl", "-d"]

    def test_cleanup_stale(self) -> None:
        from screamingface.plugins.intercept.plugin import InterceptPlugin, _cleanup_stale
        from screamingface.plugins.intercept.state import InterceptState

        state = InterceptState(
            active=True,
            activated_at="2026-01-01",
            domains=["api.anthropic.com"],
            original_hosts_hash="abc",
            pid=999999999,
        )
        with (
            patch("screamingface.plugins.intercept.plugin.load_state", return_value=state),
            patch("screamingface.plugins.intercept.plugin.remove_entries") as mock_remove,
            patch("screamingface.plugins.intercept.plugin.flush_dns") as mock_flush,
            patch("screamingface.plugins.intercept.plugin.clear_state") as mock_clear,
            patch.object(InterceptPlugin, "_teardown_port_forward") as mock_pfctl,
        ):
            _cleanup_stale()

        mock_remove.assert_called_once()
        mock_flush.assert_called_once()
        mock_pfctl.assert_called_once()
        mock_clear.assert_called_once()


# ===================================================================
# dns.py tests — process-local DNS override
# ===================================================================


class TestDNSOverride:
    """Test the socket.getaddrinfo monkey-patch for routing loop avoidance."""

    def test_install_overrides_getaddrinfo(self) -> None:
        """After install(), getaddrinfo returns real IP for intercepted domains."""
        from screamingface.plugins.intercept import dns

        original = socket.getaddrinfo
        try:
            dns.install({"example.com": "93.184.216.34"})

            # Intercepted domain should resolve to the real IP
            results = socket.getaddrinfo("example.com", 443, socket.AF_INET)
            resolved_ip = results[0][4][0]
            assert resolved_ip == "93.184.216.34"
        finally:
            dns.uninstall()
            assert socket.getaddrinfo is original

    def test_non_intercepted_domain_unchanged(self) -> None:
        """Domains not in the override map resolve normally."""
        from screamingface.plugins.intercept import dns

        try:
            dns.install({"example.com": "93.184.216.34"})

            # localhost should still resolve normally
            results = socket.getaddrinfo("localhost", 80, socket.AF_INET)
            resolved_ip = results[0][4][0]
            assert resolved_ip == "127.0.0.1"
        finally:
            dns.uninstall()

    def test_uninstall_restores_original(self) -> None:
        """After uninstall(), getaddrinfo is the original function."""
        from screamingface.plugins.intercept import dns

        original = socket.getaddrinfo
        dns.install({"example.com": "1.2.3.4"})
        assert socket.getaddrinfo is not original

        dns.uninstall()
        assert socket.getaddrinfo is original

    def test_install_idempotent(self) -> None:
        """Calling install() twice doesn't stack patches."""
        from screamingface.plugins.intercept import dns

        try:
            dns.install({"a.com": "1.1.1.1"})
            dns.install({"b.com": "2.2.2.2"})

            # Only the second mapping should be active
            # (install clears overrides before adding new ones)
            assert dns._overrides == {"b.com": "2.2.2.2"}
        finally:
            dns.uninstall()


# ===================================================================
# trust.py tests — Node.js CA trust setup
# ===================================================================


class TestTrust:
    """Tests for making Node.js trust the mkcert CA."""

    def test_ensure_shell_profile_adds_line(self, tmp_path: Path) -> None:
        from screamingface.plugins.intercept.trust import MARKER, _ensure_shell_profile

        profile = tmp_path / ".zshrc"
        profile.write_text("# existing content\n")

        with patch("screamingface.plugins.intercept.trust._shell_profile", return_value=profile):
            result = _ensure_shell_profile(Path("/fake/rootCA.pem"))

        assert result is True
        content = profile.read_text()
        assert "NODE_EXTRA_CA_CERTS" in content
        assert "/fake/rootCA.pem" in content
        assert MARKER in content
        assert "# existing content" in content

    def test_ensure_shell_profile_idempotent(self, tmp_path: Path) -> None:
        from screamingface.plugins.intercept.trust import MARKER, _ensure_shell_profile

        profile = tmp_path / ".zshrc"
        profile.write_text(f'export NODE_EXTRA_CA_CERTS="/fake/rootCA.pem"  {MARKER}\n')

        with patch("screamingface.plugins.intercept.trust._shell_profile", return_value=profile):
            result = _ensure_shell_profile(Path("/fake/rootCA.pem"))

        assert result is True
        # Should not duplicate the line
        content = profile.read_text()
        assert content.count(MARKER) == 1

    def test_ensure_shell_profile_creates_if_missing(self, tmp_path: Path) -> None:
        from screamingface.plugins.intercept.trust import _ensure_shell_profile

        profile = tmp_path / ".zshrc"
        assert not profile.exists()

        with patch("screamingface.plugins.intercept.trust._shell_profile", return_value=profile):
            result = _ensure_shell_profile(Path("/fake/rootCA.pem"))

        assert result is True
        assert profile.exists()
        assert "NODE_EXTRA_CA_CERTS" in profile.read_text()

    def test_mkcert_ca_root_returns_path(self) -> None:
        from screamingface.plugins.intercept.trust import mkcert_ca_root

        with (
            patch("subprocess.run") as mock_run,
            patch("pathlib.Path.exists", return_value=True),
        ):
            mock_run.return_value = MagicMock(stdout="/fake/caroot\n")
            result = mkcert_ca_root()

        assert result is not None
        assert str(result).endswith("rootCA.pem")

    def test_mkcert_ca_root_returns_none_on_error(self) -> None:
        from screamingface.plugins.intercept.trust import mkcert_ca_root

        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = mkcert_ca_root()

        assert result is None

    def test_ensure_launchctl_calls_setenv(self) -> None:
        from screamingface.plugins.intercept.trust import _ensure_launchctl

        with patch("subprocess.run") as mock_run:
            _ensure_launchctl(Path("/fake/rootCA.pem"))

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "launchctl"
        assert cmd[1] == "setenv"
        assert "NODE_EXTRA_CA_CERTS" in cmd


# ===================================================================
# CLI tests
# ===================================================================


class TestInterceptCLI:
    """Tests for sf intercept status/off CLI commands."""

    def test_status_inactive(self) -> None:
        from typer.testing import CliRunner

        from screamingface.plugins.intercept.cli import intercept_app

        runner = CliRunner()
        with (
            patch("screamingface.plugins.intercept.cli.load_state", return_value=None),
            patch("screamingface.plugins.intercept.cli.has_entries", return_value=False),
        ):
            result = runner.invoke(intercept_app, ["status"])

        assert result.exit_code == 0
        assert "INACTIVE" in result.output

    def test_status_active(self) -> None:
        from typer.testing import CliRunner

        from screamingface.plugins.intercept.cli import intercept_app
        from screamingface.plugins.intercept.state import InterceptState

        runner = CliRunner()
        state = InterceptState(
            active=True,
            activated_at="2026-01-01T00:00:00+00:00",
            domains=["api.anthropic.com"],
            original_hosts_hash="abc",
            pid=os.getpid(),
        )
        with (
            patch("screamingface.plugins.intercept.cli.load_state", return_value=state),
            patch("screamingface.plugins.intercept.cli.has_entries", return_value=True),
            patch("screamingface.plugins.intercept.cli.is_stale", return_value=False),
        ):
            result = runner.invoke(intercept_app, ["status"])

        assert result.exit_code == 0
        assert "ACTIVE" in result.output
        assert "api.anthropic.com" in result.output

    def test_status_stale(self) -> None:
        from typer.testing import CliRunner

        from screamingface.plugins.intercept.cli import intercept_app
        from screamingface.plugins.intercept.state import InterceptState

        runner = CliRunner()
        state = InterceptState(
            active=True,
            activated_at="2026-01-01T00:00:00+00:00",
            domains=["api.anthropic.com"],
            original_hosts_hash="abc",
            pid=999999999,
        )
        with (
            patch("screamingface.plugins.intercept.cli.load_state", return_value=state),
            patch("screamingface.plugins.intercept.cli.has_entries", return_value=True),
            patch("screamingface.plugins.intercept.cli.is_stale", return_value=True),
        ):
            result = runner.invoke(intercept_app, ["status"])

        assert result.exit_code == 0
        assert "STALE" in result.output

    def test_status_inactive_with_leftover_hosts(self) -> None:
        from typer.testing import CliRunner

        from screamingface.plugins.intercept.cli import intercept_app

        runner = CliRunner()
        with (
            patch("screamingface.plugins.intercept.cli.load_state", return_value=None),
            patch("screamingface.plugins.intercept.cli.has_entries", return_value=True),
        ):
            result = runner.invoke(intercept_app, ["status"])

        assert result.exit_code == 0
        assert "INACTIVE" in result.output
        assert "WARNING" in result.output

    def test_off_cleans_up(self) -> None:
        from typer.testing import CliRunner

        from screamingface.plugins.intercept.cli import intercept_app

        runner = CliRunner()
        with (
            patch("screamingface.plugins.intercept.cli.remove_entries") as mock_remove,
            patch("screamingface.plugins.intercept.cli.flush_dns") as mock_flush,
            patch("screamingface.plugins.intercept.cli.clear_state") as mock_clear,
            patch(
                "screamingface.plugins.intercept.cli.InterceptPlugin._teardown_port_forward",
            ) as mock_pfctl,
        ):
            result = runner.invoke(intercept_app, ["off"])

        assert result.exit_code == 0
        assert "Done" in result.output
        mock_remove.assert_called_once()
        mock_flush.assert_called_once()
        mock_pfctl.assert_called_once()
        mock_clear.assert_called_once()


# ===================================================================
# register_cli hook tests
# ===================================================================


class TestRegisterCLI:
    """Test that the register_cli hook mechanism works."""

    def test_intercept_plugin_registers_cli(self) -> None:
        import typer

        from screamingface.plugins.intercept.plugin import InterceptPlugin

        app = typer.Typer()
        InterceptPlugin.register_cli(app)

        # Verify a sub-typer was added (registered_groups is typer's internal)
        group_names = [
            g.typer_instance.info.name  # type: ignore[union-attr]
            for g in app.registered_groups
        ]
        assert "intercept" in group_names

    def test_base_plugin_register_cli_is_noop(self) -> None:
        import typer

        from screamingface.plugin import Plugin

        app = typer.Typer()
        Plugin.register_cli(app)
        # No groups added
        assert len(app.registered_groups) == 0
