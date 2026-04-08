"""Unit tests for the cross-platform credential store.

All platform branches are tested with mocked subprocess calls so every
test runs on any host regardless of which OS you're running on.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from screamingface.plugins.llm_base.credential_store import (
    LinuxLibsecretStore,
    MacOSKeychainStore,
    WindowsCredentialManagerStore,
    get_credential_store,
)


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> MagicMock:
    """Build a fake subprocess.CompletedProcess result."""
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


# ----------------------------------------------------------------------------
# Factory
# ----------------------------------------------------------------------------


class TestGetCredentialStoreFactory:
    def test_returns_macos_on_darwin(self):
        with patch("sys.platform", "darwin"):
            store = get_credential_store()
            assert isinstance(store, MacOSKeychainStore)

    def test_returns_linux_on_linux(self):
        with patch("sys.platform", "linux"):
            store = get_credential_store()
            assert isinstance(store, LinuxLibsecretStore)

    def test_returns_windows_on_win32(self):
        with patch("sys.platform", "win32"):
            store = get_credential_store()
            assert isinstance(store, WindowsCredentialManagerStore)

    def test_raises_on_unknown_platform(self):
        with patch("sys.platform", "plan9"):
            with pytest.raises(RuntimeError, match="plan9"):
                get_credential_store()


# ----------------------------------------------------------------------------
# macOS Keychain
# ----------------------------------------------------------------------------


class TestMacOSKeychainStore:
    def test_read_success(self):
        store = MacOSKeychainStore()
        with patch(
            "subprocess.run",
            return_value=_completed(0, stdout='{"claudeAiOauth":{"accessToken":"sk-ant-X"}}\n'),
        ) as run:
            value = store.read("Claude Code-credentials", "sergey")
        assert value == '{"claudeAiOauth":{"accessToken":"sk-ant-X"}}'
        # Verify the right subprocess args went in
        args = run.call_args.args[0]
        assert args[0] == "security"
        assert args[1] == "find-generic-password"
        assert "-s" in args
        assert "Claude Code-credentials" in args
        assert "-a" in args
        assert "sergey" in args
        assert "-w" in args

    def test_read_not_found_returns_none(self):
        """Exit code 44 is macOS Keychain's 'item not found' signal."""
        store = MacOSKeychainStore()
        with patch("subprocess.run", return_value=_completed(44, stderr="item not found")):
            value = store.read("Claude Code-credentials", "sergey")
        assert value is None

    def test_read_other_error_raises(self):
        store = MacOSKeychainStore()
        with patch("subprocess.run", return_value=_completed(1, stderr="generic failure")):
            with pytest.raises(RuntimeError, match="exit 1"):
                store.read("Claude Code-credentials", "sergey")

    def test_read_empty_stdout_returns_none(self):
        """Edge case: exit 0 but no password value."""
        store = MacOSKeychainStore()
        with patch("subprocess.run", return_value=_completed(0, stdout="\n")):
            value = store.read("Claude Code-credentials", "sergey")
        assert value is None

    def test_read_command_missing(self):
        store = MacOSKeychainStore()
        with patch("subprocess.run", side_effect=FileNotFoundError("security")):
            with pytest.raises(RuntimeError, match="not a macOS system"):
                store.read("Claude Code-credentials", "sergey")

    def test_read_timeout(self):
        store = MacOSKeychainStore()
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired("security", 5),
        ):
            with pytest.raises(RuntimeError, match="timed out"):
                store.read("Claude Code-credentials", "sergey")

    def test_write_success(self):
        store = MacOSKeychainStore()
        with patch("subprocess.run", return_value=_completed(0)) as run:
            store.write("Claude Code-credentials", "sergey", '{"accessToken":"new"}')
        args = run.call_args.args[0]
        assert args[0] == "security"
        assert args[1] == "add-generic-password"
        assert "-U" in args  # update flag is critical
        assert '{"accessToken":"new"}' in args

    def test_write_failure_raises(self):
        store = MacOSKeychainStore()
        with patch("subprocess.run", return_value=_completed(1, stderr="permission denied")):
            with pytest.raises(RuntimeError, match="permission denied"):
                store.write("Claude Code-credentials", "sergey", '{"x":1}')


# ----------------------------------------------------------------------------
# Linux libsecret
# ----------------------------------------------------------------------------


