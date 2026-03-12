"""Claude Intercept plugin — transparent DNS/SSL proxy for AI API traffic."""

from __future__ import annotations

import logging
import os
import socket
import subprocess
from typing import TYPE_CHECKING

from pydantic_settings import SettingsConfigDict

from screamingface.plugin import Plugin, PluginSettings
from screamingface.plugins.claude_intercept import dns
from screamingface.plugins.claude_intercept.certs import ensure_intercept_certs
from screamingface.plugins.claude_intercept.hosts import (
    add_entries,
    flush_dns,
    has_entries,
    remove_entries,
)
from screamingface.plugins.claude_intercept.state import (
    InterceptState,
    clear_state,
    hosts_hash,
    is_stale,
    load_state,
    now_iso,
    save_state,
)
from screamingface.plugins.claude_intercept.trust import (
    ensure_node_trusts_ca,
    has_node_ca_trust,
    remove_node_ca_trust,
)

if TYPE_CHECKING:
    import typer
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry

logger = logging.getLogger(__name__)


class ClaudeInterceptSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_CLAUDE_INTERCEPT__",
        env_nested_delimiter="__",
    )
    domains: list[str] = ["api.anthropic.com"]
    target_ip: str = "127.0.0.1"
    auto_cleanup: bool = True  # clean stale state on startup


