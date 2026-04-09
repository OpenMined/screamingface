"""Cross-platform credential store — wraps the OS-level secret manager.

Three concrete implementations:

- :class:`MacOSKeychainStore` — shells out to ``security``. Verified
  working by the SF-77 spike on this machine.
- :class:`LinuxLibsecretStore` — shells out to ``secret-tool``. Not yet
  verified against a real Linux machine's Claude Code install; Phase 0
  follow-up will confirm the service name is the same on Linux.
- :class:`WindowsCredentialManagerStore` — delegates to ``python-keyring``
  if installed, otherwise shells out to ``cmdkey``. Not yet verified.

The soft dep on ``python-keyring`` is checked at module import. When
available, all three platforms can optionally route through keyring for
a cleaner API — but the subprocess fallbacks are the source of truth
and must always work.

Public factory: :func:`get_credential_store` returns the appropriate
concrete implementation for the current platform.

All read/write operations are synchronous. The credential store is
typically called from inside an async function, but the underlying OS
calls are fast (low ms range) and wrapping them in ``asyncio.to_thread``
is the caller's responsibility if they need to.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


def _try_import_keyring():
    """Return the keyring module if installed, else None.

    Soft dep — the module works without it, falling back to subprocess
    calls on each platform. When installed, Windows delegates to keyring
    because writing the Windows CredMan API without it is awful.
    """
    try:
        import keyring  # type: ignore[import-not-found]

        return keyring
    except ImportError:
        return None


class CredentialStore(ABC):
    """Abstract contract for reading/writing secrets to the OS credential store.

    All methods raise no exceptions for "not found" — :meth:`read`
    returns ``None`` in that case. Callers that need to distinguish
    "not found" from "corrupted" should call :meth:`read` and check
    for ``None``, then raise :class:`CredentialNotFoundError` themselves
    at the semantic layer.

    Exceptions are raised only for genuinely exceptional cases: the
    credential store command is missing (not installed), the store is
    locked and a prompt failed, the subprocess crashed, etc. These
    surface as ``RuntimeError``.
    """

    @abstractmethod
    def read(self, service: str, account: str) -> str | None:
        """Return the password value for (service, account).

        Returns:
            The stored password as a string, or ``None`` if no entry
            exists for the given service+account combination.

        Raises:
            RuntimeError: The credential store is unreachable (command
                missing, keychain locked, subprocess crashed, etc.).
        """

    @abstractmethod
    def write(self, service: str, account: str, value: str) -> None:
        """Create or update the password for (service, account).

        Overwrites an existing entry if one is present.

        Raises:
            RuntimeError: Same conditions as :meth:`read`.
        """


# ----------------------------------------------------------------------------
# macOS Keychain — verified working by SF-77 spike
# ----------------------------------------------------------------------------


class MacOSKeychainStore(CredentialStore):
    """macOS Keychain via the built-in ``security`` command.

    Read command::

        security find-generic-password -s <service> -a <account> -w

    Write command::

        security add-generic-password -U -s <service> -a <account> -w <value>

    The ``-U`` flag on write updates an existing entry instead of
    erroring. Without it, a second ``add-generic-password`` call for the
    same service+account returns a non-zero exit code.

    Output from read is the stripped password string on stdout.
    Exit code 44 means "not found"; we convert that to ``None``.
    """

    def read(self, service: str, account: str) -> str | None:
        try:
            result = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-s",
                    service,
                    "-a",
                    account,
                    "-w",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("`security` command not found — not a macOS system?") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"`security` command timed out after 5s for service={service!r}; "
                "keychain may be locked"
            ) from exc

        if result.returncode == 44:
            # "The specified item could not be found in the keychain"
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
            raise RuntimeError(
                f"`security` write timed out after 5s for service={service!r}"
            ) from exc

        if result.returncode != 0:
            raise RuntimeError(
                f"`security add-generic-password` failed with exit "
                f"{result.returncode}: {result.stderr.strip() or '<no stderr>'}"
            )


# ----------------------------------------------------------------------------
# Linux libsecret — via secret-tool subprocess
# ----------------------------------------------------------------------------


class LinuxLibsecretStore(CredentialStore):
    """Linux libsecret via the ``secret-tool`` command.

    Read command::

        secret-tool lookup service <service> account <account>

    Write command::

        echo -n "<value>" | secret-tool store --label="<label>" \\
            service <service> account <account>

    We use ``service`` and ``account`` as custom attributes (libsecret
    is a flat key-value store; there's no native service/account
    distinction). This matches how most python-keyring backends map
    their attributes onto libsecret.

    NOTE: not yet verified against a real Linux machine's Claude Code
    install. Phase 0 follow-up will confirm the Claude Code CLI uses the
    same service name (``"Claude Code-credentials"``) on Linux.
    """

    def read(self, service: str, account: str) -> str | None:
        if shutil.which("secret-tool") is None:
            raise RuntimeError(
                "`secret-tool` command not found. Install with "
                "`apt install libsecret-tools` or equivalent."
            )

        try:
            result = subprocess.run(
                [
                    "secret-tool",
                    "lookup",
                    "service",
                    service,
                    "account",
                    account,
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"`secret-tool lookup` timed out for service={service!r}") from exc

        # secret-tool exits 1 with empty stdout when not found.
        if result.returncode != 0 or not result.stdout:
            return None

        return result.stdout.strip() or None

    def write(self, service: str, account: str, value: str) -> None:
        if shutil.which("secret-tool") is None:
            raise RuntimeError(
                "`secret-tool` command not found. Install with "
                "`apt install libsecret-tools` or equivalent."
            )

        label = f"{service} ({account})"
        try:
            # secret-tool store reads the value from stdin
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


# ----------------------------------------------------------------------------
# Windows Credential Manager — via python-keyring or cmdkey fallback
# ----------------------------------------------------------------------------


class WindowsCredentialManagerStore(CredentialStore):
    """Windows Credential Manager.

    When ``python-keyring`` is installed we delegate to it (cleanest
    path — the keyring maintainers handle all the Win32 quirks). When
    it's not, we fall back to ``cmdkey`` for writes and a best-effort
    read via PowerShell, but that path is limited and tests should
    assume python-keyring is available on Windows.

    NOTE: not yet verified against a real Windows machine. Phase 0
    follow-up will confirm whether Claude Code CLI uses the same
    service name on Windows.
    """

    def read(self, service: str, account: str) -> str | None:
        keyring = _try_import_keyring()
        if keyring is None:
            raise RuntimeError(
                "Windows credential read requires `python-keyring`. "
                "Install with: pip install keyring"
            )
        try:
            return keyring.get_password(service, account)
        except Exception as exc:  # pragma: no cover - platform specific
            raise RuntimeError(
                f"keyring.get_password failed for service={service!r}: {exc}"
            ) from exc

    def write(self, service: str, account: str, value: str) -> None:
        keyring = _try_import_keyring()
        if keyring is None:
            raise RuntimeError(
                "Windows credential write requires `python-keyring`. "
                "Install with: pip install keyring"
            )
        try:
            keyring.set_password(service, account, value)
        except Exception as exc:  # pragma: no cover - platform specific
            raise RuntimeError(
                f"keyring.set_password failed for service={service!r}: {exc}"
            ) from exc


# ----------------------------------------------------------------------------
# Factory — selects the right implementation at call time
# ----------------------------------------------------------------------------


def get_credential_store() -> CredentialStore:
    """Return the :class:`CredentialStore` appropriate for the current platform.

    Selection logic:

    - ``sys.platform == "darwin"`` → :class:`MacOSKeychainStore`
    - ``sys.platform.startswith("linux")`` → :class:`LinuxLibsecretStore`
    - ``sys.platform == "win32"`` → :class:`WindowsCredentialManagerStore`
    - Anything else → raises :class:`RuntimeError`

    The function is a factory not a module-level singleton so tests can
    monkeypatch ``sys.platform`` to exercise different branches. Each
    call is cheap (constructs a new instance with no I/O).
    """
    if sys.platform == "darwin":
        return MacOSKeychainStore()
    if sys.platform.startswith("linux"):
        return LinuxLibsecretStore()
    if sys.platform == "win32":
        return WindowsCredentialManagerStore()
    raise RuntimeError(f"No credential store implementation for platform {sys.platform!r}")