class TestLinuxLibsecretStore:
    def test_read_success(self):
        store = LinuxLibsecretStore()
        with (
            patch("shutil.which", return_value="/usr/bin/secret-tool"),
            patch(
                "subprocess.run",
                return_value=_completed(0, stdout='{"claudeAiOauth":{"accessToken":"sk-ant-X"}}\n'),
            ) as run,
        ):
            value = store.read("Claude Code-credentials", "sergey")
        assert value == '{"claudeAiOauth":{"accessToken":"sk-ant-X"}}'
        args = run.call_args.args[0]
        assert args[0] == "secret-tool"
        assert args[1] == "lookup"
        assert "service" in args
        assert "Claude Code-credentials" in args
        assert "account" in args
        assert "sergey" in args

    def test_read_not_found_returns_none(self):
        """secret-tool exits 1 with empty stdout when the item isn't there."""
        store = LinuxLibsecretStore()
        with (
            patch("shutil.which", return_value="/usr/bin/secret-tool"),
            patch("subprocess.run", return_value=_completed(1, stdout="")),
        ):
            value = store.read("Claude Code-credentials", "sergey")
        assert value is None

    def test_read_command_missing(self):
        store = LinuxLibsecretStore()
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="secret-tool.*not found"):
                store.read("Claude Code-credentials", "sergey")

    def test_write_success(self):
        store = LinuxLibsecretStore()
        with (
            patch("shutil.which", return_value="/usr/bin/secret-tool"),
            patch("subprocess.run", return_value=_completed(0)) as run,
        ):
            store.write("Claude Code-credentials", "sergey", '{"accessToken":"new"}')
        args = run.call_args.args[0]
        assert args[0] == "secret-tool"
        assert args[1] == "store"
        assert "--label" in args
        assert "service" in args
        assert "account" in args
        # The value goes via stdin, not args
        assert run.call_args.kwargs.get("input") == '{"accessToken":"new"}'

    def test_write_failure_raises(self):
        store = LinuxLibsecretStore()
        with (
            patch("shutil.which", return_value="/usr/bin/secret-tool"),
            patch(
                "subprocess.run",
                return_value=_completed(1, stderr="dbus error"),
            ),
        ):
            with pytest.raises(RuntimeError, match="dbus error"):
                store.write("Claude Code-credentials", "sergey", '{"x":1}')


# ----------------------------------------------------------------------------
# Windows Credential Manager
# ----------------------------------------------------------------------------


class TestWindowsCredentialManagerStore:
    def test_read_with_keyring_installed(self):
        store = WindowsCredentialManagerStore()
        fake_keyring = MagicMock()
        fake_keyring.get_password.return_value = '{"accessToken":"X"}'
        with patch(
            "screamingface.plugins.llm_base.credential_store._try_import_keyring",
            return_value=fake_keyring,
        ):
            value = store.read("Claude Code-credentials", "sergey")
        assert value == '{"accessToken":"X"}'
        fake_keyring.get_password.assert_called_once_with("Claude Code-credentials", "sergey")

    def test_read_without_keyring_raises(self):
        store = WindowsCredentialManagerStore()
        with patch(
            "screamingface.plugins.llm_base.credential_store._try_import_keyring",
            return_value=None,
        ):
            with pytest.raises(RuntimeError, match="python-keyring"):
                store.read("Claude Code-credentials", "sergey")

    def test_write_with_keyring_installed(self):
        store = WindowsCredentialManagerStore()
        fake_keyring = MagicMock()
        with patch(
            "screamingface.plugins.llm_base.credential_store._try_import_keyring",
            return_value=fake_keyring,
        ):
            store.write("Claude Code-credentials", "sergey", '{"new":"val"}')
        fake_keyring.set_password.assert_called_once_with(
            "Claude Code-credentials", "sergey", '{"new":"val"}'
        )

    def test_write_without_keyring_raises(self):
        store = WindowsCredentialManagerStore()
        with patch(
            "screamingface.plugins.llm_base.credential_store._try_import_keyring",
            return_value=None,
        ):
            with pytest.raises(RuntimeError, match="python-keyring"):
                store.write("Claude Code-credentials", "sergey", "x")

    def test_read_keyring_raises_wrapped(self):
        store = WindowsCredentialManagerStore()
        fake_keyring = MagicMock()
        fake_keyring.get_password.side_effect = RuntimeError("win32 broken")
        with patch(
            "screamingface.plugins.llm_base.credential_store._try_import_keyring",
            return_value=fake_keyring,
        ):
            with pytest.raises(RuntimeError, match="win32 broken"):
                store.read("Claude Code-credentials", "sergey")
