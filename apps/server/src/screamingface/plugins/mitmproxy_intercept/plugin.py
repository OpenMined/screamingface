"""Mitmproxy Intercept plugin — transparent traffic interception via mitmproxy --mode local."""

from __future__ import annotations

import logging
import os
import re
import shlex
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic_settings import SettingsConfigDict

from screamingface.plugin import Plugin, PluginSettings
from screamingface.plugins.mitmproxy_intercept.state import (
    MitmproxyState,
    clear_state,
    is_stale,
    load_state,
    now_iso,
    save_state,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry

logger = logging.getLogger(__name__)

ADDON_PATH = Path(__file__).parent / "addon.py"


class MitmproxyInterceptSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_MITMPROXY__",
        env_nested_delimiter="__",
    )
    domains: list[str] = ["api.anthropic.com"]
    proxy_port: int = 8888
    mitmdump_path: str = "mitmdump"
    process_filter: str = ""  # e.g. "node" to only capture node processes
    mitmproxy_ca_cert: str = "~/.mitmproxy/mitmproxy-ca-cert.pem"
    auto_cleanup: bool = True  # clean stale state on startup
    trust_ca: bool = True  # auto-trust mitmproxy CA in system keychain


class MitmproxyInterceptPlugin(Plugin):
    name = "mitmproxy-intercept"
    description = "Transparent traffic interception via mitmproxy --mode local (requires sudo)"
    settings_class = MitmproxyInterceptSettings
    system_deps: list[str] = []
    conflicts = ["claude-intercept"]

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._mitmdump: str = ""  # resolved full path to mitmdump

    def preflight(self) -> tuple[bool, str]:
        ok, reason = super().preflight()
        if not ok:
            return ok, reason

        settings: MitmproxyInterceptSettings = self.settings  # type: ignore[assignment]

        # Resolve mitmdump full path — check PATH first, then fall back to
        # the same directory as sys.executable (venv bin/).
        resolved = shutil.which(settings.mitmdump_path)
        if not resolved:
            import sys

            venv_bin = Path(sys.executable).parent / "mitmdump"
            if venv_bin.exists():
                resolved = str(venv_bin)
        if not resolved:
            return False, "mitmdump not found in PATH or venv"
        self._mitmdump = resolved

        # Ensure mitmproxy CA cert exists — generate via CertStore API if missing
        ca_cert = Path(settings.mitmproxy_ca_cert).expanduser()
        if not ca_cert.exists():
            logger.info("Mitmproxy CA cert not found — generating...")
            from mitmproxy.certs import CertStore

            confdir = ca_cert.parent
            confdir.mkdir(parents=True, exist_ok=True)
            # basename "mitmproxy" produces "mitmproxy-ca-cert.pem" etc.
            CertStore.create_store(confdir, "mitmproxy", key_size=2048)
            if not ca_cert.exists():
                return False, f"Failed to generate mitmproxy CA cert at {ca_cert}"
            logger.info("Mitmproxy CA cert generated at %s", ca_cert)

        # Check for stale state from a previous crash
        if is_stale():
            if settings.auto_cleanup:
                logger.warning("Stale mitmproxy intercept state detected — auto-cleaning...")
                _cleanup_stale()
            else:
                return False, (
                    "Stale mitmproxy intercept state detected "
                    "(previous mitmproxy process crashed). "
                    "Set SF_MITMPROXY__AUTO_CLEANUP=true to auto-clean."
                )

        return True, ""

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        settings: MitmproxyInterceptSettings = self.settings  # type: ignore[assignment]

        # 1. Trust mitmproxy CA in system keychain (macOS, one-time)
        if settings.trust_ca:
            _ensure_ca_trusted(settings.mitmproxy_ca_cert)

        # 2. Build mitmproxy command
        mode = f"local:{settings.process_filter}" if settings.process_filter else "local"
        allow_hosts = "|".join(re.escape(d) for d in settings.domains)

        cmd = [
            self._mitmdump,
            "--mode",
            mode,
            "--listen-port",
            str(settings.proxy_port),
            "--allow-hosts",
            allow_hosts,
            "-s",
            str(ADDON_PATH),
        ]

        # 3. Pass screamingface connection info to addon via env
        sf_scheme = "https" if app.state.config.server.ssl else "http"
        env = {
            **os.environ,
            "SF_HOST": "127.0.0.1",
            "SF_PORT": str(app.state.config.server.port),
            "SF_SCHEME": sf_scheme,
        }

        # 4. Start mitmproxy subprocess (requires root for --mode local)
        logger.info("Starting mitmproxy: %s", " ".join(cmd))
        self._process = _sudo_popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # 5. Wait briefly and check if process started OK
        time.sleep(1)
        retcode = self._process.poll()
        if retcode is not None:
            output = self._process.stdout.read() if self._process.stdout else ""
            self._process = None
            raise RuntimeError(f"mitmproxy exited immediately (code {retcode}):\n{output}")

        # Stream mitmdump output to logger in a background thread
        def _log_output(proc: subprocess.Popen) -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    logger.info("[mitmdump] %s", line)

        threading.Thread(target=_log_output, args=(self._process,), daemon=True).start()
        logger.info("Mitmproxy started (PID %d)", self._process.pid)

        # 6. Save state for crash recovery
        save_state(
            MitmproxyState(
                active=True,
                activated_at=now_iso(),
                pid=self._process.pid,
                proxy_port=settings.proxy_port,
                domains=settings.domains,
            )
        )

        # 7. Register shutdown hook
        hooks.register("app.shutdown", self._on_shutdown, plugin_name=self.name)

    async def _on_shutdown(self) -> None:
        self._stop_mitmproxy()

    def teardown(self) -> None:
        self._stop_mitmproxy()

    def _stop_mitmproxy(self) -> None:
        """Terminate the mitmproxy subprocess gracefully."""
        if self._process is None:
            clear_state()
            return

        logger.info("Stopping mitmproxy (PID %d)...", self._process.pid)
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("Mitmproxy did not terminate in time — killing")
            self._process.kill()
            self._process.wait(timeout=3)

        self._process = None
        clear_state()
        logger.info("Mitmproxy stopped")