class ClaudeInterceptPlugin(Plugin):
    name = "claude-intercept"
    description = "Transparent DNS/SSL proxy — redirects AI API traffic through ScreamingFace"
    settings_class = ClaudeInterceptSettings
    system_deps = ["mkcert"]
    depends = ["claude-frontend"]
    conflicts = ["claude-env-intercept"]
    requires_root = True
    required_port = 443

    def cleanup_stale(self) -> None:
        if is_stale():
            logger.info("Cleaning up stale intercept state from previous run")
            _cleanup_stale()
        if has_node_ca_trust():
            logger.info("Removing stale NODE_EXTRA_CA_CERTS from shell profiles")
            remove_node_ca_trust()

    def preflight(self) -> tuple[bool, str]:
        ok, reason = super().preflight()
        if not ok:
            return ok, reason

        # Must be running as root for /etc/hosts, pfctl, etc.
        if os.getuid() != 0:
            return False, "claude-intercept plugin requires root privileges (run with sudo)"

        # Check for stale state from a previous crash
        if is_stale():
            if self.settings.auto_cleanup:  # type: ignore[union-attr]
                logger.warning("Stale intercept state detected — auto-cleaning...")
                _cleanup_stale()
                return True, ""
            return False, (
                "Stale intercept state detected (previous server crashed). "
                "Run 'sf claude-intercept off' or set SF_CLAUDE_INTERCEPT__AUTO_CLEANUP=true"
            )

        return True, ""

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        settings: ClaudeInterceptSettings = self.settings  # type: ignore[assignment]
        domains = settings.domains

        # 1. Resolve real IPs *before* modifying DNS (avoids routing loop)
        #    On reload, /etc/hosts already points domains to 127.0.0.1, so
        #    socket.getaddrinfo would return localhost — use persisted IPs instead.
        real_ips: dict[str, str] = {}

        if has_entries():
            # /etc/hosts already modified (reload scenario) — use stored IPs
            state = load_state()
            if state and state.real_ips:
                real_ips = state.real_ips
                logger.info("Loaded real IPs from state file: %s", real_ips)
            else:
                # Fallback: resolve via external DNS server
                for domain in domains:
                    ip = _resolve_via_dns(domain)
                    if ip:
                        real_ips[domain] = ip
                        logger.info("Resolved %s → %s (via dig fallback)", domain, ip)
        else:
            # Fresh start — /etc/hosts is clean, resolve normally
            for domain in domains:
                try:
                    addrs = socket.getaddrinfo(domain, 443, socket.AF_INET)
                    real_ips[domain] = str(addrs[0][4][0])
                    logger.info("Resolved %s → %s (real upstream)", domain, real_ips[domain])
                except socket.gaierror:
                    logger.warning("Could not resolve %s — skipping real IP lookup", domain)

        # Install process-local DNS override so the proxy connects to
        # real upstream IPs instead of looping back to localhost.
        dns.install(real_ips)

        # Mark intercepted domains on app.state so the proxy can filter
        # by Host header (only proxy requests to intercepted domains).
        app.state.intercept_domains = set(domains)

        # Capture hosts hash BEFORE modifying /etc/hosts (for crash recovery)
        original_hash = hosts_hash()

        try:
            # 2. Generate SSL certs covering intercepted domains
            cert, key = ensure_intercept_certs(domains)
            app.state.intercept_cert = cert
            app.state.intercept_key = key

            # 3. Ensure Node.js trusts the mkcert CA (one-time shell profile setup)
            #    This makes Claude Code (Node.js) trust our certs transparently.
            ensure_node_trusts_ca()

            # 4. Modify /etc/hosts
            add_entries(domains, settings.target_ip)
            flush_dns()

            # 5. Set up port forwarding (443 → server port) if needed
            actual_port = app.state.config.server.port
            if actual_port != 443:
                self._setup_port_forward(actual_port)
            else:
                logger.info("Server already on port 443 — skipping pfctl forwarding")
        except Exception:
            logger.exception("Intercept setup failed — rolling back")
            self._teardown_common()
            raise

        # 6. Save state for crash recovery (includes real_ips for reload)
        save_state(
            InterceptState(
                active=True,
                activated_at=now_iso(),
                domains=domains,
                original_hosts_hash=original_hash,
                pid=os.getpid(),
                real_ips=real_ips,
            )
        )

        # 7. Register shutdown hook for clean teardown
        hooks.register("app.shutdown", self._on_shutdown, plugin_name=self.name)

    async def _on_shutdown(self) -> None:
        """Async shutdown hook — clean up DNS and port forwarding."""
        self._teardown_common()

    def teardown(self) -> None:
        self._teardown_common()

    def _teardown_common(self) -> None:
        """Shared cleanup logic for both shutdown hook and explicit teardown."""
        dns.uninstall()
        remove_entries()
        flush_dns()
        self._teardown_port_forward()
        remove_node_ca_trust()
        clear_state()

    def _setup_port_forward(self, server_port: int) -> None:
        """Set up pfctl to forward port 443 → server_port on loopback (macOS)."""
        rule = (
            f"rdr pass on lo0 inet proto tcp "
            f"from any to 127.0.0.1 port 443 -> 127.0.0.1 port {server_port}\n"
        )
        logger.info("Setting up port forwarding: 443 → %d", server_port)
        subprocess.run(
            ["sudo", "pfctl", "-ef", "-"],
            input=rule.encode(),
            check=True,
            capture_output=True,
        )

    @staticmethod
    def _teardown_port_forward() -> None:
        """Disable pfctl port forwarding."""
        logger.info("Tearing down port forwarding")
        subprocess.run(
            ["sudo", "pfctl", "-d"],
            check=False,  # OK if already disabled
            capture_output=True,
        )

    @classmethod
    def register_cli(cls, app: typer.Typer) -> None:
        from screamingface.plugins.claude_intercept.cli import claude_intercept_app

        app.add_typer(claude_intercept_app, name="claude-intercept")


def _resolve_via_dns(domain: str, dns_server: str = "8.8.8.8") -> str | None:
    """Resolve domain via external DNS, bypassing /etc/hosts."""
    try:
        result = subprocess.run(
            ["dig", "+short", domain, f"@{dns_server}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line and not line.endswith("."):  # skip CNAME lines
                return line
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.warning("dig not available or timed out for %s", domain)
    return None


def _cleanup_stale() -> None:
    """Clean up leftover state from a crashed server."""
    state = load_state()
    if state is None:
        return
    logger.info("Cleaning up stale intercept state (PID %d is dead)", state.pid)
    remove_entries()
    flush_dns()
    ClaudeInterceptPlugin._teardown_port_forward()
    remove_node_ca_trust()
    clear_state()
