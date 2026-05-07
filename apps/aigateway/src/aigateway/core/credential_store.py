"""Cross-platform credential store — wraps the OS-level secret manager.

- macOS: shells out to ``security``.
- Linux: shells out to ``secret-tool`` (libsecret-tools).
- Windows: delegates to ``python-keyring`` if installed.

Read returns ``None`` for "not found"; ``RuntimeError`` for genuinely
exceptional conditions (command missing, store locked, subprocess crash).
Synchronous — callers wrap in ``asyncio.to_thread`` if needed.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


def _try_import_keyring():
    try:
        import keyring  # type: ignore[import-not-found]

        return keyring
    except ImportError:
        return None


class CredentialStore(ABC):
    @abstractmethod
    def read(self, service: str, account: str) -> str | None: ...

    @abstractmethod
    def write(self, service: str, account: str, value: str) -> None: ...

    @abstractmethod
    def delete(self, service: str, account: str) -> None: ...


class MacOSKeychainStore(CredentialStore):
    def read(self, service: str, account: str) -> str | None:
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("`security` command not found — not a macOS system?") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"`security` timed out for service={service!r}; keychain may be locked"
            ) from exc

        if result.returncode == 44:
            return None
        if result.returncode != 0:
            raise RuntimeError(
                f"`security` failed with exit {result.returncode}: "
                f"{result.stderr.strip() or '<no stderr>'}"
            )
        return result.stdout.strip() or None

    def write(self, service: str, account: str, value: str) -> None:
        try:
            result = subprocess.run(
                [
                    "security",
                    "add-generic-password",
                    "-U",
                    "-s",
                    service,
                    "-a",
                    account,
                    "-w",
                    value,
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("`security` command not found — not a macOS system?") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"`security` write timed out for service={service!r}") from exc

        if result.returncode != 0:
            raise RuntimeError(
                f"`security add-generic-password` failed with exit {result.returncode}: "
                f"{result.stderr.strip() or '<no stderr>'}"
            )

    def delete(self, service: str, account: str) -> None:
        try:
            result = subprocess.run(
                ["security", "delete-generic-password", "-s", service, "-a", account],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("`security` command not found") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"`security delete` timed out for service={service!r}") from exc
        if result.returncode == 44:
            return  # already absent — idempotent
        if result.returncode != 0:
            raise RuntimeError(
                f"`security delete-generic-password` failed exit {result.returncode}: "
                f"{result.stderr.strip() or '<no stderr>'}"
            )


class LinuxLibsecretStore(CredentialStore):
    def read(self, service: str, account: str) -> str | None:
        if shutil.which("secret-tool") is None:
            raise RuntimeError(
                "`secret-tool` not found. Install with `apt install libsecret-tools`."
            )
        try:
            result = subprocess.run(
                ["secret-tool", "lookup", "service", service, "account", account],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"`secret-tool lookup` timed out for service={service!r}") from exc
        if result.returncode != 0 or not result.stdout:
            return None
        return result.stdout.strip() or None

    def write(self, service: str, account: str, value: str) -> None:
        if shutil.which("secret-tool") is None:
            raise RuntimeError(
                "`secret-tool` not found. Install with `apt install libsecret-tools`."
            )
        label = f"{service} ({account})"
        try:
            result = subprocess.run(
                [
                    "secret-tool",
                    "store",
                    "--label",
                    label,
                    "service",
                    service,
                    "account",
                    account,
                ],
                input=value,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"`secret-tool store` timed out for service={service!r}") from exc
        if result.returncode != 0:
            raise RuntimeError(
                f"`secret-tool store` failed with exit {result.returncode}: "
                f"{result.stderr.strip() or '<no stderr>'}"
            )

    def delete(self, service: str, account: str) -> None:
        if shutil.which("secret-tool") is None:
            raise RuntimeError("`secret-tool` not found")
        try:
            subprocess.run(
                ["secret-tool", "clear", "service", service, "account", account],
                check=True,
                timeout=5,
                capture_output=True,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("`secret-tool clear` timed out") from exc
        except subprocess.CalledProcessError:
            return  # idempotent


class WindowsCredentialManagerStore(CredentialStore):
    def read(self, service: str, account: str) -> str | None:
        keyring = _try_import_keyring()
        if keyring is None:
            raise RuntimeError(
                "Windows credential read requires `python-keyring`. pip install keyring"
            )
        try:
            return keyring.get_password(service, account)
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                f"keyring.get_password failed for service={service!r}: {exc}"
            ) from exc

    def write(self, service: str, account: str, value: str) -> None:
        keyring = _try_import_keyring()
        if keyring is None:
            raise RuntimeError(
                "Windows credential write requires `python-keyring`. pip install keyring"
            )
        try:
            keyring.set_password(service, account, value)
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                f"keyring.set_password failed for service={service!r}: {exc}"
            ) from exc

    def delete(self, service: str, account: str) -> None:
        keyring = _try_import_keyring()
        if keyring is None:
            raise RuntimeError("Windows credential delete requires `python-keyring`.")
        try:
            keyring.delete_password(service, account)
        except Exception:  # pragma: no cover
            pass  # idempotent — many backends raise on missing entry


def get_credential_store() -> CredentialStore:
    if sys.platform == "darwin":
        return MacOSKeychainStore()
    if sys.platform.startswith("linux"):
        return LinuxLibsecretStore()
    if sys.platform == "win32":
        return WindowsCredentialManagerStore()
    raise RuntimeError(f"No credential store implementation for platform {sys.platform!r}")