def _sudo_run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a command with elevated privileges via macOS system password dialog."""
    import platform

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
    else:
        return subprocess.run(["sudo", *cmd], capture_output=True, text=True, check=check)


def _sudo_popen(cmd: list[str], **kwargs: object) -> subprocess.Popen:
    """Start a long-running process with elevated privileges.

    On macOS, first obtains sudo credentials via the system password dialog,
    then uses sudo to launch the process.
    """
    import platform

    if platform.system() == "Darwin":
        # Prompt for credentials via the GUI dialog using a harmless command
        _sudo_run(["/usr/bin/true"])
        # Now sudo has cached credentials; launch the actual process with sudo
        return subprocess.Popen(["sudo", *cmd], **kwargs)  # type: ignore[arg-type]
    else:
        return subprocess.Popen(["sudo", *cmd], **kwargs)  # type: ignore[arg-type]


def _ensure_ca_trusted(ca_cert_path: str) -> None:
    """Trust mitmproxy CA in macOS system keychain (idempotent)."""
    import platform

    if platform.system() != "Darwin":
        return

    ca_cert = Path(ca_cert_path).expanduser()
    if not ca_cert.exists():
        return

    # Check if already trusted by looking for the cert in the system keychain
    result = subprocess.run(
        ["security", "find-certificate", "-c", "mitmproxy", "/Library/Keychains/System.keychain"],
        capture_output=True,
    )
    if result.returncode == 0:
        logger.debug("Mitmproxy CA already trusted in system keychain")
        return

    logger.info("Trusting mitmproxy CA in system keychain...")
    _sudo_run(
        [
            "security",
            "add-trusted-cert",
            "-d",
            "-p",
            "ssl",
            "-p",
            "basic",
            "-k",
            "/Library/Keychains/System.keychain",
            str(ca_cert),
        ]
    )
    logger.info("Mitmproxy CA trusted")


def _cleanup_stale() -> None:
    """Clean up leftover state from a crashed mitmproxy process."""
    state = load_state()
    if state is None:
        return
    logger.info("Cleaning up stale mitmproxy process (PID %d)", state.pid)
    try:
        os.kill(state.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass  # already dead or not ours
    clear_state()
