"""Sudo subprocess helpers — works around macOS's GUI password dialog.

mitmproxy's ``--mode local`` requires root because it opens raw network
sockets via the macOS Network Extension framework. We need a way to
prompt for the admin password (macOS) or fall back to plain sudo
(Linux), and to keep the resulting process running long-term.

Pulled out of ``plugin.py`` during SF-134 so the orchestration class
isn't cluttered with platform-specific subprocess plumbing.
"""

from __future__ import annotations

import platform
import shlex
import subprocess


def sudo_run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a command with elevated privileges.

    On macOS, prompts via the system password dialog (osascript ``do
    shell script ... with administrator privileges``). On Linux, defers
    to plain ``sudo`` and assumes credentials are already cached.
    """
    if platform.system() == "Darwin":
        escaped = " ".join(shlex.quote(c) for c in cmd)
        result = subprocess.run(
            [
                "osascript",
                "-e",
                f'do shell script "{escaped}" with administrator privileges',
            ],
            capture_output=True,
            text=True,
        )
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, cmd, result.stdout, result.stderr
            )
        return result
    return subprocess.run(["sudo", *cmd], capture_output=True, text=True, check=check)


def sudo_popen(cmd: list[str], **kwargs: object) -> subprocess.Popen:
    """Start a long-running process with elevated privileges.

    On macOS, first obtains sudo credentials via the system password
    dialog using a harmless command, then launches the actual process
    with cached sudo credentials.
    """
    if platform.system() == "Darwin":
        # Prompt for credentials via the GUI dialog using a harmless command
        sudo_run(["/usr/bin/true"])
        # Now sudo has cached credentials; launch the actual process with sudo
        return subprocess.Popen(["sudo", *cmd], **kwargs)  # type: ignore[arg-type]
    return subprocess.Popen(["sudo", *cmd], **kwargs)  # type: ignore[arg-type]
