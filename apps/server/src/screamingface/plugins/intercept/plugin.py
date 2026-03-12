"""Intercept plugin — transparent DNS/SSL proxy for AI API traffic."""

from __future__ import annotations

import logging
import os
import socket
import subprocess
from typing import TYPE_CHECKING

from pydantic_settings import SettingsConfigDict

from screamingface.plugin import Plugin, PluginSettings
from screamingface.plugins.intercept import dns
from screamingface.plugins.intercept.certs import ensure_intercept_certs
from screamingface.plugins.intercept.hosts import add_entries, flush_dns, remove_entries
from screamingface.plugins.intercept.state import (
    InterceptState,
    clear_state,
    hosts_hash,
    is_stale,
    load_state,
    now_iso,
    save_state,
)
from screamingface.plugins.intercept.trust import ensure_node_trusts_ca

if TYPE_CHECKING:
    import typer
    from fastapi import FastAPI

    from screamingface.core.classes import ClassRegistry
    from screamingface.core.hooks import HookRegistry
    from screamingface.core.routes import RouteRegistry

logger = logging.getLogger(__name__)


class InterceptSettings(PluginSettings):
    model_config = SettingsConfigDict(
        env_prefix="SF_INTERCEPT__",
        env_nested_delimiter="__",
    )
    domains: list[str] = ["api.anthropic.com"]
    target_ip: str = "127.0.0.1"
    auto_cleanup: bool = True  # clean stale state on startup
    server_port: int = 8000  # port the server listens on (for pfctl forwarding)


class InterceptPlugin(Plugin):
    name = "intercept"
    description = "Transparent DNS/SSL proxy — redirects AI API traffic through ScreamingFace"
    settings_class = InterceptSettings
    system_deps = ["mkcert"]

    def preflight(self) -> tuple[bool, str]:
        ok, reason = super().preflight()
        if not ok:
            return ok, reason

        # Check for stale state from a previous crash
        if is_stale():
            if self.settings.auto_cleanup:  # type: ignore[union-attr]
                logger.warning("Stale intercept state detected — auto-cleaning...")
                _cleanup_stale()
                return True, ""
            return False, (
                "Stale intercept state detected (previous server crashed). "
                "Run 'sf intercept off' or set SF_INTERCEPT__AUTO_CLEANUP=true"
            )

        return True, ""

    def setup(
        self,
        app: FastAPI,
        hooks: HookRegistry,
        classes: ClassRegistry,
        routes: RouteRegistry,
    ) -> None:
        settings: InterceptSettings = self.settings  # type: ignore[assignment]
        domains = settings.domains

        # 1. Resolve real IPs *before* modifying DNS (avoids routing loop)
        real_ips: dict[str, str] = {}
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

        # 5. Set up port forwarding (443 → server port)
        self._setup_port_forward(settings.server_port)

        # 6. Save state for crash recovery
        save_state(
            InterceptState(
                active=True,
                activated_at=now_iso(),
                domains=domains,
                original_hosts_hash=hosts_hash(),
                pid=os.getpid(),
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
        from screamingface.plugins.intercept.cli import intercept_app

        app.add_typer(intercept_app, name="intercept")


def _cleanup_stale() -> None:
    """Clean up leftover state from a crashed server."""
    state = load_state()
    if state is None:
        return
    logger.info("Cleaning up stale intercept state (PID %d is dead)", state.pid)
    remove_entries()
    flush_dns()
    InterceptPlugin._teardown_port_forward()
    clear_state()
