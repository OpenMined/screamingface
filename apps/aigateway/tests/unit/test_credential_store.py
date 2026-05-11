from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from aigateway.core import credential_store as module
from aigateway.core.credential_store import (
    JsonFileCredentialStore,
    LinuxLibsecretStore,
    MacOSKeychainStore,
    WindowsCredentialManagerStore,
)


def _completed(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_json_file_credential_store_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "creds.json"
    store = JsonFileCredentialStore(path)
    assert store.read("service", "account") is None
    store.write("service", "account", "secret")
    assert JsonFileCredentialStore(path).read("service", "account") == "secret"
    store.delete("service", "account")
    assert store.read("service", "account") is None


def test_json_file_credential_store_ignores_bad_json(tmp_path: Path) -> None:
    path = tmp_path / "creds.json"
    path.write_text("not-json")
    assert JsonFileCredentialStore(path).read("service", "account") is None


def test_macos_keychain_read_write_delete(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[1] == "find-generic-password":
            return _completed(stdout="secret\n")
        return _completed()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    store = MacOSKeychainStore()
    assert store.read("service", "account") == "secret"
    store.write("service", "account", "secret")
    store.delete("service", "account")
    assert [call[1] for call in calls] == [
        "find-generic-password",
        "add-generic-password",
        "delete-generic-password",
    ]


def test_macos_keychain_missing_and_errors(monkeypatch) -> None:
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: _completed(returncode=44))
    assert MacOSKeychainStore().read("service", "account") is None
    MacOSKeychainStore().delete("service", "account")

    monkeypatch.setattr(
        module.subprocess, "run", lambda *a, **k: _completed(returncode=1, stderr="nope")
    )
    with pytest.raises(RuntimeError, match="security.*failed"):
        MacOSKeychainStore().read("service", "account")


def test_linux_libsecret_read_write_delete(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/secret-tool")

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[1] == "lookup":
            return _completed(stdout="secret\n")
        return _completed()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    store = LinuxLibsecretStore()
    assert store.read("service", "account") == "secret"
    store.write("service", "account", "secret")
    store.delete("service", "account")
    assert [call[1] for call in calls] == ["lookup", "store", "clear"]


def test_linux_libsecret_missing_tool_and_values(monkeypatch) -> None:
    monkeypatch.setattr(module.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="secret-tool"):
        LinuxLibsecretStore().read("service", "account")

    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/secret-tool")
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k: _completed(returncode=1))
    assert LinuxLibsecretStore().read("service", "account") is None

    monkeypatch.setattr(
        module.subprocess, "run", lambda *a, **k: _completed(returncode=1, stderr="nope")
    )
    with pytest.raises(RuntimeError, match="secret-tool store"):
        LinuxLibsecretStore().write("service", "account", "secret")


def test_windows_credential_manager(monkeypatch) -> None:
    class FakeKeyring:
        value: str | None = None

        def get_password(self, service: str, account: str) -> str | None:
            return self.value

        def set_password(self, service: str, account: str, value: str) -> None:
            self.value = value

        def delete_password(self, service: str, account: str) -> None:
            self.value = None

    keyring = FakeKeyring()
    monkeypatch.setattr(module, "_try_import_keyring", lambda: keyring)
    store = WindowsCredentialManagerStore()
    assert store.read("service", "account") is None
    store.write("service", "account", "secret")
    assert store.read("service", "account") == "secret"
    store.delete("service", "account")
    assert store.read("service", "account") is None


def test_windows_credential_manager_without_keyring(monkeypatch) -> None:
    monkeypatch.setattr(module, "_try_import_keyring", lambda: None)
    with pytest.raises(RuntimeError, match="python-keyring"):
        WindowsCredentialManagerStore().read("service", "account")
    with pytest.raises(RuntimeError, match="python-keyring"):
        WindowsCredentialManagerStore().write("service", "account", "secret")
    with pytest.raises(RuntimeError, match="python-keyring"):
        WindowsCredentialManagerStore().delete("service", "account")


def test_get_credential_store_platforms(monkeypatch) -> None:
    monkeypatch.setattr(module.sys, "platform", "darwin")
    assert isinstance(module.get_credential_store(), MacOSKeychainStore)
    monkeypatch.setattr(module.sys, "platform", "linux")
    assert isinstance(module.get_credential_store(), LinuxLibsecretStore)
    monkeypatch.setattr(module.sys, "platform", "win32")
    assert isinstance(module.get_credential_store(), WindowsCredentialManagerStore)
    monkeypatch.setattr(module.sys, "platform", "plan9")
    with pytest.raises(RuntimeError, match="No credential store"):
        module.get_credential_store()
