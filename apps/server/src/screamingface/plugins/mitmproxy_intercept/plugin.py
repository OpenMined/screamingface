"""Mitmproxy Intercept plugin — transparent traffic interception via mitmproxy --mode local.

Auto-discovers which domains to intercept from the FrontendRegistry
(populated by frontend plugins like claude-frontend).

Explicit routing rules (``rules``) take priority over auto-discovery.
"""

from __future__ import annotations

import atexit
import json
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

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import SettingsConfigDict

from screamingface.core.frontend import FRONTENDS_FILE, FrontendRegistry
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


class RoutingRule(BaseModel):
    """Maps a domain to a frontend plugin by name."""

    domain: str = Field(min_length=1)
    frontend: str = Field(min_length=1)
    process_filter: str = ""  # e.g. "node" — only intercept traffic from this process


class MitmproxyInterceptSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_MITMPROXY__",
        env_nested_delimiter="__",
    )
    rules: list[RoutingRule] = []  # explicit domain→frontend routing rules
    proxy_port: int = 8888
    mitmdump_path: str = "mitmdump"
    mitmproxy_ca_cert: str = "~/.mitmproxy/mitmproxy-ca-cert.pem"
    auto_cleanup: bool = True  # clean stale state on startup
    trust_ca: bool = True  # auto-trust mitmproxy CA in system keychain

    @model_validator(mode="after")
    def _unique_domains(self) -> MitmproxyInterceptSettings:
        domains = [r.domain for r in self.rules if r.domain]
        dupes = [d for d in domains if domains.count(d) > 1]
        if dupes:
            raise ValueError(f"Duplicate domains: {', '.join(sorted(set(dupes)))}")
        return self


def _resolve_rules(
    rules: list[RoutingRule], registry: FrontendRegistry
) -> dict[str, dict[str, object]]:
    """Resolve explicit routing rules against the frontend registry.

    Returns ``{domain: {host, port, scheme}}`` for each rule whose frontend
    is registered.  Warns and skips rules referencing unknown frontends.
    """
    resolved: dict[str, dict[str, object]] = {}
    entries = registry.entries
    for rule in rules:
        if not rule.domain or not rule.frontend:
            continue  # skip incomplete rules (e.g. empty items from UI)
        entry = entries.get(rule.frontend)
        if entry is None:
            logger.warning(
                "Routing rule references unknown frontend %r — skipping domain %r",
                rule.frontend,
                rule.domain,
            )
            continue
        resolved[rule.domain] = {
            "host": entry.host,
            "port": entry.port,
            "scheme": entry.scheme,
        }
    return resolved


class MitmproxyInterceptPlugin(Plugin):
    name = "mitmproxy-intercept"
    description = "Transparent traffic interception via mitmproxy --mode local (requires sudo)"
    settings_class = MitmproxyInterceptSettings
    system_deps: list[str] = []
    conflicts = ["claude-intercept", "claude-env-intercept"]

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

        # 0. Clear any stale intercept from a previous unclean shutdown
        _clear_intercept()

        # 1. Trust mitmproxy CA in system keychain (macOS, one-time)
        if settings.trust_ca:
            _ensure_ca_trusted(settings.mitmproxy_ca_cert)

        # 2. Resolve explicit rules → {domain: {host, port, scheme}}
        server_port = app.state.config.server.port
        sf_scheme = "https" if app.state.config.server.ssl else "http"
        rules_map = _resolve_rules(settings.rules, app.state.frontends)

        # 3. Auto-discovered frontends
        auto_map = app.state.frontends.get_domain_map()

        # 4. Merge: auto first, rules overlay (rules win on conflict)
        merged = {**auto_map, **rules_map}

        # 5. No fallback — if empty, error and skip interception
        if not merged:
            raise RuntimeError(
                "No routing rules and no auto-discovered frontends — nothing to intercept"
            )

        # 6. Write merged map to frontends.json for the addon
        FRONTENDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        FRONTENDS_FILE.write_text(json.dumps(merged, indent=2))

        domains = list(merged.keys())
        logger.info("Intercepting domains: %s", domains)

        # 7. Build mitmproxy command
        # If all rules use the same process_filter, pass it to mitmproxy.
        # Mixed filters can't be expressed in --mode local:<proc>, so use plain local.
        filters = {r.process_filter for r in settings.rules if r.process_filter}
        mode = f"local:{filters.pop()}" if len(filters) == 1 else "local"
        logger.info(
            "[E2E-TRACE] MITMPROXY mode=%s domains=%s proxy_port=%d",
            mode,
            domains,
            settings.proxy_port,
        )
        allow_hosts = "|".join(re.escape(d) for d in domains)

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

        # 8. Pass fallback connection info to addon via env (frontends.json is
        #    the primary source; these env vars are the fallback)
        env = {
            **os.environ,
            "SF_HOST": "127.0.0.1",
            "SF_PORT": str(server_port),
            "SF_SCHEME": sf_scheme,
        }

        # 9. Start mitmproxy subprocess (requires root for --mode local)
        logger.info("Starting mitmproxy: %s", " ".join(cmd))
        self._process = _sudo_popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # 10. Wait briefly and check if process started OK
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

        # 10b. Safety net: ensure cleanup runs even on unhandled exits
        atexit.register(self._stop_mitmproxy)

        # 11. Save state for crash recovery
        save_state(
            MitmproxyState(
                active=True,
                activated_at=now_iso(),
                pid=self._process.pid,
                proxy_port=settings.proxy_port,
            )
        )

        # 12. Register shutdown hook
        hooks.register("app.shutdown", self._on_shutdown, plugin_name=self.name)

    async def _on_shutdown(self) -> None:
        self._stop_mitmproxy()

    def teardown(self) -> None:
        self._stop_mitmproxy()

    def _stop_mitmproxy(self) -> None:
        """Terminate the mitmproxy subprocess gracefully."""
        atexit.unregister(self._stop_mitmproxy)
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
    _clear_intercept()
    clear_state()


def _clear_intercept() -> None:
    """Clear the macOS local-redirect intercept so traffic flows normally.

    The mitmproxy redirector app (Network Extension) persists independently
    of the mitmdump process.  If mitmdump crashes or is killed without a
    clean shutdown, the extension keeps redirecting traffic into a void.
    This function connects to the existing redirector app and sets an empty
    intercept spec, restoring normal traffic flow.
    """
    import asyncio

    async def _do_clear() -> None:
        from mitmproxy_rs.local import start_local_redirector

        async def _noop(_stream: object) -> None:
            pass

        redirector = await start_local_redirector(_noop, _noop)
        redirector.set_intercept("")
        # Don't close — mitmproxy keeps the redirector app alive to avoid
        # re-triggering the macOS approval dialog on next start.

    try:
        asyncio.run(_do_clear())
        logger.info("Cleared stale mitmproxy intercept")
    except Exception:
        logger.debug("Could not clear mitmproxy intercept", exc_info=True)
